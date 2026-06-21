# Poster Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dense full-text SVG poster with a portrait, GUI-embeddable, 图文并茂 academic poster — figure1 lineage graph as hero, 1–2 review-paragraph excerpts interleaved with a taxonomy chart and a trade-off matrix — authored in HTML/CSS and rasterized to PNG.

**Architecture:** Pure data assembly (`poster_data`) turns a `MilestoneGraph` + review markdown + papers into a `PosterData` dataclass. A pure template (`poster_render`) renders `PosterData` + the **existing static figure1 SVG** into one HTML string (DESIGN.md tokens). A thin rasterizer (`poster_rasterize`) shells out to headless Chrome + PIL-crops. An orchestrator (`poster_generator`) wires them; `agents.py` builds the graph and calls it.

**Tech Stack:** Python 3.10, dataclasses, `re`, `html.escape`, PIL (already a dep), system Google Chrome (headless `--screenshot`). No new pip packages. Fonts via Google Fonts at rasterize time.

## Global Constraints

- Interpreter: **conda env `reviewmaker`** → `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3` (this plan calls it `$PY`). System `python3` lacks deps.
- Imports use `from src.X import Y`; tests live in `tests/`, run from repo root.
- Styling = **DESIGN.md tokens**; the canonical CSS is the committed `docs/reference/poster_redesign_mockup.html` (the approved v3 mockup) — copy its `<style>` verbatim, do not re-invent.
- Hero = reuse `figure1_render.render_figure1_svg(graph)` **static SVG** (no JS, no re-render).
- Content is **demo-grade**: simple paragraph extraction, deterministic heuristics — **no rigorous LLM filtering**.
- `generate_poster` stays **LLM-free** (graph is passed in); the only LLM/network call (`build_milestone_graph`) lives in the `agents.py` integration layer.
- Commit after every task. Run the full suite (`$PY -m pytest -q`) before each commit; new tests green, existing figure1/milestone tests not regressed.

## File Structure

| File | Responsibility | New/Modify |
|------|----------------|-----------|
| `src/poster_data.py` | Pure data assembly → `PosterData` (stats, excerpts, taxonomy, tradeoff, highlight) | Create |
| `src/poster_render.py` | Pure HTML template: `PosterData` + hero SVG → HTML string | Create |
| `src/poster_rasterize.py` | Headless-Chrome screenshot + PIL autocrop | Create |
| `src/poster_generator.py` | Orchestrate data→render→rasterize: `generate_poster(...)` | **Replace** (was PIL legacy; superseded) |
| `src/figure1_render.py` | Add `embed=` mode (suppress internal chrome) | Modify |
| `src/agents.py` | `VisualizerAgent`: build graph + call `generate_poster` | Modify |
| `tests/_poster_fixtures.py` | Shared `sample_graph()` + `SAMPLE_REVIEW` | Create |
| `tests/test_poster_data.py` / `test_poster_render.py` / `test_poster_rasterize.py` / `test_poster_generator.py` / `test_figure1_render.py`(extend) / `test_visualizer_poster.py` | Tests | Create/Modify |

> The legacy `src/svg_poster_generator.py` is left in place but no longer called; its dense-poster tests (`test_poster_embed_svg.py`) may be retired in Task 8 if they break.

---

### Task 1: PosterData models + stats + taxonomy

**Files:**
- Create: `src/poster_data.py`
- Create: `tests/_poster_fixtures.py`
- Test: `tests/test_poster_data.py`

**Interfaces:**
- Consumes: `src.figure1_models` (`Milestone, Branch, Era, MilestoneGraph, FOUND`); `Paper` (has `.has_code: bool`, `.year: int`).
- Produces: dataclasses `Stat, TaxonomyBar, Excerpt, TradeoffRow, Tradeoff, PosterData`; `build_stats(graph, papers) -> list[Stat]`; `build_taxonomy(graph) -> list[TaxonomyBar]`.

- [ ] **Step 1: Write the shared fixture**

Create `tests/_poster_fixtures.py`:

