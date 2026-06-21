# 海报文字丰富化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让海报的"研究背景""核心结论"文字更厚、不重复、随论文数自适应,并新增"算法演进脉络"板块,全程不调 LLM。

**Architecture:** `poster_data.py` 是纯函数(无 LLM/IO)。新增自适应字数预算 `_budget`、多段抽取器 `_extract_block`;改写 `extract_highlight`(启发式选最有冲击力的一句)、`select_excerpts`(更厚、换源、去重);新增 `build_lineage_excerpt` + `PosterData.lineage`;`poster_render.py` 在 Fig.1 下方渲染演进脉络块。

**Tech Stack:** Python 3.10 (conda env `reviewmaker`), pytest, 纯字符串/正则。

## Global Constraints

- 解释器/测试:`/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest`,在 worktree `/private/tmp/reviewmaker-poster-text` 下运行。
- 全程**不新增任何 LLM 调用**;不改里程碑图/SVG、taxonomy、tradeoff 逻辑。
- 已知 2 个预先存在、与本任务无关的失败:`test_paper_fetcher::test_enrich_papers_with_semantic_scholar_updates_citations`、`test_review_generator::test_build_system_prompt`。本任务不得新增失败。
- 中文 UI 文案、英文标识符;commit 末尾加 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
- 字数预算:`n≤14→220`,`15≤n≤22→320`,`n≥23→420`(硬上限)。

---

### Task 1: 加长 fixture + 自适应预算 `_budget`

**Files:**
- Modify: `tests/_poster_fixtures.py`(加长 SAMPLE_REVIEW 各节 + 新增「算法演进脉络」节)
- Modify: `src/poster_data.py`(新增 `_budget`)
- Test: `tests/test_poster_data.py`

**Interfaces:**
- Produces: `_budget(n_papers: int) -> int`(220/320/420)。
- Produces: 更长的 `SAMPLE_REVIEW`,新增 `## 七、算法演进脉络` 节;保留旧断言所依赖的句子("KV Cache 技术应运而生"、"量化类方法"、"本综述梳理"、"深度融合")。

- [ ] **Step 1: 替换 fixture 的 SAMPLE_REVIEW**

在 `tests/_poster_fixtures.py` 中把 `SAMPLE_REVIEW = """..."""` 整体替换为:

```python
SAMPLE_REVIEW = """# 文献综述

## 一、研究背景与问题定义

随着大语言模型取得突破性进展，其推理效率面临严峻挑战。KV Cache 技术应运而生，用以缓存历史键值、避免重复计算，但显存占用随序列长度线性增长，成为长上下文推理的关键瓶颈，亟需系统性优化。注意力机制本身的二次复杂度，进一步放大了长序列场景下的计算与访存开销。

如何在不牺牲生成质量的前提下压缩缓存规模、提升解码吞吐，并兼顾不同硬件平台的部署约束，成为该领域必须回答的核心问题。

## 六、横向对比分析

量化类方法对硬件友好、压缩比高；驱逐类在长上下文场景更有优势；系统类则需要软硬件协同设计。三类方法在性能效率、可复现性与适用场景上各有取舍，难以用单一方案通吃所有负载。

整体来看，缓存压缩与系统级优化是当前工程落地最广的两条路线，而量化与驱逐的结合正成为新的研究热点。

## 七、算法演进脉络

从 Transformer 的自注意力奠基，到 FlashAttention 的 IO-aware 重写，再到 KV Cache 时代的驱逐、压缩与量化分支，方法沿着"更省显存、更高吞吐"的主轴持续演进。近两年呈现多分支融合与在线自适应的趋势。

## 九、结论

本综述梳理了 KV Cache 与 Flash Attention 的关键技术。未来的突破将更依赖多种优化技术的深度融合、对任务动态特性的在线感知。
"""
```

- [ ] **Step 2: 写 `_budget` 失败测试**

在 `tests/test_poster_data.py` 末尾追加:

```python
from src.poster_data import _budget


def test_budget_scales_with_paper_count_and_caps():
    assert _budget(10) == 220
    assert _budget(20) == 320
    assert _budget(25) == 420
    assert _budget(100) == 420  # 硬上限
```

