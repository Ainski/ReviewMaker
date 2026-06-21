#!/usr/bin/env python3
"""Flask GUI server for the Literature Review Agent Tool."""

import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory, Response

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import config
from src.paper_fetcher import fetch_papers_for_queries
from src.code_finder import find_code_for_papers
from src.paper_ranker import rank_papers, filter_papers, rerank_papers_with_llm
from src.review_generator import generate_review, extract_paper_details, revise_review
from src.query_planner import plan_review_query
from src.citation_manager import generate_bibtex_file, append_references_to_review, validate_citations
from src.evolution_diagram import generate_category_distribution_chart
from src.gui_figure1 import generate_figure1
from src.poster_generator import generate_poster

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ---- Job store (thread-safe) ----
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

OUTPUT_BASE = PROJECT_ROOT / "output" / "gui_runs"
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)


def _update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _strip_reference_section(review_text: str) -> str:
    """Remove the auto-appended reference section before revision."""
    marker = "\n## 参考文献"
    if marker in review_text:
        return review_text.split(marker, 1)[0].rstrip()
    if review_text.startswith("## 参考文献"):
        return ""
    return review_text.rstrip()


def _paper_dict_to_reference_like_paper(p: dict):
    """Create a minimal object compatible with citation_manager helpers."""
    from src.models import Paper, Author
    arxiv_url = p.get("arxiv_url")
    arxiv_id = ""
    if arxiv_url and "/abs/" in arxiv_url:
        arxiv_id = arxiv_url.rsplit("/abs/", 1)[-1]
    title = p.get("title", "")
    return Paper(
        arxiv_id=arxiv_id or f"paper_{p.get('index', '')}",
        title=title,
        abstract="",
        authors=[Author(name=p.get("first_author") or "Unknown")],
        year=int(p.get("year") or 0),
        journal=p.get("venue") or None,
        arxiv_url=arxiv_url,
        pdf_url=p.get("pdf_url"),
        has_code=bool(p.get("has_code")),
        code_urls=p.get("code_urls") or [],
    )


