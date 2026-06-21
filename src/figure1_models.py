"""Data models for the Figure-1 milestone lineage diagram.

A MilestoneGraph is the rendering-agnostic structure produced by the data layer
(`milestone_graph.build_milestone_graph`) and consumed by the renderer
(`figure1_render.render_figure1_svg`).
"""

from dataclasses import dataclass, field
from typing import Optional

# Branch id marking a foundational (奠基) milestone — drawn on the central spine.
FOUND = "__found__"


@dataclass
class Milestone:
    name: str                      # short method name, e.g. "FlashAttention"
    authors: str                   # first author, e.g. "Dao et al"
    year: int
    branch: str                    # branch id; FOUND for foundational works
    contrib: str                   # one-line key contribution (<= ~24 CJK chars)
    paper_index: Optional[int]     # 1-based index into the retrieved papers; None for ancestors
    full_title: str
    venue: str
    cited_by: int
    has_code: bool
    abstract: str                  # short abstract for the detail panel
    openalex_id: Optional[str] = None


@dataclass
class Branch:
    id: str                        # "A" / "B" / ...
    name_zh: str                   # e.g. "KV Cache 压缩与淘汰"
    name_en: str                   # e.g. "COMPRESSION / EVICTION"


@dataclass
class Era:
    name_zh: str
    name_en: str
    y0: int
    y1: int


@dataclass
class MilestoneGraph:
    topic: str
    milestones: list = field(default_factory=list)
    branches: list = field(default_factory=list)
    eras: list = field(default_factory=list)
    enough: bool = True            # False -> render the "信息不足" placeholder
    metrics: dict = field(default_factory=dict)