- [ ] **Step 3: 跑测试,确认失败**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py::test_budget_scales_with_paper_count_and_caps -v`
Expected: FAIL — `ImportError: cannot import name '_budget'`

- [ ] **Step 4: 实现 `_budget`**

在 `src/poster_data.py` 的 `_truncate` 函数之后加:

```python
def _budget(n_papers: int) -> int:
    """Adaptive character budget for poster prose, scaled by paper count."""
    if n_papers >= 23:
        return 420
    if n_papers >= 15:
        return 320
    return 220
```

- [ ] **Step 5: 跑测试,确认通过(含未被 fixture 改动破坏的旧测试)**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py -v`
Expected: PASS(`_budget` 新测试通过;旧测试仍绿,因为保留了其断言依赖的句子)

- [ ] **Step 6: Commit**

```bash
git add tests/_poster_fixtures.py tests/test_poster_data.py src/poster_data.py
git commit -m "test(poster): richer fixture + adaptive _budget

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 多段抽取器 `_extract_block`

**Files:**
- Modify: `src/poster_data.py`
- Test: `tests/test_poster_data.py`

**Interfaces:**
- Consumes: 现有 `_truncate`(句末收尾 + 截断)。
- Produces: `_extract_block(body: str, budget: int) -> str` —— 跳过表格/标题/列表行,拼接多个段落,再 `_truncate(..., budget)`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_poster_data.py`:

```python
from src.poster_data import _extract_block


def test_extract_block_joins_paragraphs_up_to_budget():
    body = "第一段甲乙丙。\n\n第二段丁戊己。\n\n| 表格行 | 不要 |\n\n第三段庚辛壬。"
    out = _extract_block(body, 200)
    assert "第一段甲乙丙" in out
    assert "第二段丁戊己" in out
    assert "表格行" not in out          # 跳过表格行
    assert len(out) > len("第一段甲乙丙。")  # 比单段更厚


def test_extract_block_respects_budget():
    body = "。".join(f"句子{i}" for i in range(50)) + "。"
    out = _extract_block(body, 60)
    assert len(out) <= 62  # budget + 收尾标点容差
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py -k extract_block -v`
Expected: FAIL — `ImportError: cannot import name '_extract_block'`

- [ ] **Step 3: 实现 `_extract_block`**

在 `src/poster_data.py` 的 `_budget` 之后加:

```python
def _extract_block(body: str, budget: int) -> str:
    """Join non-table/heading/list paragraphs, then truncate to budget at a
    sentence boundary. Richer than _first_para (which took only one paragraph)."""
    paras = []
    for para in re.split(r"\n\s*\n", body or ""):
        p = para.strip()
        if p and p[0] not in "|#-!":
            paras.append(p)
    joined = " ".join(paras).strip()
    return _truncate(joined, budget)
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py -k extract_block -v`
Expected: PASS(2 个)

- [ ] **Step 5: Commit**

```bash
git add tests/test_poster_data.py src/poster_data.py
git commit -m "feat(poster): _extract_block multi-paragraph extractor

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `extract_highlight` 改为启发式选最有冲击力的一句

**Files:**
- Modify: `src/poster_data.py`(`extract_highlight` 重写 + 新增 `_TREND_RE`、`_sentences`)
- Test: `tests/test_poster_data.py`(更新现有 `test_extract_highlight_is_first_conclusion_sentence`)

**Interfaces:**
- Produces: `_sentences(text: str) -> list[str]`、模块级 `_TREND_RE`。
- Changes: `extract_highlight(review_summary)` 现在返回**含趋势/数字标记最多的句子**(并列取最早),来源优先 结论/总结/趋势/未来/展望,回退 对比,再回退末节。

- [ ] **Step 1: 更新现有 highlight 测试为新行为(失败)**

在 `tests/test_poster_data.py` 中,把现有的:

```python
def test_extract_highlight_is_first_conclusion_sentence():
    hl = extract_highlight(SAMPLE_REVIEW)
    assert hl.startswith("本综述梳理")
    assert hl.endswith("。")
```

替换为:

```python
def test_extract_highlight_picks_most_impactful_sentence():
    hl = extract_highlight(SAMPLE_REVIEW)
    # 含"未来/突破/融合"三个趋势词的那句,胜过仅含"关键"的首句
    assert "深度融合" in hl
    assert "本综述梳理" not in hl
    assert hl.endswith("。")
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py::test_extract_highlight_picks_most_impactful_sentence -v`
Expected: FAIL — 旧实现返回首句"本综述梳理…",`"深度融合" in hl` 为 False

- [ ] **Step 3: 重写 `extract_highlight`**

在 `src/poster_data.py` 中,把现有 `extract_highlight` 整体替换为(并在其上方加 `_TREND_RE` 与 `_sentences`):

```python
_TREND_RE = re.compile(r"[0-9０-９%％]|首次|显著|大幅|主流|趋势|普遍|一致|未来|融合|突破|核心|关键")


