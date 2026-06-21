"""Pure assembly of poster content from a MilestoneGraph + review + papers.

No IO, no rendering, no LLM — every function is deterministic and unit-testable.
"""
from dataclasses import dataclass, field

from src.figure1_models import FOUND


@dataclass
class Stat:
    value: str
    label: str
    sub: str
    accent: bool = False


@dataclass
class TaxonomyBar:
    name: str
    count: int
    width_pct: int = 0
    accent: bool = False


def build_stats(graph, papers):
    n = len(papers)
    with_code = sum(1 for p in papers if getattr(p, "has_code", False))
    pct = round(100 * with_code / n) if n else 0
    years = [m.year for m in graph.milestones if m.year]
    y0, y1 = (min(years), max(years)) if years else (0, 0)
    span = (y1 - y0 + 1) if years else 0
    return [
        Stat(str(n), "综述论文", "Papers Reviewed", accent=True),
        Stat(f"{pct}%", "开源代码", f"{with_code} / {n} · Code"),
        Stat(str(len(graph.branches)), "技术谱系", "Lineages"),
        Stat(str(span), "跨越年份", f"{y0} – {y1}"),
    ]


def build_taxonomy(graph):
    bars = []
    for i, b in enumerate(graph.branches):
        cnt = sum(1 for m in graph.milestones if m.branch == b.id)
        bars.append(TaxonomyBar(b.name_zh, cnt, accent=(i == 0)))
    found = sum(1 for m in graph.milestones if m.branch == FOUND)
    bars.append(TaxonomyBar("奠基性工作 Foundational", found))
    mx = max((b.count for b in bars), default=1) or 1
    for b in bars:
        b.width_pct = round(100 * b.count / mx)
    return bars
