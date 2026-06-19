"""Paper ranking module — scores and filters papers by relevance and code availability."""

import logging
import math
import re
import json
from collections import Counter
from typing import Optional

from openai import OpenAI

from src.models import Paper

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    """Tokenize English terms and CJK phrases into a small keyword set."""
    text = (text or "").lower()
    tokens = {w for w in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-]+", text) if len(w) > 2}

    # CJK support: keep contiguous phrases and 2-4 char shingles.
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.add(phrase)
        for n in (2, 3, 4):
            if len(phrase) >= n:
                tokens.update(phrase[i:i+n] for i in range(len(phrase) - n + 1))
    return tokens


def _keyword_relevance(
    paper: Paper,
    topic_keywords: set[str],
    focus_keywords: set[str] | None = None,
) -> float:
    """
    Compute keyword-based relevance between paper and topic.

    Scores title matches higher than abstract matches.
    """
    title_tokens = _tokenize(paper.title)
    abstract_tokens = _tokenize(paper.abstract)
    focus_keywords = focus_keywords or set()

    # Title match (weighted 2x)
    title_match = len(title_tokens & topic_keywords) / max(len(topic_keywords), 1)

    # Abstract match
    abstract_match = len(abstract_tokens & topic_keywords) / max(len(topic_keywords), 1)

    focus_pool = title_tokens | abstract_tokens
    focus_match = len(focus_pool & focus_keywords) / max(len(focus_keywords), 1) if focus_keywords else 0.0

    # Combined score
    score = (title_match * 0.45 + abstract_match * 0.35 + focus_match * 0.20)
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


TOP_VENUE_KEYWORDS = {
    "neurips": 1.0,
    "nips": 1.0,
    "icml": 1.0,
    "iclr": 1.0,
    "cvpr": 1.0,
    "iccv": 1.0,
    "eccv": 0.95,
    "acl": 1.0,
    "emnlp": 0.95,
    "naacl": 0.9,
    "sigir": 0.95,
    "kdd": 0.95,
    "www": 0.9,
    "the web conference": 0.9,
    "aaai": 0.9,
    "ijcai": 0.9,
    "siggraph": 1.0,
    "usenix": 0.95,
    "osdi": 1.0,
    "sosp": 1.0,
    "pldi": 0.95,
    "sigmod": 0.95,
    "vldb": 0.95,
    "nature": 1.0,
    "science": 1.0,
    "cell": 0.95,
    "pnas": 0.9,
    "jmlr": 0.9,
    "tpami": 0.95,
    "tacl": 0.9,
}


def _venue_score(venue: str | None) -> float:
    """Heuristic venue quality score based on common top CS/AI venues."""
    if not venue:
        return 0.0
    normalized = _normalize_venue(venue)
    for keyword, score in TOP_VENUE_KEYWORDS.items():
        if keyword in normalized:
            return score
    return 0.35


def _normalize_venue(venue: str) -> str:
    venue = venue.lower()
    venue = venue.replace("&", " and ")
    venue = re.sub(r"[^a-z0-9 ]+", " ", venue)
    return re.sub(r"\s+", " ", venue).strip()