def _sentences(text):
    return [s.strip() for s in re.findall(r".+?[。！？]", text or "") if s.strip()]


def extract_highlight(review_summary):
    secs = _sections(review_summary)
    body = (_find(secs, ["结论", "总结", "趋势", "未来", "展望"])
            or _find(secs, ["对比"])
            or (secs[-1][1] if secs else review_summary))
    sents = _sentences(body)
    if not sents:
        return (_first_para(body)[:60]).strip()
    best_i, best_score = 0, -1
    for i, s in enumerate(sents):
        score = len(_TREND_RE.findall(s))
        if score > best_score:
            best_score, best_i = score, i
    return sents[best_i]
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py -k highlight -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_poster_data.py src/poster_data.py
git commit -m "feat(poster): extract_highlight picks most impactful sentence

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `select_excerpts` 做厚换源去重 + `build_lineage_excerpt`

**Files:**
- Modify: `src/poster_data.py`(`select_excerpts` 重写 + 新增 `build_lineage_excerpt`)
- Test: `tests/test_poster_data.py`(更新现有 `test_select_excerpts_finds_background_and_conclusion`,新增 lineage 测试)

**Interfaces:**
- Consumes: `_extract_block`(Task 2)、`_budget`(Task 1)、`extract_highlight`(Task 3)、`Excerpt`、`_sections`、`_find`。
- Changes: `select_excerpts(review_summary, budget=220, exclude="")` —— 背景取自「研究背景/引言」,核心结论取自「对比」(回退 结论/末节),按 `budget` 做厚,并从结论文本中剔除 `exclude`(去重)。
- Produces: `build_lineage_excerpt(review_summary, budget=220) -> Excerpt | None` —— 取自「算法演进脉络」(回退「方法分类」);缺失返回 None。

- [ ] **Step 1: 更新/新增测试(失败)**

在 `tests/test_poster_data.py` 中,把现有:

```python
def test_select_excerpts_finds_background_and_conclusion():
    ex = select_excerpts(SAMPLE_REVIEW)
    assert len(ex) == 2
    assert "KV Cache 技术应运而生" in ex[0].text
    assert "深度融合" in ex[1].text
    assert "结论" in ex[1].source
```

替换为:

```python
def test_select_excerpts_thicker_and_deduped():
    ex = select_excerpts(SAMPLE_REVIEW, budget=320, exclude="未来的突破将更依赖多种优化技术的深度融合、对任务动态特性的在线感知。")
    assert len(ex) == 2
    assert "KV Cache 技术应运而生" in ex[0].text
    assert len(ex[0].text) > 150                 # 做厚:超过旧的 150 截断
    assert "量化类方法" in ex[1].text             # 核心结论换源到「横向对比」
    assert "深度融合" not in ex[1].text           # 去重:highlight 那句不重复出现


def test_build_lineage_excerpt_from_section_and_fallback_none():
    from src.poster_data import build_lineage_excerpt
    ex = build_lineage_excerpt(SAMPLE_REVIEW, budget=320)
    assert ex is not None
    assert "演进" in ex.heading
    assert "自注意力" in ex.text or "FlashAttention" in ex.text
    # 没有演进脉络/方法分类节 -> None
    assert build_lineage_excerpt("# 标题\n\n## 引言\n\n正文。") is None
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py -k "thicker or lineage" -v`
Expected: FAIL — `cannot import name 'build_lineage_excerpt'`,且旧 `select_excerpts` 不接受 `budget/exclude` 参数

- [ ] **Step 3: 重写 `select_excerpts` + 新增 `build_lineage_excerpt`**

在 `src/poster_data.py` 中,把现有 `select_excerpts` 整体替换为以下两个函数:

