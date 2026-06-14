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
from src.paper_fetcher import fetch_papers
from src.code_finder import find_code_for_papers
from src.paper_ranker import rank_papers, filter_papers
from src.review_generator import generate_review, extract_paper_details
from src.citation_manager import generate_bibtex_file, append_references_to_review, validate_citations
from src.evolution_diagram import generate_evolution_diagram, generate_category_distribution_chart
from src.svg_poster_generator import generate_svg_poster

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


def _run_pipeline_thread(job_id: str, topic: str, max_papers: int, year_range: int,
                          no_code_search: bool, no_poster: bool,
                          use_rag: bool = False, use_agent: bool = False):
    """Run the full pipeline in a background thread, updating job progress."""
    try:
        job_dir = OUTPUT_BASE / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Fetch
        _update_job(job_id, status="running", step="正在从 arXiv 抓取论文...", progress=5)
        papers = fetch_papers(topic=topic, max_results=max_papers, year_range=year_range)
        if not papers:
            _update_job(job_id, status="error", message="未找到相关论文，请尝试扩大搜索范围。")
            return
        _update_job(job_id, progress=15, step=f"已获取 {len(papers)} 篇论文")

        # Step 2: Code search
        if not no_code_search:
            _update_job(job_id, step="正在 GitHub 搜索代码...", progress=20)
            papers = find_code_for_papers(papers, github_token=config.github_token)
        _update_job(job_id, progress=30)

        # Step 3: Rank
        _update_job(job_id, step="正在排序论文...", progress=35)
        papers = rank_papers(papers, topic, year_range=year_range)
        papers = filter_papers(papers, max_papers=max_papers)
        _update_job(job_id, progress=45, step=f"已筛选 {len(papers)} 篇论文")

        # Step 3b (optional): RAG enrichment
        rag_data = {}
        if use_rag:
            _update_job(job_id, step="RAG 增强: 正在下载PDF全文并提取相关内容...", progress=48)
            from src.rag_engine import batch_rag_enrich
            try:
                rag_data = batch_rag_enrich(papers, topic, max_chunks_per_paper=5)
                num_rag = sum(1 for v in rag_data.values() if v["context"])
                _update_job(job_id, progress=55, step=f"RAG: {num_rag}/{len(papers)} 篇论文全文提取完成")
            except Exception as e:
                _update_job(job_id, step=f"RAG 步骤出错 (将使用摘要): {e}")

        # Step 4a: Extract details
        _update_job(job_id, step="DeepSeek AI 正在提取论文详情...", progress=60)
        papers = extract_paper_details(papers, api_key=config.deepseek_api_key,
                                        model=config.deepseek_model,
                                        base_url=config.deepseek_base_url)
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
                                              base_url=config.deepseek_base_url)
        else:
            review_text = generate_review(papers, topic, api_key=config.deepseek_api_key,
                                           model=config.deepseek_model,
                                           base_url=config.deepseek_base_url)
        validation = validate_citations(review_text, len(papers))
        final_review = append_references_to_review(review_text, papers)

        review_path = job_dir / "review.md"
        review_path.write_text(final_review, encoding="utf-8")

        bib_path = job_dir / "references.bib"
        generate_bibtex_file(papers, str(bib_path))
        _update_job(job_id, progress=75, step="综述已生成")

        # Step 5: Diagrams
        _update_job(job_id, step="正在生成演进图...", progress=80)
        evo_path = job_dir / "evolution.png"
        generate_evolution_diagram(papers, topic, output_path=str(evo_path))

        dist_path = job_dir / "distribution.png"
        generate_category_distribution_chart(papers, output_path=str(dist_path))
        _update_job(job_id, progress=90, step="图表已生成")

        # Poster
        poster_path = None
        if not no_poster:
            _update_job(job_id, step="正在生成海报...", progress=92)
            poster_path = job_dir / "poster.svg"
            generate_svg_poster(papers, topic, review_text, str(evo_path), str(poster_path))

        # Build paper list data for frontend
        paper_list = []
        for i, p in enumerate(papers, start=1):
            paper_list.append({
                "index": i,
                "title": p.title,
                "first_author": p.first_author,
                "year": p.year,
                "citations": p.citation_count,
                "has_code": p.has_code,
                "code_urls": p.code_urls,
                "method_category": p.method_category or "未分类",
                "key_innovation": p.key_innovation or "",
                "datasets_used": p.datasets_used,
                "key_results": p.key_results or "",
            })

        _update_job(job_id,
            status="done",
            progress=100,
            step="完成",
            result={
                "review_text": final_review,
                "paper_count": len(papers),
                "papers": paper_list,
                "validation": {
                    "valid": len(validation["valid_citations"]),
                    "total": len(papers),
                    "missing": list(validation["missing_citations"]),
                },
                "files": {
                    "review": f"/output/{job_id}/review.md",
                    "bib": f"/output/{job_id}/references.bib",
                    "evolution": f"/output/{job_id}/evolution.png",
                    "distribution": f"/output/{job_id}/distribution.png",
                    "poster": f"/output/{job_id}/poster.svg" if poster_path else None,
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
        args=(job_id, topic, max_papers, year_range, no_code_search, no_poster, use_rag, use_agent),
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
        "result": job.get("result"),
    })


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