```python
"""Shared fixtures for poster tests."""
from src.figure1_models import Milestone, Branch, Era, MilestoneGraph, FOUND


def _m(name, year, branch, contrib, code=True):
    return Milestone(name=name, authors=f"{name} et al", year=year, branch=branch,
                     contrib=contrib, paper_index=None, full_title=f"{name}: a paper",
                     venue="arXiv", cited_by=10, has_code=code, abstract="abs")


def sample_graph():
    branches = [
        Branch(id="A", name_zh="KV Cache 压缩与淘汰", name_en="COMPRESSION / EVICTION"),
        Branch(id="B", name_zh="系统 / IO-aware 引擎", name_en="SYSTEM / IO-AWARE"),
        Branch(id="C", name_zh="量化 / 紧凑存储", name_en="QUANTIZATION / STORAGE"),
    ]
    eras = [Era(name_zh="基础奠基时代", name_en="FOUNDATIONS"),
            Era(name_zh="KV Cache 优化爆发", name_en="KV-CACHE BOOM")]
    eras[0].y0, eras[0].y1 = 2017, 2023
    eras[1].y0, eras[1].y1 = 2024, 2026
    milestones = [
        _m("Transformer", 2017, FOUND, "提出自注意力"),
        _m("FlashAttention", 2022, FOUND, "IO-aware 精确注意力"),
        _m("Ada-KV", 2024, "A", "自适应预算淘汰", code=True),
        _m("ReST-KV", 2026, "A", "鲁棒淘汰", code=False),
        _m("FlashInfer", 2025, "B", "高效注意力引擎", code=True),
        _m("VecInfer", 2025, "C", "低比特量化", code=True),
    ]
    return MilestoneGraph(topic="大模型推理中 Transformer 注意力机制优化",
                          milestones=milestones, branches=branches, eras=eras,
                          enough=True, metrics={"num_milestones": 6, "num_branches": 3})


SAMPLE_REVIEW = """# 文献综述

## 一、研究背景与问题定义

随着大语言模型取得突破性进展，其推理效率面临挑战。KV Cache 技术应运而生，但显存占用随序列长度线性增长，成为关键瓶颈，需要系统性优化。

## 六、横向对比分析

量化类方法对硬件友好；驱逐类在长上下文更有优势；系统类需要软硬件协同。

## 九、结论

本综述梳理了 KV Cache 与 Flash Attention 的关键技术。未来的突破将更依赖多种优化技术的深度融合、对任务动态特性的在线感知。
"""
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_poster_data.py`:

```python
from tests._poster_fixtures import sample_graph
from src.poster_data import build_stats, build_taxonomy


class _P:
    def __init__(self, has_code): self.has_code = has_code; self.year = 2024


def test_build_stats_counts_papers_and_code_pct():
    papers = [_P(True), _P(True), _P(True), _P(False)]  # 3/4 = 75%
    stats = build_stats(sample_graph(), papers)
    assert [s.value for s in stats] == ["4", "75%", "3", "10"]  # 2017..2026 -> 10 yrs
    assert stats[0].accent is True


def test_build_taxonomy_counts_and_normalizes():
    bars = build_taxonomy(sample_graph())
    names = {b.name: b.count for b in bars}
    assert names["KV Cache 压缩与淘汰"] == 2  # Ada-KV + ReST-KV
    assert names["奠基性工作 Foundational"] == 2  # Transformer + FlashAttention
    assert max(b.width_pct for b in bars) == 100
```

- [ ] **Step 3: Run test to verify it fails**

Run: `$PY -m pytest tests/test_poster_data.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.poster_data'`

- [ ] **Step 4: Write minimal implementation**

Create `src/poster_data.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `$PY -m pytest tests/test_poster_data.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/poster_data.py tests/_poster_fixtures.py tests/test_poster_data.py
git commit -m "feat(poster): PosterData stats + taxonomy assembly"
```

---

### Task 2: Review excerpt + highlight extraction

**Files:**
- Modify: `src/poster_data.py`
- Test: `tests/test_poster_data.py`

**Interfaces:**
- Produces: `Excerpt(heading, heading_en, source, text)`; `select_excerpts(review_summary: str) -> list[Excerpt]` (always length 2: background, conclusion); `extract_highlight(review_summary: str) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_poster_data.py`:

```python
from tests._poster_fixtures import SAMPLE_REVIEW
from src.poster_data import select_excerpts, extract_highlight


