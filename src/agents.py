"""Multi-Agent architecture for the Literature Review Tool.

Agents:
- OrchestratorAgent: Coordinates the workflow, manages state
- SearcherAgent:  Handles paper fetching + code discovery
- AnalystAgent:   Handles paper ranking + RAG enrichment + detail extraction
- ReviewerAgent:  Handles review generation with RAG-augmented context
- VisualizerAgent: Handles evolution diagram + poster generation
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any

from config import config
from src.models import Paper
from src.paper_fetcher import fetch_papers
from src.code_finder import find_code_for_papers
from src.paper_ranker import rank_papers, filter_papers
from src.review_generator import generate_review, extract_paper_details
from src.citation_manager import (
    generate_bibtex_file,
    append_references_to_review,
    validate_citations,
)
from src.evolution_diagram import generate_evolution_diagram, generate_category_distribution_chart
from src.svg_poster_generator import generate_svg_poster
from src.rag_engine import batch_rag_enrich

logger = logging.getLogger(__name__)


# ---- Workflow State ----

@dataclass
class WorkflowState:
    """Shared state passed between agents in the pipeline."""
    topic: str
    max_papers: int = 20
    year_range: int = 5
    no_code_search: bool = False
    no_poster: bool = False

    # Intermediate results
    papers: list[Paper] = field(default_factory=list)
    rag_data: dict[str, dict] = field(default_factory=dict)
    review_text: str = ""
    final_review: str = ""

    # Output paths
    output_dir: str = "output"
    review_path: str = ""
    bib_path: str = ""
    evo_path: str = ""
    dist_path: str = ""
    poster_path: str = ""

    # Metadata
    steps_completed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def log_step(self, step: str) -> None:
        self.steps_completed.append(step)
        logger.info(f"[Workflow] {step}")


# ---- Agent Base Class ----

class BaseAgent(ABC):
    """Abstract base for all agents."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def run(self, state: WorkflowState) -> WorkflowState:
        """Execute the agent's task and return updated state."""
        ...

    def log(self, msg: str) -> None:
        logger.info(f"[{self.name}] {msg}")


# ---- SearcherAgent ----

class SearcherAgent(BaseAgent):
    """Responsible for fetching papers from arXiv + Semantic Scholar,
    and discovering associated GitHub code repositories."""

    def __init__(self):
        super().__init__("SearcherAgent")

    def run(self, state: WorkflowState) -> WorkflowState:
        self.log(f"开始搜索论文: {state.topic}")

        # Step 1: Fetch papers
        papers = fetch_papers(
            topic=state.topic,
            max_results=state.max_papers,
            year_range=state.year_range,
            api_key=config.semantic_scholar_api_key,
        )
        if not papers:
            state.errors.append("未找到相关论文")
            return state

        self.log(f"从 arXiv + Semantic Scholar 获取 {len(papers)} 篇论文")
        state.log_step(f"论文抓取: {len(papers)} 篇")

        # Step 2: Find code
        if not state.no_code_search:
            papers = find_code_for_papers(papers, github_token=config.github_token)
            num_code = sum(1 for p in papers if p.has_code)
            self.log(f"为 {num_code}/{len(papers)} 篇论文找到开源代码")
            state.log_step(f"代码搜索: {num_code} 篇含代码")

        state.papers = papers
        return state


# ---- AnalystAgent ----

class AnalystAgent(BaseAgent):
    """Responsible for ranking papers, RAG enrichment,
    and extracting structured details via LLM."""

    def __init__(self):
        super().__init__("AnalystAgent")

    def run(self, state: WorkflowState) -> WorkflowState:
        if not state.papers:
            state.errors.append("AnalystAgent: 无输入论文")
            return state

        # Step 1: Rank
        self.log("排序论文...")
        papers = rank_papers(state.papers, state.topic, year_range=state.year_range)
        papers = filter_papers(papers, max_papers=state.max_papers)
        self.log(f"排序后保留 {len(papers)} 篇高质量论文")
        state.log_step(f"论文排序: {len(papers)} 篇")

        # Step 2: RAG Enrichment — download PDFs and extract full text + images
        self.log("RAG 增强: 下载 PDF 全文并提取相关段落...")
        try:
            rag_data = batch_rag_enrich(
                papers, state.topic,
                max_chunks_per_paper=5,
            )
            num_with_rag = sum(1 for v in rag_data.values() if v["context"])
            self.log(f"RAG 完成: {num_with_rag}/{len(papers)} 篇论文提取了全文上下文")
            state.log_step(f"RAG 增强: {num_with_rag} 篇全文提取")
        except Exception as e:
            self.log(f"RAG 步骤出错 (将使用摘要): {e}")
            rag_data = {}
        state.rag_data = rag_data

        # Step 3: Extract structured details via LLM
        self.log("提取论文结构化信息...")
        try:
            papers = extract_paper_details(
                papers,
                api_key=config.deepseek_api_key,
                model=config.deepseek_model,
                base_url=config.deepseek_base_url,
            )
            state.log_step("论文详情提取: 完成")
        except Exception as e:
            state.errors.append(f"论文详情提取失败: {e}")

        state.papers = papers
        return state


