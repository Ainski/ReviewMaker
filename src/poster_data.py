"""Pure assembly of poster content from a MilestoneGraph + review + papers.

No IO, no rendering, no LLM — every function is deterministic and unit-testable.
"""
from dataclasses import dataclass, field
import re

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


_HEADING = re.compile(r"^#{1,4}\s*(.+?)\s*$", re.M)


@dataclass
class Excerpt:
    heading: str
    heading_en: str
    source: str
    text: str


def _sections(md):
    ms = list(_HEADING.finditer(md))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(md)
        out.append((m.group(1), md[m.end():end].strip()))
    return out


def _first_para(body):
    for para in re.split(r"\n\s*\n", body):
        p = para.strip()
        if p and p[0] not in "|#-!":
            return p
    return body.strip()


def _truncate(text, limit=150):
    t = text.strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    for sep in ("。", "；", "，"):
        idx = cut.rfind(sep)
        if idx >= limit * 0.6:
            return cut[: idx + 1]
    return cut + "…"


def _find(secs, keys):
    for title, body in secs:
        if any(k in title for k in keys):
            return body
    return None


def select_excerpts(review_summary):
    secs = _sections(review_summary)
    bg = _find(secs, ["研究背景", "背景", "摘要", "引言", "问题定义"])
    cc = _find(secs, ["结论", "总结"])
    if bg is None:
        bg = secs[0][1] if secs else review_summary
    if cc is None:
        cc = secs[-1][1] if secs else review_summary
    return [
        Excerpt("研究背景与问题定义", "Background · 摘要节选",
                "— 节选自综述「研究背景 / 摘要」", _truncate(_first_para(bg))),
        Excerpt("核心结论与趋势", "Key Findings · 结论节选",
                "— 节选自综述「结论」", _truncate(_first_para(cc))),
    ]


def extract_highlight(review_summary):
    secs = _sections(review_summary)
    cc = _find(secs, ["结论", "总结"]) or (secs[-1][1] if secs else review_summary)
    para = _first_para(cc)
    m = re.search(r"(.+?[。！？])", para)
    return (m.group(1) if m else para[:60]).strip()