def rank_papers(
    papers: list[Paper],
    topic: str,
    year_range: int = 5,
    current_year: Optional[int] = None,
    focus_keywords: Optional[list[str]] = None,
    search_queries: Optional[list[str]] = None,
) -> list[Paper]:
    """
    Rank papers by composite score:
      score = relevance * 0.45 + citations_norm * 0.20 + venue * 0.15 + recency * 0.10 + has_code * 0.10

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

    expanded_topic = " ".join([topic, *(search_queries or [])])
    topic_keywords = _tokenize(expanded_topic)
    focus_token_set = _tokenize(" ".join(focus_keywords or []))
    all_citations = [p.citation_count for p in papers]

    for paper in papers:
        # 1. Relevance score (40%)
        relevance = _keyword_relevance(paper, topic_keywords, focus_token_set)
        paper.relevance_score = relevance

        # 2. Code availability score
        code_score = 1.0 if paper.has_code else 0.0

        # 3. Citation score
        citation_score = _normalize_citations(paper.citation_count, all_citations)

        # 4. Venue score
        venue = _venue_score(paper.journal)

        # 5. Recency score
        recency = _recency_score(paper.year, current_year, year_range)

        # Composite rank score
        paper.rank_score = (
            relevance * 0.45
            + citation_score * 0.20
            + venue * 0.15
            + recency * 0.10
            + code_score * 0.10
        )

        logger.debug(
            f"  {paper.short_title[:60]}: "
            f"rel={relevance:.2f} code={code_score:.1f} "
            f"cit={citation_score:.2f} venue={venue:.2f} rec={recency:.2f} "
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


def rerank_papers_with_llm(
    papers: list[Paper],
    topic: str,
    api_key: str,
    raw_request: str = "",
    focus_keywords: Optional[list[str]] = None,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
    candidate_limit: int = 50,
) -> list[Paper]:
    """
    Use an LLM as a second-stage relevance judge for top candidates.

    The first-stage ranker is fast and recall-oriented. This step improves
    precision by asking the model whether each candidate truly matches the
    user's research intent.
    """
    if not papers or not api_key:
        return papers

    candidates = papers[:candidate_limit]
    tail = papers[candidate_limit:]

    paper_blocks = []
    for i, paper in enumerate(candidates, start=1):
        paper_blocks.append(
            f"[{i}] 标题: {paper.title}\n"
            f"年份: {paper.year}\n"
            f"摘要: {(paper.abstract or '')[:700]}"
        )

    prompt = f"""你是科研文献检索相关性评估器。请判断每篇候选论文与用户综述需求的相关性。

用户原始需求：{raw_request or topic}
提取主题：{topic}
关注重点：{"、".join(focus_keywords or []) or "未额外指定"}

请仅返回 JSON 数组，不要输出其他文字。每个对象包含：
- index: 论文编号
- relevance: 0 到 1 的相关性分数
- decision: "strong"、"medium"、"weak"、"unrelated" 之一
- reason: 一句中文理由

判断标准：
- strong: 论文核心任务/方法与主题直接一致，适合进入综述主体。
- medium: 与主题有明显关联，可作为背景、应用或补充。
- weak: 只有关键词相似，主题贡献有限。
- unrelated: 与用户需求基本不相关。

候选论文：
{chr(10).join(paper_blocks)}"""

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            logger.warning("LLM rerank response did not contain JSON")
            return papers
        judgments = json.loads(text[start:end])
    except Exception as e:
        logger.warning(f"LLM rerank failed, using keyword rank only: {e}")
        return papers

    decision_weight = {
        "strong": 1.0,
        "medium": 0.75,
        "weak": 0.35,
        "unrelated": 0.0,
    }
    by_index = {}
    for item in judgments:
        try:
            by_index[int(item.get("index")) - 1] = item
        except (TypeError, ValueError):
            continue

    reranked = []
    for idx, paper in enumerate(candidates):
        judgment = by_index.get(idx, {})
        relevance = judgment.get("relevance")
        decision = str(judgment.get("decision", "")).lower()
        try:
            llm_relevance = max(0.0, min(float(relevance), 1.0))
        except (TypeError, ValueError):
            llm_relevance = paper.relevance_score

        gate = decision_weight.get(decision, 0.5)
        paper.relevance_score = max(paper.relevance_score * 0.35 + llm_relevance * 0.65, gate * 0.4)
        paper.rank_score = paper.rank_score * 0.45 + paper.relevance_score * 0.55
        reranked.append(paper)

    reranked.sort(key=lambda p: p.rank_score, reverse=True)
    logger.info("LLM reranked %d candidate papers", len(reranked))
    return reranked + tail
