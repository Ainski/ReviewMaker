"""Code finder module — discovers GitHub repositories associated with papers."""

import logging
import time
import re
from typing import Optional
from urllib.parse import quote_plus

import requests

from src.models import Paper

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
PAPERS_WITH_CODE_API = "https://paperswithcode.com/api/v1"


def search_github_repos(
    query: str,
    github_token: Optional[str] = None,
    max_results: int = 5,
) -> list[dict]:
    """
    Search GitHub for repositories matching a query.

    Args:
        query: Search query (paper title or arxiv ID)
        github_token: GitHub personal access token
        max_results: Maximum number of repos to return

    Returns:
        List of repo dicts with keys: full_name, html_url, description, stars, language
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    # Clean query for GitHub search
    clean_query = re.sub(r"[^\w\s-]", "", query)[:256]
    url = f"{GITHUB_API}/search/repositories"
    params = {
        "q": clean_query,
        "sort": "stars",
        "order": "desc",
        "per_page": max_results,
    }

    repos = []
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 403:
            logger.warning("GitHub API rate limit exceeded. Set GITHUB_TOKEN for higher limits.")
            return repos
        response.raise_for_status()
        data = response.json()

        for item in data.get("items", []) or []:
            repos.append({
                "full_name": item.get("full_name", ""),
                "html_url": item.get("html_url", ""),
                "description": item.get("description", "") or "",
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language", ""),
            })
    except requests.exceptions.RequestException as e:
        logger.warning(f"GitHub search error: {e}")

    return repos


def _score_repo_relevance(repo: dict, paper: Paper) -> float:
    """Score how relevant a GitHub repo is to a paper."""
    score = 0.0
    desc_lower = repo["description"].lower()
    title_lower = paper.title.lower()

    # Check if paper title keywords appear in repo description
    title_keywords = [w for w in title_lower.split() if len(w) > 3]
    matched = sum(1 for kw in title_keywords if kw in desc_lower)
    if len(title_keywords) > 0:
        score += (matched / len(title_keywords)) * 0.5

    # Check for arxiv ID in description or name
    if paper.arxiv_id.lower() in desc_lower or paper.arxiv_id.lower() in repo["full_name"].lower():
        score += 0.3

    # Stars bonus
    if repo["stars"] > 100:
        score += 0.1
    if repo["stars"] > 1000:
        score += 0.1

    return min(score, 1.0)


def find_code_for_paper(
    paper: Paper,
    github_token: Optional[str] = None,
) -> list[str]:
    """
    Find GitHub repositories associated with a specific paper.

    Searches by:
    1. Paper title keywords
    2. ArXiv ID

    Args:
        paper: Paper to find code for
        github_token: GitHub personal access token

    Returns:
        List of GitHub repo URLs
    """
    code_urls = []

    # Search by paper title (use first 100 chars as query)
    title_query = paper.title[:100]
    repos = search_github_repos(title_query, github_token=github_token, max_results=5)

    # Also search by arxiv ID
    if paper.arxiv_id and not paper.arxiv_id.startswith("ss_"):
        time.sleep(0.3)  # Rate limit
        arxiv_repos = search_github_repos(
            paper.arxiv_id, github_token=github_token, max_results=3
        )
        repos.extend(arxiv_repos)

    # Deduplicate and score
    seen_urls = set()
    scored_repos = []
    for repo in repos:
        if repo["html_url"] not in seen_urls:
            seen_urls.add(repo["html_url"])
            relevance = _score_repo_relevance(repo, paper)
            scored_repos.append((relevance, repo))

    # Sort by relevance (highest first)
    scored_repos.sort(key=lambda x: x[0], reverse=True)

    # Filter: only keep repos with relevance > 0.1
    for rel, repo in scored_repos:
        if rel > 0.1:
            code_urls.append(repo["html_url"])
            logger.debug(f"  Found code: {repo['html_url']} (relevance={rel:.2f})")

    return code_urls


def find_code_for_papers(
    papers: list[Paper],
    github_token: Optional[str] = None,
) -> list[Paper]:
    """
    Find GitHub repositories for a list of papers.

    Updates each Paper's has_code and code_urls fields in-place.

    Args:
        papers: List of Paper objects to search code for
        github_token: GitHub personal access token

    Returns:
        The updated list of Paper objects (same objects, mutated in-place)
    """
    logger.info(f"Searching GitHub code for {len(papers)} papers...")

    for i, paper in enumerate(papers):
        logger.info(f"  [{i+1}/{len(papers)}] Searching code for: {paper.short_title}")

        code_urls = find_code_for_paper(paper, github_token=github_token)

        if code_urls:
            paper.has_code = True
            paper.code_urls = code_urls
            logger.info(f"    Found {len(code_urls)} repo(s)")
        else:
            logger.debug(f"    No code found")

        # Rate limiting between papers
        if i < len(papers) - 1:
            time.sleep(0.5)

    papers_with_code = sum(1 for p in papers if p.has_code)
    logger.info(f"Code found for {papers_with_code}/{len(papers)} papers")

    return papers