def _run_pipeline_thread(job_id: str, topic: str, max_papers: int, year_range: int,
                          no_code_search: bool, no_poster: bool,
                          use_rag: bool = False, use_agent: bool = False,
                          raw_request: str = ""):
    """Run the full pipeline in a background thread, updating job progress."""
    try:
        job_dir = OUTPUT_BASE / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        warnings = []

        # Step 0: Plan request
        _update_job(job_id, status="running", step="正在解析综述需求...", progress=3)
        query_plan = plan_review_query(
            raw_request or topic,
            api_key=config.deepseek_api_key,
            model=config.deepseek_model,
            base_url=config.deepseek_base_url,
        )
        warnings.extend(query_plan.warnings)
        topic = query_plan.chinese_topic or query_plan.topic or topic
        search_topic = query_plan.topic or topic
        _update_job(
            job_id,
            progress=5,
            step=f"已提取主题: {topic}",
            query_plan={
                "topic": query_plan.topic,
                "chinese_topic": query_plan.chinese_topic,
                "search_queries": query_plan.normalized_queries(),
                "focus_keywords": query_plan.focus_keywords,
                "source": query_plan.source,
            },
        )

        # Step 1: Fetch
        _update_job(job_id, status="running", step="正在多 query 检索论文...", progress=8)
        papers, fetch_warnings, query_stats = fetch_papers_for_queries(
            plan=query_plan,
            max_results=max_papers,
            year_range=year_range,
            api_key=config.semantic_scholar_api_key,
        )
        warnings.extend(fetch_warnings)
        if not papers:
            _update_job(job_id, status="error", message="未找到相关论文，请尝试扩大搜索范围。")
            return
        _update_job(job_id, progress=15, step=f"已获取 {len(papers)} 篇论文")

        # Code search is intentionally delayed until after ranking/filtering.
        # Searching every raw candidate is slow and wastes API quota.
        _update_job(job_id, progress=30)

        # Step 3: Rank
        _update_job(job_id, step="正在排序论文...", progress=35)
        ranked_candidates = rank_papers(
            papers,
            search_topic,
            year_range=year_range,
            focus_keywords=query_plan.focus_keywords,
            search_queries=query_plan.normalized_queries(),
        )
        _update_job(job_id, step="正在进行语义相关性重排...", progress=40)
        ranked_candidates = rerank_papers_with_llm(
            ranked_candidates,
            search_topic,
            api_key=config.deepseek_api_key,
            raw_request=raw_request,
            focus_keywords=query_plan.focus_keywords,
            model=config.deepseek_model,
            base_url=config.deepseek_base_url,
            candidate_limit=max(max_papers * 3, 30),
        )
        papers = filter_papers(ranked_candidates, max_papers=max_papers)
        if len(papers) < max_papers:
            warnings.append(
                f"用户请求 {max_papers} 篇论文，系统筛选出 {len(papers)} 篇高相关论文，已继续生成。"
            )
        if not papers:
            papers = ranked_candidates[:min(max_papers, len(ranked_candidates))]
            warnings.append("严格相关性过滤后没有论文达到阈值，已使用排序最高的候选论文继续生成。")
        _update_job(job_id, progress=45, step=f"已筛选 {len(papers)} 篇论文")

        # Step 3a: Code search on selected papers only
        if not no_code_search:
            _update_job(job_id, step=f"正在为 {len(papers)} 篇入选论文搜索代码...", progress=46)
            papers = find_code_for_papers(
                papers,
                github_token=config.github_token,
                deepseek_api_key=config.deepseek_api_key,
                deepseek_model=config.deepseek_model,
                deepseek_base_url=config.deepseek_base_url,
                scan_pdf=True,
                verify_with_llm=True,
                max_workers=3,
            )

        # Step 3b (optional): RAG enrichment
        rag_data = {}
        if use_rag:
            _update_job(job_id, step="RAG 增强: 正在下载PDF全文并提取相关内容...", progress=48)
            from src.rag_engine import batch_rag_enrich
            try:
                evidence_query = (
                    f"{search_topic} dataset benchmark experiments evaluation results "
                    "accuracy latency throughput memory table code github repository"
                )
                rag_data = batch_rag_enrich(papers, evidence_query, max_chunks_per_paper=8)
                num_rag = sum(1 for v in rag_data.values() if v["context"])
                _update_job(job_id, progress=55, step=f"RAG: {num_rag}/{len(papers)} 篇论文全文提取完成")
            except Exception as e:
                _update_job(job_id, step=f"RAG 步骤出错 (将使用摘要): {e}")

        # Step 4a: Extract details
        _update_job(job_id, step="DeepSeek AI 正在提取论文详情...", progress=60)
        papers = extract_paper_details(papers, api_key=config.deepseek_api_key,
                                        model=config.deepseek_model,
                                        base_url=config.deepseek_base_url,
                                        rag_data=rag_data)
        _update_job(job_id, progress=65)

        # Step 4b: Generate review (with RAG if enabled)
        _update_job(job_id, step="DeepSeek AI 正在生成综述...", progress=70)
        if use_rag and rag_data:
            from src.agents import ReviewerAgent
            # Use RAG-augmented review generation
            try:
                reviewer = ReviewerAgent()
                import threading as _thr
                state = _thr.local()
                state.papers = papers
                state.topic = topic
                state.rag_data = rag_data
                user_prompt = reviewer._build_rag_augmented_prompt(papers, topic, rag_data)
                from src.review_generator import _build_system_prompt
                from openai import OpenAI
                client = OpenAI(api_key=config.deepseek_api_key, base_url=config.deepseek_base_url)
                response = client.chat.completions.create(
                    model=config.deepseek_model,
                    max_tokens=8192,
                    messages=[
                        {"role": "system", "content": _build_system_prompt()},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                review_text = response.choices[0].message.content or ""
            except Exception:
                review_text = generate_review(papers, topic, api_key=config.deepseek_api_key,
                                              model=config.deepseek_model,
                                              base_url=config.deepseek_base_url,
                                              raw_request=raw_request,
                                              focus_keywords=query_plan.focus_keywords)
        else:
            review_text = generate_review(papers, topic, api_key=config.deepseek_api_key,
                                           model=config.deepseek_model,
                                           base_url=config.deepseek_base_url,
                                           raw_request=raw_request,
                                           focus_keywords=query_plan.focus_keywords)
        validation = validate_citations(review_text, len(papers))
        final_review = append_references_to_review(review_text, papers)

        review_path = job_dir / "review.md"
        review_path.write_text(final_review, encoding="utf-8")

        bib_path = job_dir / "references.bib"
        generate_bibtex_file(papers, str(bib_path))
        _update_job(job_id, progress=75, step="综述已生成")

        # Step 5: Diagrams — Figure-1 milestone lineage (SVG) replaces the scatter
        _update_job(job_id, step="正在生成演进谱系图...", progress=80)
        evo_path = job_dir / "evolution.svg"
        graph = None
        try:
            graph = generate_figure1(papers, topic, job_dir)
        except Exception as e:
            logger.exception("Figure-1 generation failed")
            _update_job(job_id, step=f"演进图生成出错: {e}")

        dist_path = job_dir / "distribution.png"
        generate_category_distribution_chart(papers, output_path=str(dist_path))
        _update_job(job_id, progress=90, step="图表已生成")

        # Poster (redesigned: figure1 lineage hero + 图文并茂, reuses the graph above)
        poster_path = None
        if not no_poster and graph is not None:
            _update_job(job_id, step="正在生成海报...", progress=92)
            try:
                result = generate_poster(topic, review_text, papers, graph, str(job_dir))
                poster_path = result.get("png") or result.get("html")
            except Exception as e:
                logger.exception("Poster generation failed")
                _update_job(job_id, step=f"海报生成出错: {e}")
                poster_path = None

        # Build paper list data for frontend
        paper_list = []
        for i, p in enumerate(papers, start=1):
            paper_list.append({
                "index": i,
                "title": p.title,
                "first_author": p.first_author,
                "year": p.year,
                "venue": p.journal or "",
                "citations": p.citation_count,
                "arxiv_url": p.arxiv_url,
                "pdf_url": p.pdf_url,
                "has_code": p.has_code,
                "code_urls": p.code_urls,
                "method_category": p.method_category or "未分类",
                "key_innovation": p.key_innovation or "",
                "datasets_used": p.datasets_used,
                "key_results": p.key_results or "",
                "evidence_source": p.evidence_source or "",
                "detail_confidence": p.detail_confidence,
            })

        _update_job(job_id,
            status="done",
            progress=100,
            step="完成",
            result={
                "review_text": final_review,
                "paper_count": len(papers),
                "requested_count": max_papers,
                "warnings": warnings,
                "query_plan": {
                    "topic": query_plan.topic,
                    "chinese_topic": query_plan.chinese_topic,
                    "search_queries": query_plan.normalized_queries(),
                    "focus_keywords": query_plan.focus_keywords,
                    "source": query_plan.source,
                    "query_stats": query_stats,
                },
                "papers": paper_list,
                "validation": {
                    "valid": len(validation["valid_citations"]),
                    "total": len(papers),
                    "missing": list(validation["missing_citations"]),
                },
                "files": {
                    "review": f"/output/{job_id}/review.md",
                    "bib": f"/output/{job_id}/references.bib",
                    "evolution": f"/output/{job_id}/evolution.svg",
                    "evolution_nodes": f"/output/{job_id}/evolution_nodes.json",
                    "distribution": f"/output/{job_id}/distribution.png",
                    "poster": f"/output/{job_id}/poster.html" if poster_path else None,
                    "poster_png": f"/output/{job_id}/poster.png" if poster_path else None,
                }
            },
        )

    except Exception as e:
        logger.exception(f"Job {job_id} failed")
        _update_job(job_id, status="error", message=str(e))


# ---- Routes ----

@app.route("/")
def index():
    """Main GUI page."""
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    """Start a new review job."""
    data = request.get_json()
    topic = data.get("topic", "").strip()
    raw_request = data.get("raw_request", "").strip()
    if not topic and raw_request:
        topic = raw_request
    if not topic:
        return jsonify({"error": "请输入研究主题"}), 400

    job_id = uuid.uuid4().hex[:12]
    max_papers = int(data.get("max_papers", config.max_papers))
    year_range = int(data.get("year_range", config.year_range))
    no_code_search = bool(data.get("no_code_search", False))
    no_poster = bool(data.get("no_poster", False))
    use_rag = bool(data.get("use_rag", False))
    use_agent = bool(data.get("use_agent", False))

    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "topic": topic,
            "status": "starting",
            "progress": 0,
            "step": "初始化中...",
            "message": "",
            "result": None,
            "created_at": datetime.now().isoformat(),
        }

    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(job_id, topic, max_papers, year_range, no_code_search, no_poster, use_rag, use_agent, raw_request),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/progress/<job_id>")
def api_progress(job_id):
    """Get current progress of a job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": job["status"],
        "progress": job["progress"],
        "step": job["step"],
        "message": job.get("message", ""),
        "query_plan": job.get("query_plan"),
        "result": job.get("result"),
    })


@app.route("/api/revise", methods=["POST"])
def api_revise():
    """Revise the generated review according to a follow-up chat instruction."""
    data = request.get_json()
    job_id = (data.get("job_id") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    if not job_id:
        return jsonify({"error": "缺少 job_id"}), 400
    if not instruction:
        return jsonify({"error": "请输入修改意见"}), 400

    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or not job.get("result"):
        return jsonify({"error": "当前没有可修改的综述结果"}), 404

    result = job["result"]
    current_review = _strip_reference_section(result.get("review_text", ""))
    papers = result.get("papers", [])
    if not current_review or not papers:
        return jsonify({"error": "当前结果缺少综述正文或论文列表，无法修改"}), 400

    try:
        revised_body = revise_review(
            current_review=current_review,
            papers=papers,
            user_instruction=instruction,
            api_key=config.deepseek_api_key,
            model=config.deepseek_model,
            base_url=config.deepseek_base_url,
        )

        ref_papers = [_paper_dict_to_reference_like_paper(p) for p in papers]
        final_review = append_references_to_review(revised_body, ref_papers)
        validation = validate_citations(revised_body, len(papers))

        result["review_text"] = final_review
        result["validation"] = {
            "valid": len(validation["valid_citations"]),
            "total": len(papers),
            "missing": list(validation["missing_citations"]),
        }
        result.setdefault("revision_history", []).append({
            "instruction": instruction,
            "created_at": datetime.now().isoformat(),
        })

        review_path = OUTPUT_BASE / job_id / "review.md"
        review_path.write_text(final_review, encoding="utf-8")

        _update_job(job_id, result=result, step="综述已按反馈修改")
        return jsonify({"result": result})
    except Exception as e:
        logger.exception(f"Review revision failed for job {job_id}")
        return jsonify({"error": str(e)}), 500


@app.route("/output/<path:filepath>")
def serve_output(filepath):
    """Serve generated output files."""
    return send_from_directory(str(OUTPUT_BASE), filepath)


@app.route("/api/config")
def api_config():
    """Return current config (without sensitive keys)."""
    return jsonify({
        "max_papers": config.max_papers,
        "year_range": config.year_range,
        "has_api_key": bool(config.deepseek_api_key),
    })


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("\n  📚 文献综述 Agent 工具 - Web GUI")
    print("  ─────────────────────────────────")
    print("  打开浏览器访问: http://127.0.0.1:7860\n")
    app.run(host="127.0.0.1", port=7860, debug=False)


if __name__ == "__main__":
    main()
