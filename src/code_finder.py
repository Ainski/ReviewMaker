"""Code finder module — discovers GitHub repositories associated with papers."""

import logging
import time
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import unquote

import requests
import fitz  # PyMuPDF
from openai import OpenAI

from src.models import Paper
from src.rag_engine import download_pdf

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
PAPERS_WITH_CODE_API = "https://paperswithcode.com/api/v1"


def _request_with_retries(method: str, url: str, max_retries: int = 3, **kwargs) -> requests.Response:
    """HTTP request helper with small backoff for GitHub/Papers with Code."""
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


def _normalize_text(text: str) -> str:
    """Normalize text for loose title/repo matching."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _title_queries(title: str) -> list[str]:
    """Build several code-search queries from a paper title."""
    title = (title or "").strip()
    if not title:
        return []

    queries = [title[:100]]
    short_title = re.split(r"[:：\-–—]", title, maxsplit=1)[0].strip()
    if short_title and short_title != title:
        queries.append(short_title[:80])

    # Distinctive method names such as SageAttention, AlayaDB, FlashAttention.
    method_names = re.findall(r"\b[A-Z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b", title)
    queries.extend(method_names[:3])

    seen = set()
    deduped = []
    for q in queries:
        key = q.lower()
        if q and key not in seen:
            seen.add(key)
            deduped.append(q)
    return deduped


def _clean_url(url: str) -> str:
    """Clean URLs extracted from PDF text."""
    url = unquote(url.strip())
    url = re.sub(r"\s+", "", url)
    url = url.rstrip(").,;]'\"}>")
    url = url.replace("\\", "")
    return url


def _url_text_variants(text: str) -> list[str]:
    """Build URL-oriented text variants without deleting meaningful hyphens."""
    if not text:
        return []

    variants = [text]
    # Conservative line unwrap: only join a line break when the left side
    # already contains a code hosting domain and the next line looks URL-like.
    lines = text.splitlines()
    repaired_lines = []
    i = 0
    while i < len(lines):
        current = lines[i].rstrip()
        while (
            i + 1 < len(lines)
            and re.search(r"(github\.com|huggingface\.co|gitlab\.com|bitbucket\.org)/", current)
            and re.match(r"^[A-Za-z0-9_.\-/]+", lines[i + 1].strip())
            and current.endswith(("/", "-", ".", "_"))
            and not re.search(r"[)\],;。]$", current)
        ):
            next_part = lines[i + 1].strip().split()[0]
            current += next_part
            i += 1
        repaired_lines.append(current)
        i += 1
    variants.append("\n".join(repaired_lines))

    deduped = []
    for variant in variants:
        if variant not in deduped:
            deduped.append(variant)
    return deduped


def extract_code_urls_from_text(text: str) -> list[str]:
    """Extract likely code/project URLs from paper full text."""
    if not text:
        return []

    patterns = [
        r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+",
        r"https?://huggingface\.co/[A-Za-z0-9_.\-/]+",
        r"https?://gitlab\.com/[A-Za-z0-9_.\-/]+",
        r"https?://bitbucket\.org/[A-Za-z0-9_.\-/]+",
    ]
    urls: list[str] = []
    for variant in _url_text_variants(text):
        for pattern in patterns:
            for match in re.findall(pattern, variant):
                url = _clean_url(match)
                if url and url not in urls:
                    urls.append(url)
    return _drop_prefix_urls(urls)


def _drop_prefix_urls(urls: list[str]) -> list[str]:
    """Drop shorter broken URLs when a longer repaired URL contains them."""
    result = []
    for url in urls:
        if any(other != url and other.startswith(url) and len(other) > len(url) for other in urls):
            continue
        result.append(url)
    return result


def _extract_raw_text_from_pdf(pdf_path: str) -> str:
    """Extract raw PDF text without generic hyphenation cleanup."""
    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def _url_is_confirmed_missing(url: str) -> bool:
    """Return True only when the remote service clearly says the URL is missing."""
    try:
        response = _request_with_retries("HEAD", url, allow_redirects=True, timeout=8, max_retries=2)
        if response.status_code in {403, 405}:
            response = _request_with_retries("GET", url, allow_redirects=True, timeout=8, stream=True, max_retries=2)
        return response.status_code == 404
    except requests.exceptions.RequestException:
        # Network instability should not be treated as proof that code is absent.
        return False


def _is_supported_code_url(url: str) -> bool:
    """Allow only common code/model hosting URLs."""
    return bool(re.match(
        r"^https?://(github\.com|huggingface\.co|gitlab\.com|bitbucket\.org)/[A-Za-z0-9_.\-/]+$",
        url or "",
    ))


def _url_title_hint_score(url: str, paper: Paper) -> float:
    """Lightweight plausibility score for an LLM-suggested code URL."""
    url_norm = _normalize_text(url)
    title_norm = _normalize_text(paper.title)
    title_keywords = [w for w in title_norm.split() if len(w) > 3]
    if not title_keywords:
        return 0.0

    matched = sum(1 for kw in title_keywords if kw in url_norm)
    score = matched / len(title_keywords)

    method_names = [
        _normalize_text(m)
        for m in re.findall(r"\b[A-Z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b", paper.title)
    ]
    if any(name and name in url_norm for name in method_names):
        score += 0.45

    short_title = _normalize_text(re.split(r"[:：\-–—]", paper.title, maxsplit=1)[0])
    if short_title and short_title in url_norm:
        score += 0.35

    return min(score, 1.0)


def _validate_suggested_code_url(url: str, paper: Paper) -> bool:
    """Validate a DeepSeek-suggested URL before it can compete with candidates."""
    url = _clean_url(url)
    if not _is_supported_code_url(url):
        return False
    if _url_is_confirmed_missing(url):
        return False
    return _url_title_hint_score(url, paper) >= 0.18


def filter_missing_urls(urls: list[str]) -> list[str]:
    """Filter URLs that are confirmed 404 while preserving order."""
    filtered = []
    for url in urls:
        if url in filtered:
            continue
        if _url_is_confirmed_missing(url):
            logger.debug(f"Discarding confirmed missing code URL: {url}")
            continue
        filtered.append(url)
    return filtered


def find_code_urls_in_pdf(paper: Paper, max_urls: int = 5) -> list[str]:
    """Download PDF and scan full text for repository links."""
    if not paper.arxiv_id or paper.arxiv_id.startswith("ss_"):
        return []
    try:
        pdf_path = download_pdf(paper)
        if not pdf_path:
            return []
        full_text = _extract_raw_text_from_pdf(pdf_path)
    except Exception as e:
        logger.debug(f"PDF code link extraction failed for {paper.arxiv_id}: {e}")
        return []
    return filter_missing_urls(extract_code_urls_from_text(full_text))[:max_urls]


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
        response = _request_with_retries("GET", url, params=params, headers=headers, timeout=15)
        if response.status_code == 403:
            logger.warning("GitHub API rate limit exceeded. Set GITHUB_TOKEN for higher limits.")
            return repos
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
    desc_norm = _normalize_text(repo.get("description", ""))
    name_norm = _normalize_text(repo.get("full_name", ""))
    repo_text = f"{name_norm} {desc_norm}"
    title_norm = _normalize_text(paper.title)
    short_title_norm = _normalize_text(re.split(r"[:：\-–—]", paper.title, maxsplit=1)[0])

    # Check if paper title keywords appear in repo description
    title_keywords = [w for w in title_norm.split() if len(w) > 3]
    matched = sum(1 for kw in title_keywords if kw in repo_text)
    if len(title_keywords) > 0:
        score += (matched / len(title_keywords)) * 0.45

    if short_title_norm and short_title_norm in repo_text:
        score += 0.35

    method_names = [_normalize_text(m) for m in re.findall(r"\b[A-Z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b", paper.title)]
    if any(m and m in repo_text for m in method_names):
        score += 0.35

    # Check for arxiv ID in description or name
    if paper.arxiv_id and paper.arxiv_id.lower() in repo_text:
        score += 0.3

    # Stars bonus
    if repo["stars"] > 100:
        score += 0.1
    if repo["stars"] > 1000:
        score += 0.1

    return min(score, 1.0)


def search_paperswithcode_repos(
    paper: Paper,
    max_results: int = 5,
) -> list[str]:
    """Search Papers with Code for official repository URLs."""
    urls: list[str] = []

    def add_url(url: str | None):
        if url and url not in urls:
            urls.append(url)

    try:
        params = {"q": paper.title, "page_size": max_results}
        response = _request_with_retries("GET", f"{PAPERS_WITH_CODE_API}/papers/", params=params, timeout=15)
        results = response.json().get("results", []) or []
    except requests.exceptions.RequestException as e:
        logger.debug(f"Papers with Code search error: {e}")
        return urls

    paper_title_norm = _normalize_text(paper.title)
    for item in results:
        candidate_title = _normalize_text(item.get("title", ""))
        arxiv_match = paper.arxiv_id and str(item.get("arxiv_id", "")).lower() == paper.arxiv_id.lower()
        title_match = candidate_title and (
            candidate_title == paper_title_norm
            or candidate_title in paper_title_norm
            or paper_title_norm in candidate_title
        )
        if not (arxiv_match or title_match):
            continue

        paper_id = item.get("id")
        if not paper_id:
            continue
        try:
            repo_response = _request_with_retries(
                "GET",
                f"{PAPERS_WITH_CODE_API}/papers/{paper_id}/repositories/",
                params={"page_size": max_results},
                timeout=15,
            )
            repos = repo_response.json().get("results", []) or []
            for repo in repos:
                add_url(repo.get("url") or repo.get("repository_url"))
        except requests.exceptions.RequestException as e:
            logger.debug(f"Papers with Code repositories error: {e}")

    return urls[:max_results]


def _add_candidate(candidates: list[dict], url: str, source: str, score: float, evidence: str = ""):
    """Add a deduplicated code candidate."""
    if not url:
        return
    url = _clean_url(url)
    if not url or any(c["url"] == url for c in candidates):
        return
    candidates.append({
        "url": url,
        "source": source,
        "score": score,
        "evidence": evidence[:500],
    })


def select_best_code_url_with_llm(
    paper: Paper,
    candidates: list[dict],
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> Optional[str]:
    """Let DeepSeek choose among found candidates and one validated suggested URL."""
    if not candidates and not api_key:
        return None
    candidates = sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)[:8]
    if not api_key:
        return candidates[0]["url"]

    candidate_text = "\n".join(
        f"[{i}] url: {c['url']}\nsource: {c['source']}\nscore: {c.get('score', 0):.2f}\nevidence: {c.get('evidence', '')}"
        for i, c in enumerate(candidates, start=1)
    )
    prompt = f"""请判断下面哪些代码仓库候选最可能对应这篇论文。

