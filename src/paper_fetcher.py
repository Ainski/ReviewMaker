"""Paper fetching module — searches arXiv and Semantic Scholar APIs."""

import time
import logging
import re
from typing import Optional
from datetime import datetime, timedelta

import arxiv
import requests

from src.models import Paper, Author
from src.query_planner import QueryPlan

logger = logging.getLogger(__name__)


def _request_with_retries(method: str, url: str, max_retries: int = 3, **kwargs) -> requests.Response:
    """HTTP request helper with small exponential backoff for flaky academic APIs."""
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = requests.HTTPError(f"{response.status_code} retryable error")
                time.sleep(0.8 * (attempt + 1))
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise
    raise last_error or requests.RequestException("request failed")

# --- ArXiv Search ---

ARXIV_SORT_MAP = {
    "relevance": arxiv.SortCriterion.Relevance,
    "recency": arxiv.SortCriterion.SubmittedDate,
    "citations": arxiv.SortCriterion.Relevance,  # arXiv doesn't sort by citations
}


def normalize_arxiv_id(arxiv_id: str | None) -> str:
    """Normalize arXiv identifiers so v1/v2 variants can be merged."""
    if not arxiv_id:
        return ""

    normalized = arxiv_id.strip()
    normalized = normalized.removeprefix("ARXIV:").removeprefix("arXiv:")
    normalized = normalized.replace("https://arxiv.org/abs/", "")
    normalized = normalized.replace("http://arxiv.org/abs/", "")
    normalized = normalized.replace("https://arxiv.org/pdf/", "")
    normalized = normalized.replace("http://arxiv.org/pdf/", "")
    normalized = normalized.removesuffix(".pdf")
    normalized = normalized.split("?")[0].split("#")[0].strip("/")
    normalized = re.sub(r"v\d+$", "", normalized)
    return normalized


def _arxiv_result_to_paper(result: arxiv.Result) -> Paper:
    """Convert an arxiv.Result to our Paper dataclass."""
    arxiv_id_clean = normalize_arxiv_id(result.entry_id)

    authors = [Author(name=a.name) for a in result.authors]

    return Paper(
        arxiv_id=arxiv_id_clean,
        title=result.title.strip(),
        abstract=result.summary.strip().replace("\n", " "),
        authors=authors,
        year=result.published.year,
        published_date=result.published.strftime("%Y-%m-%d"),
        arxiv_url=result.entry_id,
        pdf_url=result.pdf_url,
        source="arxiv",
    )