def test_select_excerpts_finds_background_and_conclusion():
    ex = select_excerpts(SAMPLE_REVIEW)
    assert len(ex) == 2
    assert "KV Cache 技术应运而生" in ex[0].text
    assert "深度融合" in ex[1].text
    assert "结论" in ex[1].source


def test_select_excerpts_fallback_when_no_sections():
    ex = select_excerpts("只有一段没有标题的纯文本，作为兜底。")
    assert len(ex) == 2
    assert ex[0].text  # non-empty fallback


def test_extract_highlight_is_first_conclusion_sentence():
    hl = extract_highlight(SAMPLE_REVIEW)
    assert hl.startswith("本综述梳理")
    assert hl.endswith("。")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_poster_data.py -q`
Expected: FAIL — `ImportError: cannot import name 'select_excerpts'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/poster_data.py`:

```python
import re

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PY -m pytest tests/test_poster_data.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/poster_data.py tests/test_poster_data.py
git commit -m "feat(poster): review excerpt + highlight extraction"
```

---

### Task 3: Trade-off matrix + build_poster_data

**Files:**
- Modify: `src/poster_data.py`
- Test: `tests/test_poster_data.py`

**Interfaces:**
- Produces: `TradeoffRow(name, marks: list[str])`; `Tradeoff(dims: list[str], rows: list[TradeoffRow])`; `build_tradeoff(review_summary, graph) -> Tradeoff`; `PosterData(...)`; `build_poster_data(topic, review_summary, papers, graph) -> PosterData`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_poster_data.py`:

```python
from tests._poster_fixtures import sample_graph as _sg
from src.poster_data import build_tradeoff, build_poster_data


def test_build_tradeoff_dims_and_rows():
    t = build_tradeoff("", _sg())
    assert t.dims == ["性能·效率", "可复现", "适用场景"]
    assert len(t.rows) == 3
    assert t.rows[0].name == "KV Cache 压缩与淘汰"
    assert t.rows[0].marks[2] == "长上下文"   # EVICTION scenario
    assert all(len(r.marks) == 3 for r in t.rows)


def test_build_poster_data_full():
    papers = [_P(True)] * 4
    d = build_poster_data("我的主题", SAMPLE_REVIEW, papers, _sg())
    assert d.title == "我的主题"
    assert len(d.stats) == 4 and len(d.excerpts) == 2
    assert len(d.taxonomy) == 4 and len(d.tradeoff.rows) == 3
    assert d.highlight and d.foot_left
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_poster_data.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_tradeoff'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/poster_data.py`:

```python
@dataclass
class TradeoffRow:
    name: str
    marks: list = field(default_factory=list)


@dataclass
class Tradeoff:
    dims: list
    rows: list


_SCENARIO = {"EVICTION": "长上下文", "COMPRESSION": "长上下文",
             "SYSTEM": "服务器集群", "IO": "服务器集群",
             "QUANT": "边缘部署", "STORAGE": "边缘部署"}


def _scenario(name_en):
    up = (name_en or "").upper()
    for k, v in _SCENARIO.items():
        if k in up:
            return v
    return "通用"


def build_tradeoff(review_summary, graph):
    rows = []
    for b in graph.branches[:3]:
        members = [m for m in graph.milestones if m.branch == b.id]
        ratio = (sum(1 for m in members if m.has_code) / len(members)) if members else 0
        repro = "●" if ratio >= 0.5 else "◐"
        up = (b.name_en or "").upper()
        perf = "●" if ("SYSTEM" in up or "IO" in up or "QUANT" in up) else "◐"
        rows.append(TradeoffRow(b.name_zh, [perf, repro, _scenario(b.name_en)]))
    return Tradeoff(["性能·效率", "可复现", "适用场景"], rows)


@dataclass
class PosterData:
    title: str
    stats: list
    highlight: str
    excerpts: list
    taxonomy: list
    tradeoff: Tradeoff
    foot_left: str = "文献综述 Agent · 基于 DeepSeek 大模型自动生成"
    foot_right: str = "Fig.1 Lineage · OpenAlex 引用骨架"


def build_poster_data(topic, review_summary, papers, graph):
    return PosterData(
        title=topic,
        stats=build_stats(graph, papers),
        highlight=extract_highlight(review_summary),
        excerpts=select_excerpts(review_summary),
        taxonomy=build_taxonomy(graph),
        tradeoff=build_tradeoff(review_summary, graph),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PY -m pytest tests/test_poster_data.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/poster_data.py tests/test_poster_data.py
git commit -m "feat(poster): tradeoff matrix + build_poster_data"
```