# ---- ReviewerAgent ----

class ReviewerAgent(BaseAgent):
    """Responsible for generating the structured literature review,
    now with RAG-augmented context from full-text PDFs."""

    def __init__(self):
        super().__init__("ReviewerAgent")

    def _build_rag_augmented_prompt(
        self, papers: list[Paper], topic: str, rag_data: dict
    ) -> str:
        """Build a user prompt enriched with RAG full-text context."""
        from src.review_generator import _build_paper_context

        paper_blocks = []
        for i, paper in enumerate(papers, start=1):
            base_block = _build_paper_context(paper, i)

            # Augment with RAG context if available
            rag = rag_data.get(paper.arxiv_id, {})
            rag_context = rag.get("context", "")
            if rag_context:
                # Truncate to fit within token limits
                rag_snippet = rag_context[:1500]
                base_block += (
                    f"\n  [RAG 全文增强内容 — 以下来自 PDF 全文的相关段落]:\n"
                    f"  {rag_snippet}\n"
                )

            paper_blocks.append(base_block)

        papers_text = "\n\n".join(paper_blocks)

        return f"""主题：{topic}
论文数量：{len(papers)} 篇

{papers_text}

【严格执行】
- 直接从 "## 一、引言" 开始输出，在此之前不要有任何文字。
- 文中引用标注 [1]-[{len(papers)}]。
- 不要输出参考文献列表。
- 充分利用 [RAG 全文增强内容] 中的技术细节。"""

    def run(self, state: WorkflowState) -> WorkflowState:
        if not state.papers:
            state.errors.append("ReviewerAgent: 无输入论文")
            return state

        self.log(f"生成综述 (RAG增强模式, {len(state.papers)} 篇论文)...")

        # Import here to access internal functions
        from src.review_generator import _build_system_prompt, generate_review

        # We call the existing generate_review but with a RAG-augmented user prompt.
        # Since generate_review builds its own user prompt, we need to work with it.
        # Strategy: store RAG data temporarily so _build_user_prompt can access it.
        # Simpler approach: directly call the API with our augmented prompt.

        from openai import OpenAI

        client = OpenAI(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
        )

        system_prompt = _build_system_prompt()
        user_prompt = self._build_rag_augmented_prompt(
            state.papers, state.topic, state.rag_data
        )

        try:
            response = client.chat.completions.create(
                model=config.deepseek_model,
                max_tokens=8192,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            review_text = response.choices[0].message.content or ""
            self.log(f"综述生成完成: {len(review_text)} 字符")
        except Exception as e:
            state.errors.append(f"综述生成失败: {e}")
            # Fallback to regular generation without RAG
            self.log("回退到非RAG模式生成综述...")
            review_text = generate_review(
                state.papers, state.topic,
                api_key=config.deepseek_api_key,
                model=config.deepseek_model,
                base_url=config.deepseek_base_url,
            )

        # Validate + append references
        validation = validate_citations(review_text, len(state.papers))
        state.log_step(
            f"综述生成: {len(review_text)} 字符, "
            f"引用覆盖 {len(validation['valid_citations'])}/{len(state.papers)}"
        )

        final_review = append_references_to_review(review_text, state.papers)
        state.review_text = review_text
        state.final_review = final_review

        # Save
        os.makedirs(state.output_dir, exist_ok=True)
        review_path = os.path.join(state.output_dir, "review.md")
        with open(review_path, "w", encoding="utf-8") as f:
            f.write(final_review)
        state.review_path = review_path

        bib_path = os.path.join(state.output_dir, "references.bib")
        generate_bibtex_file(state.papers, bib_path)
        state.bib_path = bib_path

        return state


# ---- VisualizerAgent ----

class VisualizerAgent(BaseAgent):
    """Responsible for generating evolution diagrams and the academic poster.
    Now embeds original paper figures into the poster."""

    def __init__(self):
        super().__init__("VisualizerAgent")

    def run(self, state: WorkflowState) -> WorkflowState:
        if not state.papers:
            state.errors.append("VisualizerAgent: 无输入论文")
            return state

        self.log("生成可视化图表...")

        # Evolution diagram
        evo_path = os.path.join(state.output_dir, "evolution.png")
        generate_evolution_diagram(state.papers, state.topic, output_path=evo_path)
        state.evo_path = evo_path
        self.log(f"演进图: {evo_path}")

        # Category distribution
        dist_path = os.path.join(state.output_dir, "distribution.png")
        generate_category_distribution_chart(state.papers, output_path=dist_path)
        state.dist_path = dist_path

        # Poster with paper figures
        if not state.no_poster:
            poster_path = os.path.join(state.output_dir, "poster.svg")

            # Collect paper figures from RAG data
            paper_figures = []
            for p in state.papers:
                rag = state.rag_data.get(p.arxiv_id, {})
                images = rag.get("images", [])
                if images:
                    # Take the largest image (probably the most meaningful figure)
                    largest = max(images, key=lambda x: x.get("size_bytes", 0))
                    paper_figures.append({
                        "arxiv_id": p.arxiv_id,
                        "first_author": p.first_author,
                        "year": p.year,
                        "image_bytes": largest["image_bytes"],
                    })

            self.log(f"从论文PDF提取了 {len(paper_figures)} 张图片用于海报")

            generate_svg_poster(
                papers=state.papers,
                topic=state.topic,
                review_summary=state.review_text,
                evolution_diagram_path=evo_path,
                output_path=poster_path,
                paper_figures=paper_figures if paper_figures else None,
                generate_png=True,
            )
            state.poster_path = poster_path
            self.log(f"海报: {poster_path}")

        state.log_step(f"可视化: 演进图+分布图+海报")
        return state


# ---- OrchestratorAgent ----

class OrchestratorAgent(BaseAgent):
    """Top-level orchestrator that coordinates all agents in sequence."""

    def __init__(self):
        super().__init__("Orchestrator")
        self.searcher = SearcherAgent()
        self.analyst = AnalystAgent()
        self.reviewer = ReviewerAgent()
        self.visualizer = VisualizerAgent()

    def run(self, state: WorkflowState) -> WorkflowState:
        """Execute the full multi-agent pipeline."""
        self.log(f"开始工作流: {state.topic}")

        # Phase 1: Search
        state = self.searcher.run(state)
        if state.errors:
            self.log(f"搜索阶段错误: {state.errors}")
            return state

        # Phase 2: Analyze + RAG
        state = self.analyst.run(state)
        if state.errors:
            self.log(f"分析阶段错误 (非致命): {state.errors}")

        # Phase 3: Review
        state = self.reviewer.run(state)
        if state.errors:
            self.log(f"综述阶段错误: {state.errors}")

        # Phase 4: Visualize
        state = self.visualizer.run(state)
        if state.errors:
            self.log(f"可视化阶段错误: {state.errors}")

        self.log(f"工作流完成: {state.steps_completed}")
        return state


def run_agent_pipeline(
    topic: str,
    max_papers: int = 20,
    year_range: int = 5,
    no_code_search: bool = False,
    no_poster: bool = False,
    output_dir: str = "output",
) -> WorkflowState:
    """
    Convenience function to run the full agent pipeline.

    Args:
        topic: Research topic
        max_papers: Max papers to fetch
        year_range: Year range for search
        no_code_search: Skip GitHub code search
        no_poster: Skip poster generation
        output_dir: Output directory

    Returns:
        WorkflowState with all results
    """
    state = WorkflowState(
        topic=topic,
        max_papers=max_papers,
        year_range=year_range,
        no_code_search=no_code_search,
        no_poster=no_poster,
        output_dir=output_dir,
    )

    orchestrator = OrchestratorAgent()
    state = orchestrator.run(state)
    return state