论文标题：{paper.title}
arXiv ID：{paper.arxiv_id}
摘要：{(paper.abstract or '')[:700]}

候选代码链接：
{candidate_text}

请只返回 JSON：
{{
  "best_index": 1,
  "suggested_url": "如果你确信存在官方/相关代码链接，可填写一个候选列表之外的 URL；不确定则为空字符串",
  "preferred": "candidate 或 suggested 或 none",
  "confidence": 0.0到1.0,
  "reason": "一句中文理由"
}}

规则：
- 优先选择 PDF 原文或 Papers with Code 明确给出的链接。
- 如果 GitHub 候选的仓库名/描述与论文标题、方法名或 arXiv ID 明显对应，可以选择。
- 你可以根据已有知识提出一个候选列表之外的 suggested_url，但必须是你较确信的官方/相关链接；不确定就留空。
- 不要为了填 suggested_url 而猜测。
- 最后在候选链接和 suggested_url 之间比较，preferred 返回 candidate、suggested 或 none。
- 如果所有链接都不像对应论文，best_index 返回 0 且 preferred 返回 none。"""

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return candidates[0]["url"]
        decision = json.loads(text[start:end])
        best_index = int(decision.get("best_index") or 0)
        confidence = float(decision.get("confidence") or 0.0)
        preferred = str(decision.get("preferred") or "candidate").strip().lower()
        suggested_url = _clean_url(str(decision.get("suggested_url") or ""))

        if preferred == "suggested" and confidence >= 0.55 and _validate_suggested_code_url(suggested_url, paper):
            return suggested_url
        if preferred == "none":
            return None
        if 1 <= best_index <= len(candidates) and confidence >= 0.35:
            return candidates[best_index - 1]["url"]
        if suggested_url and confidence >= 0.7 and _validate_suggested_code_url(suggested_url, paper):
            return suggested_url
        return None
    except Exception as e:
        logger.debug(f"DeepSeek code candidate verification failed: {e}")
        return candidates[0]["url"]


def find_code_for_paper(
    paper: Paper,
    github_token: Optional[str] = None,
    max_urls: int = 1,
    deepseek_api_key: Optional[str] = None,
    deepseek_model: str = "deepseek-chat",
    deepseek_base_url: str = "https://api.deepseek.com",
    scan_pdf: bool = True,
    verify_with_llm: bool = True,
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
        Best matching code URL, or an empty list if none is found.
    """
    candidates: list[dict] = []

    # Strongest evidence: repository links explicitly printed in the PDF.
    # This is accurate but can be slow, so GUI fast mode can disable it.
    if scan_pdf:
        for url in find_code_urls_in_pdf(paper, max_urls=5):
            _add_candidate(candidates, url, "PDF原文链接", 1.0, "论文 PDF 中直接出现的代码链接")

    # Curated source: Papers with Code repository mappings.
    for url in search_paperswithcode_repos(paper, max_results=5):
        _add_candidate(candidates, url, "Papers with Code", 0.92, "Papers with Code 论文仓库映射")

    repos = []
    query_limit = 2 if not scan_pdf else 4
    for title_query in _title_queries(paper.title)[:query_limit]:
        repos.extend(search_github_repos(title_query, github_token=github_token, max_results=5))
        time.sleep(0.2)

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
            _add_candidate(
                candidates,
                repo["html_url"],
                "GitHub搜索",
                min(0.8, rel),
                f"{repo.get('full_name', '')}: {repo.get('description', '')} stars={repo.get('stars', 0)}",
            )
            logger.debug(f"  Found code: {repo['html_url']} (relevance={rel:.2f})")

    best_url = None
    if verify_with_llm:
        best_url = select_best_code_url_with_llm(
            paper,
            candidates,
            api_key=deepseek_api_key,
            model=deepseek_model,
            base_url=deepseek_base_url,
        )
    elif candidates:
        best_url = sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)[0]["url"]
    return [best_url] if best_url else []


