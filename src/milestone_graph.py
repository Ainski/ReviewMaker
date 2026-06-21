"""Assemble a MilestoneGraph from retrieved papers.

Pipeline: LLM plan (milestone_planner) -> map milestones back to real papers ->
verify LLM-proposed foundational classics against OpenAlex (drop unresolved) ->
decide `enough` -> compute metrics.
"""

import logging
from typing import Optional

from src.figure1_models import Milestone, Branch, Era, MilestoneGraph, FOUND
from src.milestone_planner import plan_milestones

logger = logging.getLogger(__name__)


def _venue_of(p) -> str:
    journal = getattr(p, "journal", None)
    if journal:
        return journal
    return f"arXiv {getattr(p, 'year', '')}".strip()


def _short_name(title: str) -> str:
    """First token of a title, e.g. 'Attention Is All You Need' -> 'Attention'."""
    parts = (title or "").split()
    return parts[0] if parts else "?"


def build_milestone_graph(papers: list, topic: str, *, llm_call,
                          client=None, min_milestones: int = 5) -> MilestoneGraph:
    if client is None:
        from src.openalex_client import OpenAlexClient
        client = OpenAlexClient()

    plan = plan_milestones(papers, topic, llm_call)

    # 1) paper milestones -> map back to real paper metadata
    milestones: list = []
    for item in plan.get("milestones", []):
        idx = item.get("paper_index")
        if not isinstance(idx, int) or not (1 <= idx <= len(papers)):
            continue
        p = papers[idx - 1]
        milestones.append(Milestone(
            name=item.get("name") or _short_name(getattr(p, "title", "")),
            authors=f"{getattr(p, 'first_author', '?')} et al",
            year=getattr(p, "year", 0) or 0,
            branch=item.get("branch") or "A",
            contrib=item.get("contrib") or (getattr(p, "key_innovation", "") or "")[:24],
            paper_index=idx,
            full_title=getattr(p, "title", ""),
            venue=_venue_of(p),
            cited_by=getattr(p, "oa_cited_by_count", 0) or getattr(p, "citation_count", 0) or 0,
            has_code=bool(getattr(p, "has_code", False)),
            abstract=(getattr(p, "abstract", "") or "")[:220],
            openalex_id=getattr(p, "openalex_id", "") or None,
        ))

    # 2) foundational classics: verify each against OpenAlex; drop unresolved + dedup
    verified = 0
    proposed = plan.get("foundational", []) or []
    seen_oa: set = set()
    for cand in proposed:
        name = cand.get("name")
        year = cand.get("year")
        work = client.verify_foundational(name, year)
        if work is None:
            continue
        if work.openalex_id and work.openalex_id in seen_oa:
            continue  # two candidates resolved to the same work
        seen_oa.add(work.openalex_id)
        verified += 1
        label = cand.get("short") or _short_name(work.title) or (name or "?")
        milestones.append(Milestone(
            name=label,
            authors="经典",            # ancestors: OpenAlex search doesn't fetch authors
            year=work.year or (year or 0),
            branch=FOUND,
            contrib="领域奠基之作",
            paper_index=None,
            full_title=work.title or name or "",
            venue=f"{work.year}" if work.year else "",
            cited_by=work.cited_by_count,
            has_code=False,
            abstract="该领域被广泛引用的经典奠基工作。",
            openalex_id=work.openalex_id or None,
        ))

    branches = [Branch(b.get("id", ""), b.get("name_zh", ""), b.get("name_en", ""))
                for b in plan.get("branches", []) if b.get("id")]
    eras = [Era(e.get("name_zh", ""), e.get("name_en", ""), e.get("y0", 0), e.get("y1", 0))
            for e in plan.get("eras", [])]

    enough = len(milestones) >= min_milestones
    metrics = {
        "num_milestones": len(milestones),
        "num_foundational": verified,
        "num_branches": len(branches),
        "openalex_verify_rate": f"{verified}/{len(proposed)}" if proposed else "0/0",
        "topic": topic,
    }
    return MilestoneGraph(topic=topic, milestones=milestones, branches=branches,
                          eras=eras, enough=enough, metrics=metrics)
