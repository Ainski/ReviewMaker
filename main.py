#!/usr/bin/env python3
"""
Literature Review Agent Tool
=============================
Automated research paper review generation with:
- Paper fetching from arXiv & Semantic Scholar
- GitHub code discovery
- AI-powered review generation (DeepSeek)
- Citation management
- Algorithm evolution diagrams
- Academic poster generation

Usage:
    python main.py "Transformer attention mechanisms"
    python main.py "Graph Neural Networks" --max-papers 30 --year-range 3
    python main.py "Diffusion models for image generation" --no-code-search --output-dir my_review
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.markdown import Markdown

from config import config
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

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stderr),
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="文献综述Agent工具 — 自动生成研究论文综述",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py "Transformer attention mechanisms"
  python main.py "Graph Neural Networks for drug discovery" --max-papers 30
  python main.py "Diffusion models" --year-range 3 --no-code-search
  python main.py "Federated Learning privacy" --output-dir ./review_output
        """,
    )

    parser.add_argument(
        "topic",
        type=str,
        help="要综述的研究主题（例如: 'Transformer attention mechanisms'）",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=config.max_papers,
        help=f"最大获取论文数量（默认: {config.max_papers}）",
    )
    parser.add_argument(
        "--year-range",
        type=int,
        default=config.year_range,
        help=f"仅包含最近 N 年的论文（默认: {config.year_range}）",
    )
    parser.add_argument(
        "--sort-by",
        type=str,
        default="relevance",
        choices=["relevance", "recency", "citations"],
        help="论文搜索排序依据（默认: relevance）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=config.output_dir,
        help=f"输出目录（默认: {config.output_dir}）",
    )
    parser.add_argument(
        "--no-code-search",
        action="store_true",
        help="跳过GitHub代码搜索（更快，但无代码链接）",
    )
    parser.add_argument(
        "--no-poster",
        action="store_true",
        help="跳过海报生成",
    )
    parser.add_argument(
        "--rag",
        action="store_true",
        help="启用 RAG 增强模式（下载PDF全文，提取相关内容丰富综述）",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="使用多 Agent 协作模式（Searcher→Analyst→Reviewer→Visualizer）",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=config.deepseek_model,
        help=f"DeepSeek 模型（默认: {config.deepseek_model}）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="启用详细日志输出",
    )

    return parser.parse_args()