def find_code_for_papers(
    papers: list[Paper],
    github_token: Optional[str] = None,
    deepseek_api_key: Optional[str] = None,
    deepseek_model: str = "deepseek-chat",
    deepseek_base_url: str = "https://api.deepseek.com",
    scan_pdf: bool = True,
    verify_with_llm: bool = True,
    max_workers: int = 1,
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

    def search_one(index_and_paper: tuple[int, Paper]) -> tuple[int, list[str]]:
        i, paper = index_and_paper
        logger.info(f"  [{i+1}/{len(papers)}] Searching code for: {paper.short_title}")
        code_urls = find_code_for_paper(
            paper,
            github_token=github_token,
            max_urls=1,
            deepseek_api_key=deepseek_api_key,
            deepseek_model=deepseek_model,
            deepseek_base_url=deepseek_base_url,
            scan_pdf=scan_pdf,
            verify_with_llm=verify_with_llm,
        )
        return i, code_urls

    if max_workers <= 1:
        results = [search_one((i, paper)) for i, paper in enumerate(papers)]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(search_one, (i, paper)) for i, paper in enumerate(papers)]
            for future in as_completed(futures):
                results.append(future.result())

    for i, code_urls in sorted(results, key=lambda item: item[0]):
        paper = papers[i]
        if code_urls:
            paper.has_code = True
            paper.code_urls = code_urls
            logger.info(f"    Found {len(code_urls)} repo(s)")
        else:
            logger.debug(f"    No code found")

    papers_with_code = sum(1 for p in papers if p.has_code)
    logger.info(f"Code found for {papers_with_code}/{len(papers)} papers")

    return papers