---

### Task 4: figure1_render embed mode

**Files:**
- Modify: `src/figure1_render.py` (wrap kicker/title ~lines 90-91 and footer ~lines 164-170)
- Test: `tests/test_figure1_render.py` (extend)

**Interfaces:**
- Produces: `render_figure1_svg(graph, embed=False) -> (svg: str, nodes_json: list)`. When `embed=True`: omit the internal kicker ("ALGORITHM LINEAGE"), the topic title, and the footer chrome ("METHOD EVOLUTION TIMELINE" line) — the poster supplies its own. Graph body, lanes, eras, nodes unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_figure1_render.py` (create if absent, with the import):

```python
from tests._poster_fixtures import sample_graph
from src.figure1_render import render_figure1_svg


def test_embed_mode_omits_internal_chrome():
    full, _ = render_figure1_svg(sample_graph(), embed=False)
    bare, _ = render_figure1_svg(sample_graph(), embed=True)
    assert "ALGORITHM LINEAGE" in full
    assert "METHOD EVOLUTION TIMELINE" in full
    assert "ALGORITHM LINEAGE" not in bare
    assert "METHOD EVOLUTION TIMELINE" not in bare
    # graph body still present in both
    assert "KV Cache 压缩与淘汰" in bare
    assert "<circle" in bare
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_figure1_render.py::test_embed_mode_omits_internal_chrome -q`
Expected: FAIL — `TypeError: render_figure1_svg() got an unexpected keyword argument 'embed'`

- [ ] **Step 3: Write minimal implementation**

In `src/figure1_render.py`, change the signature and wrap the chrome blocks:

```python
def render_figure1_svg(graph, embed=False):
```

Wrap the kicker + title block (currently the two `parts.append(... t-kicker ...)` / `... t-title ...` lines) in:

```python
    if not embed:
        parts.append(f'<text class="t-kicker" x="{PAD["l"]}" y="22">ALGORITHM LINEAGE · 算法演进谱系</text>')
        parts.append(f'<text class="t-title" x="{PAD["l"]}" y="46">{_esc(graph.topic)}</text>')
```

Wrap the footer chrome block (the `nf = ...` through the two `t-foot` `parts.append(...)` lines) in:

```python
    if not embed:
        nf = sum(1 for m in graph.milestones if m.branch == FOUND)
        nb = len(graph.branches)
        parts.append(f'<line class="fig-line" x1="{PAD["l"]}" y1="{H-46}" x2="{W-PAD["r"]}" y2="{H-46}" style="stroke-opacity:.4"/>')
        parts.append(f'<text class="t-foot" x="{PAD["l"]}" y="{H-30}">FIG. 1 — METHOD EVOLUTION TIMELINE</text>')
        parts.append(f'<text class="t-foot" x="{W-PAD["r"]}" y="{H-30}" text-anchor="end">'
                     f'{len(graph.milestones)} MILESTONES · {nf} FOUNDATIONAL · {nb} LINEAGES</text>')