```python
def select_excerpts(review_summary, budget=220, exclude=""):
    secs = _sections(review_summary)
    bg = (_find(secs, ["研究背景", "背景", "摘要", "引言", "问题定义"])
          or (secs[0][1] if secs else review_summary))
    cc = (_find(secs, ["对比", "趋势"])
          or _find(secs, ["结论", "总结"])
          or (secs[-1][1] if secs else review_summary))
    bg_text = _extract_block(bg, budget)
    cc_text = _extract_block(cc, budget)
    if exclude:
        cc_text = re.sub(r"\s{2,}", " ", cc_text.replace(exclude, "")).strip()
    return [
        Excerpt("研究背景与问题定义", "Background · 摘要节选",
                "— 节选自综述「研究背景 / 摘要」", bg_text),
        Excerpt("核心结论与趋势", "Key Findings · 对比与结论",
                "— 节选自综述「横向对比 / 结论」", cc_text),
    ]


def build_lineage_excerpt(review_summary, budget=220):
    secs = _sections(review_summary)
    body = (_find(secs, ["演进脉络", "脉络", "演进"])
            or _find(secs, ["方法分类", "方法体系", "分类"]))
    if not body:
        return None
    text = _extract_block(body, budget)
    if not text:
        return None
    return Excerpt("算法演进脉络", "Lineage Narrative · 演进叙述",
                   "— 节选自综述「算法演进脉络」", text)
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py -k "excerpt or lineage or thicker" -v`
Expected: PASS(含兜底测试 `test_select_excerpts_fallback_when_no_sections` 仍绿)

- [ ] **Step 5: Commit**

```bash
git add tests/test_poster_data.py src/poster_data.py
git commit -m "feat(poster): thicker deduped excerpts + lineage extractor

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `PosterData.lineage` + `build_poster_data` 接线(自适应 + 去重)

**Files:**
- Modify: `src/poster_data.py`(`PosterData` 加字段;`build_poster_data` 重写)
- Test: `tests/test_poster_data.py`(更新 `test_build_poster_data_full`)

**Interfaces:**
- Consumes: `_budget`、`extract_highlight`、`select_excerpts(..., exclude=)`、`build_lineage_excerpt`。
- Produces: `PosterData.lineage: Excerpt | None = None`;`build_poster_data(topic, review_summary, papers, graph)` 用 `n=len(papers)` 算 budget,先取 highlight 再据其去重抽取,并填 lineage。

- [ ] **Step 1: 更新 `test_build_poster_data_full`(失败)**

把现有:

```python
def test_build_poster_data_full():
    papers = [_P(True)] * 4
    d = build_poster_data("我的主题", SAMPLE_REVIEW, papers, _sg())
    assert d.title == "我的主题"
    assert len(d.stats) == 4 and len(d.excerpts) == 2
    assert len(d.taxonomy) == 4 and len(d.tradeoff.rows) == 3
    assert d.highlight and d.foot_left
```

替换为:

```python
def test_build_poster_data_full():
    papers = [_P(True)] * 25  # 大评论:走 420 预算
    d = build_poster_data("我的主题", SAMPLE_REVIEW, papers, _sg())
    assert d.title == "我的主题"
    assert len(d.stats) == 4 and len(d.excerpts) == 2
    assert len(d.taxonomy) == 4 and len(d.tradeoff.rows) == 3
    assert d.highlight and d.foot_left
    assert d.lineage is not None and "演进" in d.lineage.heading
    # highlight 不在核心结论里(去重)
    assert d.highlight not in d.excerpts[1].text
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py::test_build_poster_data_full -v`
Expected: FAIL — `PosterData` 无 `lineage` 属性 / `build_poster_data` 未填 lineage

- [ ] **Step 3: 加 `PosterData.lineage` + 重写 `build_poster_data`**

在 `src/poster_data.py`,`PosterData` 的字段里(`tradeoff: Tradeoff` 之后、`foot_left` 之前)加:

```python
    lineage: object = None  # Excerpt | None
```

并把 `build_poster_data` 整体替换为:

```python
def build_poster_data(topic, review_summary, papers, graph):
    n = len(papers)
    budget = _budget(n)
    highlight = extract_highlight(review_summary)
    return PosterData(
        title=topic,
        stats=build_stats(graph, papers),
        highlight=highlight,
        excerpts=select_excerpts(review_summary, budget, exclude=highlight),
        lineage=build_lineage_excerpt(review_summary, budget),
        taxonomy=build_taxonomy(graph),
        tradeoff=build_tradeoff(review_summary, graph),
    )
```

- [ ] **Step 4: 跑测试,确认通过(整文件)**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_data.py -v`
Expected: PASS(全部)

- [ ] **Step 5: Commit**

