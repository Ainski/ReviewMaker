"""OpenAlex client — resolves papers to OpenAlex works and fetches the citation graph.

Uses `select` (NOT `fields`) for projection; `select` MUST include referenced_works.
OpenAlex IDs are normalized to bare form (W123…), never full URLs.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from config import config
from src.models import Paper

logger = logging.getLogger(__name__)

OA_SELECT = "id,ids,doi,title,publication_year,cited_by_count,referenced_works"


@dataclass
class OpenAlexWork:
    openalex_id: str
    title: str
    year: int
    cited_by_count: int
    referenced_works: list[str] = field(default_factory=list)
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None


def _bare_id(oa_url: str) -> str:
    """'https://openalex.org/W123' -> 'W123'."""
    if not oa_url:
        return ""
    return oa_url.rstrip("/").split("/")[-1]


def _strip_arxiv_version(arxiv_id: str) -> str:
    """'2211.12792v2' -> '2211.12792'."""
    return re.sub(r"v\d+$", "", arxiv_id)


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _title_similarity(query: str, candidate: str) -> float:
    """Fraction of query title tokens present in the candidate title (0..1)."""
    q = _tokens(query)
    if not q:
        return 0.0
    c = _tokens(candidate)
    return len(q & c) / len(q)


def _sanitize_filter_value(s: str) -> str:
    """Strip characters that break an OpenAlex filter value: ',' (filter sep),
    '|' (OR sep), ':' (key sep). title.search tokenizes anyway, so this is lossless
    for matching while avoiding 400s on titles like 'Tokens-to-Token ViT, ...'."""
    return re.sub(r"\s+", " ", re.sub(r"[,|:]+", " ", s)).strip()


def _parse_work(data: dict) -> OpenAlexWork:
    ids = data.get("ids") or {}
    arxiv_id = ids.get("arxiv") if isinstance(ids, dict) else None
    return OpenAlexWork(
        openalex_id=_bare_id(data.get("id", "")),
        title=data.get("title") or "",
        year=data.get("publication_year") or 0,
        cited_by_count=data.get("cited_by_count") or 0,
        referenced_works=[_bare_id(r) for r in (data.get("referenced_works") or [])],
        doi=data.get("doi"),
        arxiv_id=arxiv_id,
    )


class OpenAlexClient:
    def __init__(self, base_url: Optional[str] = None, mailto: Optional[str] = None,
                 session: Optional[requests.Session] = None):
        self.base_url = base_url or config.openalex_base_url
        self.mailto = mailto or config.openalex_mailto
        self.session = session or requests.Session()
        self._cache: dict = {}

    def _get(self, path: str, params: dict) -> Optional[dict]:
        params = dict(params)
        params["mailto"] = self.mailto
        url = f"{self.base_url}{path}"
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=20)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 500, 502, 503):
                    time.sleep(1.0 * (attempt + 1))
                    continue
                logger.warning(f"OpenAlex {resp.status_code} for {url}")
                return None
            except requests.exceptions.RequestException as e:
                logger.warning(f"OpenAlex request error: {e}")
                time.sleep(0.5 * (attempt + 1))
        return None

    def resolve_work(self, paper: Paper) -> Optional[OpenAlexWork]:
        cache_key = paper.arxiv_id or paper.title
        if cache_key in self._cache:
            return self._cache[cache_key]
        preprint = None
        if paper.arxiv_id and not paper.arxiv_id.startswith("ss_"):
            clean = _strip_arxiv_version(paper.arxiv_id)
            data = self._get(f"/works/doi:10.48550/arXiv.{clean}", {"select": OA_SELECT})
            if data and data.get("id"):
                preprint = _parse_work(data)
        # OpenAlex arXiv-preprint records usually have EMPTY referenced_works; if so,
        # fall back to title search for the published version that actually has refs.
        if preprint is not None and preprint.referenced_works:
            self._cache[cache_key] = preprint
            return preprint
        work = self._resolve_by_title(paper) or preprint
        if work is not None:
            self._cache[cache_key] = work
        return work

    def _resolve_by_title(self, paper: Paper) -> Optional[OpenAlexWork]:
        if not paper.title:
            return None
        data = self._get("/works", {
            "filter": f"title.search:{_sanitize_filter_value(paper.title)}",
            "select": OA_SELECT,
            "per_page": 5,
        })
        if not data:
            return None
        best, best_score = None, 0.0
        for raw in (data.get("results") or []):
            cand = _parse_work(raw)
            score = _title_similarity(paper.title, cand.title)
            if score < 0.7:
                continue  # require a genuine title match before year/refs bonuses
            if paper.year and cand.year and abs(paper.year - cand.year) <= 2:
                score += 0.1
            if cand.referenced_works:
                score += 0.3  # prefer the version that actually carries the citation graph
            if score > best_score:
                best, best_score = cand, score
        return best if best_score >= 0.8 else None

    def fetch_works_by_ids(self, ids: list) -> dict:
        out: dict = {}
        unique = [i for i in dict.fromkeys(ids) if i]
        for start in range(0, len(unique), 50):
            batch = unique[start:start + 50]
            data = self._get("/works", {
                "filter": f"openalex:{'|'.join(batch)}",
                "select": OA_SELECT,
                "per_page": 50,
            })
            if not data:
                continue
            for raw in (data.get("results") or []):
                work = _parse_work(raw)
                if work.openalex_id:
                    out[work.openalex_id] = work
            time.sleep(0.15)
        return out

    def enrich_papers(self, papers: list) -> list:
        for p in papers:
            work = self.resolve_work(p)
            if work:
                p.openalex_id = work.openalex_id
                p.referenced_works = work.referenced_works
                p.oa_cited_by_count = work.cited_by_count
                p.oa_year = work.year
            time.sleep(0.15)
        return papers