```

(Leave era labels, lanes, spine, nodes untouched.)

- [ ] **Step 4: Run tests to verify pass + no regression**

Run: `$PY -m pytest tests/test_figure1_render.py -q`
Expected: PASS (existing figure1 render tests + the new one)

- [ ] **Step 5: Commit**

```bash
git add src/figure1_render.py tests/test_figure1_render.py
git commit -m "feat(figure1): embed mode (omit internal chrome) for poster reuse"
```

---

### Task 5: poster_render HTML template

**Files:**
- Create: `src/poster_render.py`
- Test: `tests/test_poster_render.py`

**Interfaces:**
- Consumes: `PosterData` (Task 3); a `hero_svg: str` (Task 4 output); CSS from `docs/reference/poster_redesign_mockup.html`.
- Produces: `render_poster_html(data: PosterData, hero_svg: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_poster_render.py`:

```python
from tests._poster_fixtures import sample_graph, SAMPLE_REVIEW
from src.poster_data import build_poster_data
from src.poster_render import render_poster_html


class _P:
    has_code = True
    year = 2024


def test_render_contains_all_regions():
    data = build_poster_data("我的主题 TopicX", SAMPLE_REVIEW, [_P()] * 4, sample_graph())
    html = render_poster_html(data, '<svg id="hero"><circle/></svg>')
    for needle in ["TopicX", "综述论文", "<svg id=\"hero\"",
                   "方法体系分类", "横向对比", "节选自综述",
                   "性能·效率", "class=\"poster\"", "Jost"]:
        assert needle in html, needle
    # CJK auto-wrapped for title weight
    assert 'class="zh"' in html


def test_render_escapes_text():
    data = build_poster_data("A & B <x>", SAMPLE_REVIEW, [_P()] * 2, sample_graph())
    html = render_poster_html(data, "<svg/>")
    assert "A &amp; B" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_poster_render.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.poster_render'`

- [ ] **Step 3: Write minimal implementation**

First, open `docs/reference/poster_redesign_mockup.html` and copy the **entire contents between `<style>` and `</style>`** (the `:root` vars through the `.legend` rule, ≈130 lines) into the `_STYLE` string below (replace the `<<< PASTE >>>` marker). This is the approved v3 CSS — do not rewrite it.

Create `src/poster_render.py`:

```python
"""Pure HTML template: PosterData + hero SVG -> one self-contained HTML string.

CSS is the committed v3 mockup (docs/reference/poster_redesign_mockup.html).
Rendered to PNG by poster_rasterize (headless browser loads the Google Fonts).
"""
import re
from html import escape as _esc

_STYLE = r"""
<<< PASTE the contents between <style> and </style> from
    docs/reference/poster_redesign_mockup.html here, verbatim >>>
"""

_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link href="https://fonts.googleapis.com/css2?family=Jost:wght@200;300;400;500'
          '&family=Lora:ital,wght@0,400;0,500;1,400&family=JetBrains+Mono:wght@400;500'
          '&family=Noto+Sans+SC:wght@300;400;500;700&family=Noto+Serif+SC:wght@400;600'
          '&display=swap" rel="stylesheet">')

_CJK = re.compile(r"([一-鿿，。：；！？、（）「」]+)")


def _wrap_cjk(text):
    return _CJK.sub(r'<span class="zh">\1</span>', _esc(text))


def _stat(s):
    style = ' style="border-top-color:var(--primary)"' if s.accent else ""
    val = s.value.replace("%", '<span class="u">%</span>')
    return (f'<div class="stat"{style}><div class="num">{val}</div>'
            f'<div class="lab">{_esc(s.label)}</div><div class="sub">{_esc(s.sub)}</div></div>')


def _bar(b):
    extra = ";background:var(--primary)" if b.accent else ""
    return (f'<div class="bar"><div class="top"><span class="nm">{_esc(b.name)}</span>'
            f'<span class="ct">{b.count}</span></div><div class="track">'
            f'<div class="fill" style="width:{b.width_pct}%{extra}"></div></div></div>')


def _excerpt(e):
    return (f'<div class="sec-h"><span class="zh">{_esc(e.heading)}</span>'
            f'<span class="en">{_esc(e.heading_en)}</span></div>'
            f'<div class="excerpt">{_esc(e.text)}</div>'
            f'<div class="src">{_esc(e.source)}</div>')


def _matrix(t):
    head = "".join(f"<th>{_esc(d)}</th>" for d in t.dims)
    body = ""
    for r in t.rows:
        cells = "".join(f'<td><span class="mk">{_esc(m)}</span></td>' for m in r.marks)
        body += f'<tr><td class="rowh">{_esc(r.name)}</td>{cells}</tr>'
    return (f'<table class="mtx"><tr><th>类别 / Lineage</th>{head}</tr>{body}</table>'
            '<div class="legend">● High&nbsp;&nbsp;◐ Medium&nbsp;&nbsp;'
            "— 适用场景由综述横向对比节归纳</div>")


def render_poster_html(data, hero_svg):
    stats = "".join(_stat(s) for s in data.stats)
    bars = "".join(_bar(b) for b in data.taxonomy)
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">{_FONTS}
<style>{_STYLE}</style></head><body><div class="poster">
<div class="chrome"><span>ReviewMaker · 文献综述海报</span><span>AUTO-GENERATED</span></div>
<div class="rule-full"></div>
<div class="kicker">Algorithm Lineage · 算法演进谱系</div>
<div class="title">{_wrap_cjk(data.title)}</div>
<div class="rule36"></div>
<div class="stats">{stats}</div>
<div class="figwrap">{hero_svg}<div class="caption">Fig. 1 — Method Evolution Timeline</div></div>
<div class="highlight">“{_esc(data.highlight)}”</div>
<div class="band"><div class="col-text">{_excerpt(data.excerpts[0])}</div>
<div class="col-viz"><div class="sec-h"><span class="zh">方法体系分类</span>
<span class="en">Taxonomy</span></div>{bars}</div></div>
<div class="band alt"><div class="col-viz"><div class="sec-h"><span class="zh">横向对比</span>
<span class="en">Trade-offs</span></div>{_matrix(data.tradeoff)}</div>
<div class="col-text">{_excerpt(data.excerpts[1])}</div></div>
<div class="chrome foot"><span>{_esc(data.foot_left)}</span><span>{_esc(data.foot_right)}</span></div>
</div></body></html>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PY -m pytest tests/test_poster_render.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/poster_render.py tests/test_poster_render.py
git commit -m "feat(poster): HTML template (DESIGN.md, 图文并茂) from PosterData"
```

---

### Task 6: poster_rasterize (headless Chrome + PIL crop)

**Files:**
- Create: `src/poster_rasterize.py`
- Test: `tests/test_poster_rasterize.py`

**Interfaces:**
- Produces: `find_chrome() -> str | None`; `rasterize_html(html: str, png_path: str, *, width=1240, height=2600, scale=2) -> str` (writes a trimmed PNG, returns its path; raises `RuntimeError` if no browser).

- [ ] **Step 1: Write the failing test**

Create `tests/test_poster_rasterize.py`:

```python
import os
import pytest
from src.poster_rasterize import find_chrome, rasterize_html

pytestmark = pytest.mark.skipif(find_chrome() is None, reason="no chrome/chromium")


def test_rasterize_produces_nonempty_png(tmp_path):
    html = ('<!DOCTYPE html><html><body style="margin:0">'
            '<div style="width:400px;height:300px;background:#6D5DF6"></div></body></html>')
    out = str(tmp_path / "out.png")
    rasterize_html(html, out, width=500, height=500)
    assert os.path.exists(out) and os.path.getsize(out) > 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_poster_rasterize.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.poster_rasterize'`

- [ ] **Step 3: Write minimal implementation**

Create `src/poster_rasterize.py`:

```python
"""Rasterize an HTML poster to PNG via headless Chrome, then trim margins (PIL).

Uses the system browser (no new pip dependency); Google Fonts load at render
time via --virtual-time-budget.
"""
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageChops

_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_chrome():
    for c in _CANDIDATES:
        if os.path.exists(c):
            return c
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


def _autocrop(png_path, pad=24):
    im = Image.open(png_path).convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((0, 0)))
    bbox = ImageChops.difference(im, bg).getbbox()
    if bbox:
        l, t, r, b = bbox
        im.crop((max(0, l - pad), max(0, t - pad),
                 min(im.width, r + pad), min(im.height, b + pad))).save(png_path)


def rasterize_html(html, png_path, *, width=1240, height=2600, scale=2):
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("no chrome/chromium binary found for rasterize")
    os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        html_path = f.name
    try:
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--force-device-scale-factor={scale}", f"--window-size={width},{height}",
             "--virtual-time-budget=8000", f"--screenshot={png_path}", f"file://{html_path}"],
            check=True, capture_output=True, timeout=90)
    finally:
        os.unlink(html_path)
    _autocrop(png_path)
    return png_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PY -m pytest tests/test_poster_rasterize.py -q`
Expected: PASS (1 passed) — or SKIPPED if no browser; if skipped, also run a manual check:
`$PY -c "from src.poster_rasterize import find_chrome; print(find_chrome())"` should print a path.

- [ ] **Step 5: Commit**

```bash
git add src/poster_rasterize.py tests/test_poster_rasterize.py
git commit -m "feat(poster): headless-chrome rasterizer + PIL autocrop"
```

---

### Task 7: poster_generator orchestrator

**Files:**
- Modify: `src/poster_generator.py` (replace legacy PIL contents with the orchestrator)
- Test: `tests/test_poster_generator.py`

**Interfaces:**
- Consumes: `build_poster_data` (T3), `render_figure1_svg(graph, embed=True)` (T4), `render_poster_html` (T5), `rasterize_html` (T6), `render_insufficient_svg`.
- Produces: `generate_poster(topic, review_summary, papers, graph, out_dir, *, rasterize=True) -> dict` with keys `html` (path) and `png` (path or None).

- [ ] **Step 1: Write the failing test**

Create `tests/test_poster_generator.py`:

```python
import os
from tests._poster_fixtures import sample_graph, SAMPLE_REVIEW
from src.poster_generator import generate_poster


class _P:
    has_code = True
    year = 2024


def test_generate_poster_writes_html(tmp_path):
    res = generate_poster("主题 X", SAMPLE_REVIEW, [_P()] * 4, sample_graph(),
                          str(tmp_path), rasterize=False)
    assert os.path.exists(res["html"])
    html = open(res["html"], encoding="utf-8").read()
    assert "主题" in html and "<svg" in html and "方法体系分类" in html
    assert res["png"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_poster_generator.py -q`
Expected: FAIL — `ImportError: cannot import name 'generate_poster'` (or old PIL symbol).

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `src/poster_generator.py` with:

```python
"""Orchestrate the redesigned poster: data -> HTML -> PNG.

Pipeline-agnostic and LLM-free: the caller passes an already-built
MilestoneGraph (see src/agents.py). Visual spec: docs/superpowers/specs/
2026-06-21-poster-redesign-design.md.
"""
import logging
import os

from src.poster_data import build_poster_data
from src.poster_render import render_poster_html
from src.figure1_render import render_figure1_svg, render_insufficient_svg
from src.poster_rasterize import rasterize_html

logger = logging.getLogger(__name__)


def generate_poster(topic, review_summary, papers, graph, out_dir, *, rasterize=True):
    os.makedirs(out_dir, exist_ok=True)
    data = build_poster_data(topic, review_summary, papers, graph)
    if getattr(graph, "enough", True):
        hero_svg = render_figure1_svg(graph, embed=True)[0]
    else:
        hero_svg = render_insufficient_svg(topic)
    html = render_poster_html(data, hero_svg)
    html_path = os.path.join(out_dir, "poster.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    result = {"html": html_path, "png": None}
    if rasterize:
        try:
            result["png"] = rasterize_html(html, os.path.join(out_dir, "poster.png"))
        except Exception as e:  # browser missing / render failure — keep HTML, don't break pipeline
            logger.warning("poster rasterize skipped: %s", e)
    logger.info("poster written: %s (png=%s)", html_path, result["png"])
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PY -m pytest tests/test_poster_generator.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/poster_generator.py tests/test_poster_generator.py
git commit -m "feat(poster): generate_poster orchestrator (data->html->png)"
```

---

### Task 8: Wire into agents.py VisualizerAgent

**Files:**
- Modify: `src/agents.py` (imports near line 28-29; `VisualizerAgent` body lines ~322-353)
- Test: `tests/test_visualizer_poster.py`

**Interfaces:**
- Consumes: `build_milestone_graph(papers, topic, llm_call) -> MilestoneGraph` (`src/milestone_graph`); `_default_llm_call()` (`src/gui_figure1`); `generate_poster` (T7).
- Produces: `VisualizerAgent._build_poster(self, state)` — builds the graph and calls `generate_poster`, sets `state.poster_path`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_visualizer_poster.py`:

```python
import types
import src.agents as agents
from tests._poster_fixtures import sample_graph


def test_build_poster_uses_graph_and_generate_poster(tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(agents, "build_milestone_graph",
                        lambda papers, topic, llm_call=None: sample_graph())
    monkeypatch.setattr(agents, "_default_llm_call", lambda: (lambda p: ""))

    def fake_generate_poster(topic, review_summary, papers, graph, out_dir, **kw):
        calls["graph"] = graph
        calls["out_dir"] = out_dir
        return {"html": out_dir + "/poster.html", "png": out_dir + "/poster.png"}

    monkeypatch.setattr(agents, "generate_poster", fake_generate_poster)

    state = types.SimpleNamespace(
        papers=[object()], topic="T", review_text="R",
        output_dir=str(tmp_path), no_poster=False, poster_path=None)

    agents.VisualizerAgent()._build_poster(state)

    assert calls["graph"] is not None
    assert state.poster_path.endswith("poster.png")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_visualizer_poster.py -q`
Expected: FAIL — `AttributeError: 'VisualizerAgent' object has no attribute '_build_poster'`

- [ ] **Step 3: Write minimal implementation**

In `src/agents.py`, update imports (replace the `from src.svg_poster_generator import generate_svg_poster` line near line 29):

```python
from src.milestone_graph import build_milestone_graph
from src.gui_figure1 import _default_llm_call
from src.poster_generator import generate_poster
```

Add this method to `VisualizerAgent` (above `run`):

```python
    def _build_poster(self, state):
        graph = build_milestone_graph(state.papers, state.topic, llm_call=_default_llm_call())
        result = generate_poster(
            topic=state.topic,
            review_summary=state.review_text,
            papers=state.papers,
            graph=graph,
            out_dir=state.output_dir,
        )
        state.poster_path = result.get("png") or result["html"]
        self.log(f"海报: {state.poster_path}")
```

In `VisualizerAgent.run`, replace the whole `if not state.no_poster:` block (the `paper_figures` collection + the `generate_svg_poster(...)` call + `state.poster_path`/`self.log`, currently lines ~323-353) with:

```python
        if not state.no_poster:
            self._build_poster(state)
```

- [ ] **Step 4: Run tests — new + no regression**

Run: `$PY -m pytest tests/test_visualizer_poster.py -q`
Expected: PASS (1 passed)

Run the full suite: `$PY -m pytest -q`
Expected: new poster tests pass; figure1/milestone/openalex tests still pass. If `tests/test_poster_embed_svg.py` (legacy dense poster) fails because the pipeline no longer calls `generate_svg_poster`, retire it: `git rm tests/test_poster_embed_svg.py` and note it in the commit (the legacy generator is superseded).

- [ ] **Step 5: Commit**

```bash
git add src/agents.py tests/test_visualizer_poster.py
git commit -m "feat(poster): wire redesigned poster into VisualizerAgent pipeline"
```

---

## Final verification

- [ ] Run full suite: `$PY -m pytest -q` — all green (legacy dense-poster test retired if it conflicted).
- [ ] Live smoke (optional, needs Chrome): build a poster from the fixtures and eyeball it:

```bash
$PY -c "
from tests._poster_fixtures import sample_graph, SAMPLE_REVIEW
from src.poster_generator import generate_poster
class P: has_code=True; year=2024
print(generate_poster('大模型推理中 Transformer 注意力机制优化', SAMPLE_REVIEW, [P()]*15, sample_graph(), 'output/poster_demo'))
"
open output/poster_demo/poster.png
```

Compare against `docs/reference/poster_redesign_mockup.html`.

## Self-Review (done while writing — recorded for the implementer)

- **Spec coverage:** D1 portrait/§3 layout → T5 template; D2 DESIGN.md → T5 CSS reuse; D3 图文并茂 → T2 excerpts + T5 bands; D4 demo extraction → T2/T3 deterministic; D5 HTML+browser → T5/T6; D6 hero reuse → T4 embed + T7; D7 taxonomy+matrix → T1/T3/T5. §4 data map → T1–T3. §5 components → T1–T8 (one file each). §7 tests → each task. §8 risks (no-browser fallback) → T7 try/except.
- **Type consistency:** `PosterData/Stat/TaxonomyBar/Excerpt/Tradeoff/TradeoffRow` defined T1–T3, consumed T5/T7; `render_figure1_svg(graph, embed=)` T4 → used T7; `render_poster_html(data, hero_svg)` T5 → used T7; `generate_poster(...)→{html,png}` T7 → used T8. Names checked across tasks.
- **Deviation from spec §4:** spec assumed the pipeline pre-builds the graph; the CLI does **not** at this commit, so T8 builds it via `build_milestone_graph` (the one LLM/network call) and passes it in — `generate_poster` stays LLM-free and unit-testable.