def run_pipeline(args: argparse.Namespace) -> None:
    """Execute the full literature review pipeline."""
    topic = args.topic
    output_dir = args.output_dir

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    console.print()
    console.rule("[bold blue]文献综述 Agent 工具[/bold blue]")
    console.print(f"[bold]研究主题:[/bold] {topic}")
    console.print(f"[bold]输出目录:[/bold] {output_dir}/")
    if args.agent:
        console.print(f"[bold]模式:[/bold] 多 Agent 协作 (Searcher→Analyst→Reviewer→Visualizer)")
    if args.rag:
        console.print(f"[bold]RAG:[/bold] 已启用 PDF 全文增强")
    console.print()

    # ---- Agent Mode ----
    if args.agent:
        from src.agents import run_agent_pipeline
        console.print("[bold]启动多 Agent 协作工作流...[/bold]")
        state = run_agent_pipeline(
            topic=topic,
            max_papers=args.max_papers,
            year_range=args.year_range,
            no_code_search=args.no_code_search,
            no_poster=args.no_poster,
            output_dir=output_dir,
        )

        # Display results
        if state.errors:
            for err in state.errors:
                console.print(f"  [yellow]⚠[/yellow] {err}")

        console.print()
        console.rule("[bold green]生成完成[/bold green]")
        console.print(f"[bold]工作流步骤:[/bold] {' → '.join(state.steps_completed)}")
        console.print(f"[bold]{output_dir}/ 目录下的输出文件:[/bold]")
        for f in os.listdir(output_dir):
            fpath = os.path.join(output_dir, f)
            size_kb = os.path.getsize(fpath) / 1024
            console.print(f"  • {f} ({size_kb:.1f} KB)")
        return

    # ---- Step 1: Fetch Papers ----
    console.print("[bold]第1步/共5步:[/bold] 从 arXiv 和 Semantic Scholar 抓取论文...")
    papers = fetch_papers(
        topic=topic,
        max_results=args.max_papers,
        year_range=args.year_range,
        sort_by=args.sort_by,
        api_key=config.semantic_scholar_api_key,
    )

    if not papers:
        console.print("[red]未找到相关论文，请尝试扩大搜索范围。[/red]")
        return

    console.print(f"  [green]✓[/green] 找到 {len(papers)} 篇论文")

    # ---- Step 2: Find Code ----
    if not args.no_code_search:
        console.print("[bold]第2步/共5步:[/bold] 在 GitHub 上搜索论文代码...")
        papers = find_code_for_papers(papers, github_token=config.github_token)
        num_with_code = sum(1 for p in papers if p.has_code)
        console.print(f"  [green]✓[/green] 为 {num_with_code}/{len(papers)} 篇论文找到代码")
    else:
        console.print("[bold]第2步/共5步:[/bold] 代码搜索 [dim](已跳过)[/dim]")

    # ---- Step 3: Rank Papers ----
    console.print("[bold]第3步/共5步:[/bold] 按相关性排序...")
    papers = rank_papers(papers, topic, year_range=args.year_range)
    papers = filter_papers(papers, max_papers=args.max_papers)

    # Display top papers
    table = Table(title=f"论文列表: {topic}", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("标题", style="cyan", max_width=60)
    table.add_column("年份", width=6)
    table.add_column("引用数", width=10)
    table.add_column("代码", width=6)
    table.add_column("评分", width=8)

    for i, p in enumerate(papers, start=1):
        code_icon = "✓" if p.has_code else "—"
        code_style = "green" if p.has_code else "dim"
        table.add_row(
            str(i),
            p.short_title,
            str(p.year),
            str(p.citation_count),
            f"[{code_style}]{code_icon}[/{code_style}]",
            f"{p.rank_score:.3f}",
        )

    console.print(table)
    console.print()

    # ---- Step 4: Extract Paper Details & Generate Review ----
    console.print("[bold]第4步/共5步:[/bold] 使用 DeepSeek AI 生成文献综述...")

    # Check API key
    if not config.deepseek_api_key:
        console.print(
            "[red]错误: DEEPSEEK_API_KEY 未设置。 "
            "请在 .env 文件中或环境变量中设置。[/red]"
        )
        return

    # Extract structured details from each paper
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("正在提取论文详情...", total=None)
        papers = extract_paper_details(
            papers,
            api_key=config.deepseek_api_key,
            model=args.model,
            base_url=config.deepseek_base_url,
        )

    # Generate review
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("正在生成综述文本...", total=None)
        review_text = generate_review(
            papers,
            topic,
            api_key=config.deepseek_api_key,
            model=args.model,
            base_url=config.deepseek_base_url,
        )

    # Validate citations
    validation = validate_citations(review_text, len(papers))
    if validation["missing_citations"]:
        console.print(
            f"  [yellow]⚠[/yellow] {len(validation['missing_citations'])} 篇论文在综述中未被引用"
        )
    if validation["invalid_citations"]:
        console.print(
            f"  [yellow]⚠[/yellow] 发现无效引用编号: {validation['invalid_citations']}"
        )

    # Append references to review
    final_review = append_references_to_review(review_text, papers)

    # Save review
    review_path = os.path.join(output_dir, "review.md")
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(final_review)
    console.print(f"  [green]✓[/green] 综述已保存至 [bold]{review_path}[/bold]")

    # Save BibTeX
    bib_path = os.path.join(output_dir, "references.bib")
    generate_bibtex_file(papers, bib_path)
    console.print(f"  [green]✓[/green] BibTeX 已保存至 [bold]{bib_path}[/bold]")

    # ---- Step 5: Generate Visualizations ----
    console.print("[bold]第5步/共5步:[/bold] 生成可视化图表...")

    # Evolution diagram
    evo_path = os.path.join(output_dir, "evolution.png")
    generate_evolution_diagram(papers, topic, output_path=evo_path)
    console.print(f"  [green]✓[/green] 算法演进图已保存至 [bold]{evo_path}[/bold]")

    # Category distribution
    dist_path = os.path.join(output_dir, "category_distribution.png")
    generate_category_distribution_chart(papers, output_path=dist_path)
    console.print(f"  [green]✓[/green] 类别分布图已保存至 [bold]{dist_path}[/bold]")

    # Poster
    if not args.no_poster:
        poster_path = os.path.join(output_dir, "poster.svg")

        generate_svg_poster(
            papers=papers,
            topic=topic,
            review_summary=review_text,
            evolution_diagram_path=evo_path,
            output_path=poster_path,
            generate_png=True,
        )
        console.print(f"  [green]✓[/green] SVG 海报已保存至 [bold]{poster_path}[/bold]")
        png_path = poster_path.replace(".svg", ".png")
        if os.path.exists(png_path):
            console.print(f"  [green]✓[/green] PNG 海报已保存至 [bold]{png_path}[/bold]")

    # ---- Summary ----
    console.print()
    console.rule("[bold green]生成完成[/bold green]")
    console.print(f"[bold]{output_dir}/ 目录下的输出文件:[/bold]")
    for f in os.listdir(output_dir):
        fpath = os.path.join(output_dir, f)
        size_kb = os.path.getsize(fpath) / 1024
        console.print(f"  • {f} ({size_kb:.1f} KB)")

    console.print()
    console.print("[bold]下一步:[/bold]")
    console.print(f"  1. 查看综述: [code]open {review_path}[/code]")
    console.print(f"  2. 查看演进图: [code]open {evo_path}[/code]")
    if not args.no_poster:
        console.print(f"  3. 查看海报: [code]open {os.path.join(output_dir, 'poster.png')}[/code]")
    console.print()


def main() -> None:
    """Main entry point."""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    try:
        config.ensure_api_keys()
    except ValueError as e:
        console.print(f"[red]配置错误: {e}[/red]")
        console.print(
            "[yellow]提示: 请将 .env.example 复制为 .env 并填入 API Key。[/yellow]"
        )
        sys.exit(1)

    try:
        run_pipeline(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断。[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]错误: {e}[/red]")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
