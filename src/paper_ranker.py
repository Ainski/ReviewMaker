"""Paper ranking module — scores and filters papers by relevance and code availability."""

import logging
import math
import re
from collections import Counter
from typing import Optional

from src.models import Paper

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    """Simple tokenizer: lowercase, split, remove short words."""
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {w for w in words if len(w) > 2}


def _keyword_relevance(paper: Paper, topic_keywords: set[str]) -> float:
    """
    Compute keyword-based relevance between paper and topic.

    Scores title matches higher than abstract matches.
    """
    title_tokens = _tokenize(paper.title)
    abstract_tokens = _tokenize(paper.abstract)

    # Title match (weighted 2x)
    title_match = len(title_tokens & topic_keywords) / max(len(topic_keywords), 1)

    # Abstract match
    abstract_match = len(abstract_tokens & topic_keywords) / max(len(topic_keywords), 1)

    # Combined score
    score = (title_match * 0.6 + abstract_match * 0.4)
    return min(score * 1.5, 1.0)  # Scale up but cap at 1.0


def _normalize_citations(citation_count: int, all_counts: list[int]) -> float:
    """Normalize citation count to [0, 1] using log scale."""
    if not all_counts or max(all_counts) == 0:
        return 0.0
    max_log = math.log(max(all_counts) + 1)
    if max_log == 0:
        return 0.0
    return math.log(citation_count + 1) / max_log


def _recency_score(year: int, current_year: int, year_range: int) -> float:
    """Score papers higher if they are more recent."""
    if year == 0:
        return 0.5
    age = current_year - year
    if age <= 0:
        return 1.0
    if age >= year_range:
        return 0.0
    return 1.0 - (age / year_range)


def rank_papers(
    papers: list[Paper],
    topic: str,
    year_range: int = 5,
    current_year: Optional[int] = None,
) -> list[Paper]:
    """
    Rank papers by composite score:
      score = relevance * 0.40 + has_code * 0.30 + citations_norm * 0.15 + recency * 0.15

    Args:
        papers: List of papers to rank
        topic: Original search topic for relevance computation
        year_range: Year range for recency scoring
        current_year: Current year (defaults to system year)

    Returns:
        Sorted list of Paper objects (highest score first), with rank_score populated
    """
    if not papers:
        return papers

    import datetime
    if current_year is None:
        current_year = datetime.datetime.now().year

    topic_keywords = _tokenize(topic)
    all_citations = [p.citation_count for p in papers]

    for paper in papers:
        # 1. Relevance score (40%)
        relevance = _keyword_relevance(paper, topic_keywords)
        paper.relevance_score = relevance

        # 2. Code availability score (30%)
        code_score = 1.0 if paper.has_code else 0.0

        # 3. Citation score (15%)
        citation_score = _normalize_citations(paper.citation_count, all_citations)

        # 4. Recency score (15%)
        recency = _recency_score(paper.year, current_year, year_range)

        # Composite rank score
        paper.rank_score = (
            relevance * 0.40
            + code_score * 0.30
            + citation_score * 0.15
            + recency * 0.15
        )

        logger.debug(
            f"  {paper.short_title[:60]}: "
            f"rel={relevance:.2f} code={code_score:.1f} "
            f"cit={citation_score:.2f} rec={recency:.2f} "
            f"→ rank={paper.rank_score:.3f}"
        )

    # Sort by rank score descending
    papers.sort(key=lambda p: p.rank_score, reverse=True)
    return papers


def filter_papers(
    papers: list[Paper],
    max_papers: int = 20,
    min_relevance: float = 0.05,
) -> list[Paper]:
    """
    Filter papers: remove low-relevance, cap at max_papers.

    Args:
        papers: Ranked list of papers
        max_papers: Maximum number to keep
        min_relevance: Minimum relevance score threshold

    Returns:
        Filtered list of Paper objects
    """
    # Filter by minimum relevance
    filtered = [p for p in papers if p.relevance_score >= min_relevance]

    # Cap at max_papers
    filtered = filtered[:max_papers]

    # Log quality check: topic accuracy estimation
    if filtered:
        high_rel = sum(1 for p in filtered if p.relevance_score > 0.2)
        topic_accuracy = high_rel / len(filtered)
        logger.info(
            f"Topic accuracy estimate: {topic_accuracy:.1%} "
            f"({high_rel}/{len(filtered)} papers highly relevant)"
        )

    logger.info(f"Filtered: {len(filtered)} papers (from {len(papers)})")
    return filtered
