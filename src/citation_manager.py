"""Citation manager — generates BibTeX and validates in-text citations (Chinese labels)."""

import logging
import re
from typing import Optional

from src.models import Paper

logger = logging.getLogger(__name__)


def generate_bibtex_entry(paper: Paper, index: int) -> str:
    """Generate a BibTeX entry for a single paper."""
    first_author_last = paper.first_author.lower().replace(" ", "_").replace(".", "")
    label = f"ref{index}_{first_author_last}{paper.year}"

    authors = " and ".join(a.name for a in paper.authors) if paper.authors else "{Unknown}"

    entry_type = "article" if paper.journal else "misc"

    B = "{"
    E = "}"

    lines = [f"@{entry_type}{B}{label},"]
    lines.append(f"  title = {B}{paper.title}{E},")
    lines.append(f"  author = {B}{authors}{E},")
    lines.append(f"  year = {B}{paper.year}{E},")

    if paper.journal:
        lines.append(f"  journal = {B}{paper.journal}{E},")

    if paper.arxiv_id and not paper.arxiv_id.startswith("ss_"):
        lines.append(f"  archiveprefix = {B}arXiv{E},")
        lines.append(f"  eprint = {B}{paper.arxiv_id}{E},")

    if paper.arxiv_url:
        lines.append(f"  url = {B}{paper.arxiv_url}{E},")

    if paper.arxiv_id.startswith("ss_"):
        ss_id = paper.arxiv_id.replace("ss_", "")
        lines.append(f"  note = {B}Semantic Scholar ID: {ss_id}{E},")

    lines.append("}")

    return "\n".join(lines)


def generate_bibtex_file(papers: list[Paper], output_path: str) -> str:
    """Generate a complete .bib file for all papers."""
    entries = []
    for i, paper in enumerate(papers, start=1):
        entries.append(generate_bibtex_entry(paper, i))

    bibtex_content = "\n\n".join(entries) + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(bibtex_content)

    logger.info(f"BibTeX 文件已写入 {output_path} ({len(entries)} 条)")
    return bibtex_content


def generate_reference_list(papers: list[Paper]) -> str:
    """
    Generate a formatted reference list in Markdown (Chinese labels).
    """
    lines = ["\n## 参考文献\n"]
    for i, paper in enumerate(papers, start=1):
        authors = ", ".join(a.name for a in paper.authors[:3])
        if len(paper.authors) > 3:
            authors += " 等"

        ref_line = f"- [{i}] {authors}. **{paper.title}**."
        if paper.journal:
            ref_line += f" *{paper.journal}*."
        ref_line += f" ({paper.year})."

        if paper.arxiv_url and not paper.arxiv_id.startswith("ss_"):
            ref_line += f" arXiv: [{paper.arxiv_id}]({paper.arxiv_url})."

        if paper.has_code and paper.code_urls:
            ref_line += f" [[代码]]({paper.code_urls[0]})"

        lines.append(ref_line)

    return "\n".join(lines)


def validate_citations(review_text: str, num_papers: int) -> dict:
    """Validate that all in-text citations reference valid paper indices."""
    citation_pattern = re.findall(r"\[([^\]]+)\]", review_text)

    all_cited = set()
    for cite_group in citation_pattern:
        parts = cite_group.split(",")
        for part in parts:
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    for n in range(int(start), int(end) + 1):
                        all_cited.add(n)
                except ValueError:
                    continue
            else:
                try:
                    all_cited.add(int(part))
                except ValueError:
                    continue

    valid_range = set(range(1, num_papers + 1))
    valid_citations = all_cited & valid_range
    invalid_citations = all_cited - valid_range
    missing_citations = valid_range - all_cited

    logger.info(
        f"引用验证: {len(valid_citations)}/{num_papers} 篇论文被引用, "
        f"{len(missing_citations)} 篇未引用, {len(invalid_citations)} 个无效引用"
    )

    return {
        "valid_citations": valid_citations,
        "missing_citations": missing_citations,
        "invalid_citations": invalid_citations,
    }


def append_references_to_review(
    review_text: str,
    papers: list[Paper],
) -> str:
    """Append a formatted reference list to the review text."""
    ref_list = generate_reference_list(papers)
    return review_text + "\n" + ref_list