def search_arxiv(
    topic: str,
    max_results: int = 20,
    sort_by: str = "relevance",
    year_range: int = 5,
) -> list[Paper]:
    """
    Search arXiv for papers matching the topic.

    Args:
        topic: Research topic / search query
        max_results: Maximum number of results to return
        sort_by: Sort criterion ("relevance", "recency", "citations")
        year_range: Only include papers from the last N years

    Returns:
        List of Paper objects
    """
    logger.info(f"Searching arXiv for: '{topic}' (max={max_results})")

    sort_criterion = ARXIV_SORT_MAP.get(sort_by, arxiv.SortCriterion.Relevance)

    client = arxiv.Client(
        page_size=min(max_results, 100),
        delay_seconds=1.0,
        num_retries=3,
    )

    search = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=sort_criterion,
    )

    papers = []
    for attempt in range(3):
        try:
            for result in client.results(search):
                # Filter by year range
                cutoff_year = datetime.now().year - year_range
                if result.published.year < cutoff_year:
                    continue
                paper = _arxiv_result_to_paper(result)
                papers.append(paper)

                if len(papers) >= max_results:
                    break
            break
        except Exception as e:
            papers = []
            logger.warning(f"arXiv search encountered an error (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(1.2 * (attempt + 1))

    logger.info(f"arXiv returned {len(papers)} papers")
    return papers


# --- Semantic Scholar Search ---

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"


def _ss_result_to_paper(ss_paper: dict) -> Optional[Paper]:
    """Convert a Semantic Scholar result to our Paper dataclass."""
    try:
        # Try to extract arxiv_id
        arxiv_id = None
        external_ids = ss_paper.get("externalIds", {}) or {}
        arxiv_id = normalize_arxiv_id(external_ids.get("ArXiv"))

        if not arxiv_id:
            # Generate a synthetic ID from Semantic Scholar ID
            arxiv_id = f"ss_{ss_paper.get('paperId', 'unknown')}"

        authors = []
        for a in ss_paper.get("authors", []) or []:
            authors.append(Author(name=a.get("name", "Unknown")))

        year = ss_paper.get("year") or 0
        pub_date = ss_paper.get("publicationDate") or f"{year}-01-01" if year else None
        venue = ""
        publication_venue = ss_paper.get("publicationVenue") or {}
        if isinstance(publication_venue, dict):
            alt_names = publication_venue.get("alternate_names") or []
            venue = publication_venue.get("name") or (alt_names[0] if alt_names else "")
        if not venue and isinstance(ss_paper.get("journal"), dict):
            venue = ss_paper["journal"].get("name") or ""
        venue = venue or ss_paper.get("venue") or ""

        paper = Paper(
            arxiv_id=arxiv_id,
            title=ss_paper.get("title", "Untitled").strip(),
            abstract=ss_paper.get("abstract", "") or "",
            authors=authors,
            year=year,
            published_date=pub_date,
            journal=venue,
            arxiv_url=f"https://arxiv.org/abs/{arxiv_id}" if not arxiv_id.startswith("ss_") else None,
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf" if not arxiv_id.startswith("ss_") else None,
            citation_count=ss_paper.get("citationCount", 0) or 0,
            influential_citation_count=ss_paper.get("influentialCitationCount", 0) or 0,
            source="semantic_scholar",
        )

        # Check for code URLs in external IDs
        if ss_paper.get("externalIds"):
            # Some papers have GitHub links in publicationVenue or other fields
            pass

        return paper
    except Exception as e:
        logger.debug(f"Failed to convert Semantic Scholar paper: {e}")
        return None


def search_semantic_scholar(
    topic: str,
    max_results: int = 20,
    year_range: int = 5,
    api_key: Optional[str] = None,
) -> list[Paper]:
    """
    Search Semantic Scholar for papers matching the topic.

    Args:
        topic: Research topic / search query
        max_results: Maximum number of results
        year_range: Only include papers from the last N years
        api_key: Optional API key for higher rate limits

    Returns:
        List of Paper objects
    """
    logger.info(f"Searching Semantic Scholar for: '{topic}' (max={max_results})")

    headers = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    # Use the search endpoint with fields parameter for rich metadata
    url = f"{SEMANTIC_SCHOLAR_API}/paper/search"
    params = {
        "query": topic,
        "limit": min(max_results, 100),
        "offset": 0,
        "fields": (
            "title,abstract,year,authors,externalIds,"
            "citationCount,influentialCitationCount,"
            "publicationDate,journal,publicationVenue"
        ),
    }

    papers = []
    try:
        response = _request_with_retries("GET", url, params=params, headers=headers, timeout=30)
        data = response.json()

        cutoff_year = datetime.now().year - year_range

        for item in data.get("data", []) or []:
            paper = _ss_result_to_paper(item)
            if paper and (paper.year == 0 or paper.year >= cutoff_year):
                papers.append(paper)

    except requests.exceptions.RequestException as e:
        logger.warning(f"Semantic Scholar search error: {e}")

    logger.info(f"Semantic Scholar returned {len(papers)} papers")
    return papers


def enrich_papers_with_semantic_scholar(
    papers: list[Paper],
    api_key: Optional[str] = None,
) -> list[Paper]:
    """
    Fill citation metadata for arXiv papers via Semantic Scholar's paper batch API.

    Topic search results from arXiv and Semantic Scholar do not always overlap.
    Looking up exact arXiv IDs is more reliable for citation counts.
    """
    arxiv_papers = [
        p for p in papers
        if p.arxiv_id and not p.arxiv_id.startswith("ss_")
    ]
    if not arxiv_papers:
        return papers

    headers = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    url = f"{SEMANTIC_SCHOLAR_API}/paper/batch"
    fields = (
        "title,abstract,year,authors,externalIds,"
        "citationCount,influentialCitationCount,"
        "publicationDate,journal,publicationVenue"
    )

    by_arxiv_id = {normalize_arxiv_id(p.arxiv_id): p for p in arxiv_papers}
    ids = [f"ARXIV:{arxiv_id}" for arxiv_id in by_arxiv_id]

    enriched = 0
    try:
        for start in range(0, len(ids), 100):
            batch_ids = ids[start:start + 100]
            response = _request_with_retries(
                "POST",
                url,
                params={"fields": fields},
                json={"ids": batch_ids},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            for item in response.json() or []:
                if not item:
                    continue
                external_ids = item.get("externalIds", {}) or {}
                arxiv_id = normalize_arxiv_id(external_ids.get("ArXiv"))
                paper = by_arxiv_id.get(arxiv_id)
                if not paper:
                    continue

                citation_count = item.get("citationCount", 0) or 0
                influential_count = item.get("influentialCitationCount", 0) or 0
                if citation_count > paper.citation_count:
                    paper.citation_count = citation_count
                if influential_count > paper.influential_citation_count:
                    paper.influential_citation_count = influential_count
                if not paper.abstract and item.get("abstract"):
                    paper.abstract = item["abstract"]
                venue = ""
                publication_venue = item.get("publicationVenue") or {}
                if isinstance(publication_venue, dict):
                    alt_names = publication_venue.get("alternate_names") or []
                    venue = publication_venue.get("name") or (alt_names[0] if alt_names else "")
                if not venue and isinstance(item.get("journal"), dict):
                    venue = item["journal"].get("name") or ""
                venue = venue or item.get("venue") or ""
                if venue and not paper.journal:
                    paper.journal = venue
                enriched += 1
    except requests.exceptions.RequestException as e:
        logger.warning(f"Semantic Scholar batch enrichment error: {e}")

    logger.info(f"Semantic Scholar enriched citation metadata for {enriched}/{len(arxiv_papers)} arXiv papers")
    return papers


# --- Unified Search ---

def fetch_papers(
    topic: str,
    max_results: int = 20,
    year_range: int = 5,
    sort_by: str = "relevance",
    include_ss: bool = True,
    api_key: Optional[str] = None,
) -> list[Paper]:
    """
    Fetch papers from arXiv and optionally Semantic Scholar, then merge + deduplicate.

    Args:
        topic: Research topic / search query
        max_results: Maximum number of papers to return
        year_range: Look back N years
        sort_by: Sort criterion for arXiv
        include_ss: Whether to also search Semantic Scholar
        api_key: Semantic Scholar API key

    Returns:
        Deduplicated list of Paper objects
    """
    all_papers: dict[str, Paper] = {}

    # Search arXiv first (primary source)
    arxiv_papers = search_arxiv(
        topic=topic,
        max_results=max_results,
        sort_by=sort_by,
        year_range=year_range,
    )
    for p in arxiv_papers:
        key = normalize_arxiv_id(p.arxiv_id)
        all_papers[key] = p

    # Search Semantic Scholar (supplement)
    if include_ss:
        enrich_papers_with_semantic_scholar(
            list(all_papers.values()),
            api_key=api_key,
        )

        time.sleep(0.5)  # Be polite to APIs
        ss_papers = search_semantic_scholar(
            topic=topic,
            max_results=max_results,
            year_range=year_range,
            api_key=api_key,
        )
        for p in ss_papers:
            key = normalize_arxiv_id(p.arxiv_id)
            if key not in all_papers:
                all_papers[key] = p
            else:
                # Enrich existing paper with SS metadata
                existing = all_papers[key]
                if p.citation_count > existing.citation_count:
                    existing.citation_count = p.citation_count
                if p.influential_citation_count > existing.influential_citation_count:
                    existing.influential_citation_count = p.influential_citation_count

    papers = list(all_papers.values())
    logger.info(f"Total unique papers after merge: {len(papers)}")
    return papers


def fetch_papers_for_queries(
    plan: QueryPlan,
    max_results: int = 20,
    year_range: int = 5,
    sort_by: str = "relevance",
    include_ss: bool = True,
    api_key: Optional[str] = None,
) -> tuple[list[Paper], list[str], dict]:
    """
    Fetch papers using multiple planned queries and return warnings/statistics.

    This is more robust than a single raw query, especially for Chinese
    requests or focused topics with several key techniques.
    """
    queries = plan.normalized_queries(max_queries=6)
    all_papers: dict[str, Paper] = {}
    warnings: list[str] = []
    query_stats = {"queries": [], "requested": max_results}
    # Fetch more than the final target, then let ranker/LLM reranker improve precision.
    per_query_limit = max(12, min(50, max_results * 2))

    for query in queries:
        before = len(all_papers)
        arxiv_count = 0
        ss_count = 0

        arxiv_papers = search_arxiv(
            topic=query,
            max_results=per_query_limit,
            sort_by=sort_by,
            year_range=year_range,
        )
        arxiv_count = len(arxiv_papers)
        for p in arxiv_papers:
            key = normalize_arxiv_id(p.arxiv_id) or p.title.lower()
            all_papers.setdefault(key, p)

        if include_ss:
            # Exact citation enrichment for arXiv hits is useful even if topic
            # search later gets rate-limited.
            enrich_papers_with_semantic_scholar(
                list(all_papers.values()),
                api_key=api_key,
            )
            time.sleep(0.3)
            ss_papers = search_semantic_scholar(
                topic=query,
                max_results=per_query_limit,
                year_range=year_range,
                api_key=api_key,
            )
            ss_count = len(ss_papers)
            for p in ss_papers:
                key = normalize_arxiv_id(p.arxiv_id) or p.title.lower()
                if key not in all_papers:
                    all_papers[key] = p
                else:
                    existing = all_papers[key]
                    if p.citation_count > existing.citation_count:
                        existing.citation_count = p.citation_count
                    if p.influential_citation_count > existing.influential_citation_count:
                        existing.influential_citation_count = p.influential_citation_count

        added = len(all_papers) - before
        query_stats["queries"].append({
            "query": query,
            "arxiv": arxiv_count,
            "semantic_scholar": ss_count,
            "new_unique": added,
        })

    papers = list(all_papers.values())
    if not papers:
        warnings.append("多个检索 query 均未返回论文，建议扩大年份范围或换用更宽泛的主题。")
    elif len(papers) < max_results:
        warnings.append(f"仅检索到 {len(papers)} 篇候选论文，少于请求的 {max_results} 篇。")

    logger.info(
        "Multi-query fetch returned %d unique papers from %d queries",
        len(papers), len(queries),
    )
    return papers, warnings, query_stats