```bash
git add tests/test_poster_data.py src/poster_data.py
git commit -m "feat(poster): wire adaptive budget + lineage into build_poster_data

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 渲染演进脉络板块(Fig.1 正下方)

**Files:**
- Modify: `src/poster_render.py`(`render_poster_html` 插入 lineage 块;`_STYLE` 加 `.lineage`)
- Test: `tests/test_poster_render.py`

**Interfaces:**
- Consumes: `PosterData.lineage`(Task 5)、现有 `_excerpt`。
- Changes: `render_poster_html` 在 `figwrap` 与 `highlight` 之间渲染 `data.lineage`(存在时),为 None 时不渲染。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_poster_render.py`(若无该文件则创建,头部加 `from tests._poster_fixtures import sample_graph` 等;本仓库已存在该文件,直接追加):

```python
def test_render_includes_lineage_block_when_present():
    from src.poster_data import build_poster_data
    from src.poster_render import render_poster_html
    from tests._poster_fixtures import sample_graph, SAMPLE_REVIEW

    class _P:
        has_code = True
        year = 2024

    d = build_poster_data("T", SAMPLE_REVIEW, [_P()] * 25, sample_graph())
    html = render_poster_html(d, "<svg></svg>")
    assert "算法演进脉络" in html               # 渲染了新板块
    assert html.index("算法演进脉络") < html.index('class="highlight"')  # 在金句之前(图正下方)


def test_render_omits_lineage_block_when_none():
    from src.poster_render import render_poster_html
    from src.poster_data import build_poster_data
    from tests._poster_fixtures import sample_graph

    class _P:
        has_code = True
        year = 2024

    # 综述没有演进脉络/方法分类节 -> lineage is None
    d = build_poster_data("T", "# 标题\n\n## 引言\n\n背景正文。\n\n## 结论\n\n结论正文。",
                          [_P()] * 4, sample_graph())
    html = render_poster_html(d, "<svg></svg>")
    assert d.lineage is None
    assert "Lineage Narrative" not in html
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/test_poster_render.py -k lineage -v`
Expected: FAIL — 当前 HTML 不含演进脉络块

- [ ] **Step 3: 实现渲染**

(3a) 在 `src/poster_render.py` 的 `_STYLE` 里,`/* serif highlight ... */` 规则之后加一行:

```python
  .lineage{margin-top:22px;}
```

(3b) 在 `render_poster_html` 中,把:

```python
<div class="figwrap">{hero_svg}<div class="caption">Fig. 1 — Method Evolution Timeline</div></div>
<div class="highlight">"{_esc(data.highlight)}"</div>
```

替换为:

```python
<div class="figwrap">{hero_svg}<div class="caption">Fig. 1 — Method Evolution Timeline</div></div>
{('<div class="lineage">' + _excerpt(data.lineage) + '</div>') if getattr(data, "lineage", None) else ''}
<div class="highlight">"{_esc(data.highlight)}"</div>
```

- [ ] **Step 4: 跑测试,确认通过 + 全量回归**

Run: `/opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 -m pytest tests/ -q`
Expected: PASS — 仅余 2 个预先存在、与本任务无关的失败(见 Global Constraints),无新增失败。

- [ ] **Step 5: Commit**

```bash
git add tests/test_poster_render.py src/poster_render.py
git commit -m "feat(poster): render lineage narrative block under Fig.1

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** ① 四块文字来源/处理 → Task 3(highlight)、Task 4(背景/结论 + lineage)。② 新板块位置 figwrap 下方 → Task 6。③ 自适应 `_budget` → Task 1 + 接线 Task 5。④ 容错(缺节回退/空输入)→ `select_excerpts`/`build_lineage_excerpt` 的 `or` 回退 + Task 6 的 None 分支测试。⑤ 改动文件 `poster_data.py`/`poster_render.py`/测试 → 全覆盖。去重 → Task 4 `exclude` + Task 5 断言。全部覆盖。

**Placeholder scan:** 无 TBD/“类似 Task N”;每步含真实代码与命令。

**Type consistency:** `_budget(int)->int`、`_extract_block(str,int)->str`、`extract_highlight(str)->str`、`select_excerpts(str,int,str)->list[Excerpt]`、`build_lineage_excerpt(str,int)->Excerpt|None`、`PosterData.lineage` 在 Task 4/5 定义并在 Task 5/6 使用,一致。`_sentences`/`_TREND_RE` 在 Task 3 定义、Task 3 使用。
