# Figure-1 演进谱系图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用面向计算机前沿主题的 Figure-1 横向里程碑谱系图(中央奠基主轴 → 分叉子主题 → 精选里程碑,关系靠结构),完全替换 ReviewMaker 现有散点演进图。

**Architecture:** 数据层 `build_milestone_graph`(LLM 规划里程碑/分支/时代 + OpenAlex 验证奠基)→ 渲染层 `render_figure1_svg`(纯函数布局 + Ivory-Ledger 单色 SVG)→ 产物 `evolution.svg` + `evolution_nodes.json`;GUI 内联渲染 SVG 并支持点击详情;海报嵌入静态 SVG。

**Tech Stack:** Python 3.10+,dataclasses,requests(OpenAlex),OpenAI SDK(DeepSeek,复用现有 llm_call),pytest;前端 vanilla JS + inline SVG。

## Global Constraints

- 分支基于 `origin/main`;分支名 `feat/evolution-figure1`。
- 视觉:Ivory Ledger 单色(ink `#171717` / graphite `#55514A` / graphite-light `#96918A`),**背景 `#FFFFFF`**,交互主色 `#6D5DF6`;字体 Jost / JetBrains Mono / Noto Sans SC。
- 不画论文间连线;关系靠 分支 + 时代 + 时间先后。
- 同 `(branch, year)` 一个点 → 点击列出该位置全部论文。
- fork 肘形终点必须 < 第一个分支节点 x。
- `···` + 断线放在主轴**最大空白年份段**。
- 里程碑有效数 < 5 → `enough=False` → 渲染「信息不足」占位。
- 参考已验证原型:`docs/reference/figure1_embedded_prototype.html`(布局+交互+视觉的事实标准)。
- 测试:`python -m pytest tests/ -v`。每个 Python 任务先写失败测试再实现。
- 提交频繁;commit message 末尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`。

---

### Task 1: 移植 OpenAlex 客户端 + 奠基验证接口

**Files:**
- Create: `src/openalex_client.py`(从 clean-slate 分支移植)
- Create: `tests/test_openalex_client.py`

**Interfaces:**
- Produces: `OpenAlexClient` 类;`OpenAlexWork`(含 `openalex_id, title, year, cited_by_count, referenced_works`);新增方法 `verify_foundational(name_hint: str, year_hint: int|None) -> OpenAlexWork | None`(按标题搜索,返回最匹配且 cited_by 高的 work,失败返回 None)。

- [x] **Step 1: 取得源文件**
  Run: `git show origin/clean-slate:src/openalex_client.py > src/openalex_client.py`(若该 ref 不可用,用 `git show clean-slate:src/openalex_client.py`)。确认文件含 `OpenAlexClient`, `OpenAlexWork`, `_get`, `resolve_work`, `fetch_works_by_ids`, `enrich_papers`。

- [x] **Step 2: 写失败测试**
```python
# tests/test_openalex_client.py
from src.openalex_client import OpenAlexClient, OpenAlexWork

class _FakeResp:
    status_code = 200
    def __init__(self, data): self._d = data
    def json(self): return self._d

def test_verify_foundational_returns_best_match(monkeypatch):
    client = OpenAlexClient()
    payload = {"results": [
        {"id": "https://openalex.org/W1", "display_name": "Attention Is All You Need",
         "publication_year": 2017, "cited_by_count": 130000, "referenced_works": []},
    ]}
    monkeypatch.setattr(client, "_get", lambda path, params: payload)
    w = client.verify_foundational("Attention Is All You Need", 2017)
    assert w is not None and w.year == 2017 and w.cited_by_count == 130000

def test_verify_foundational_none_on_empty(monkeypatch):
    client = OpenAlexClient()
    monkeypatch.setattr(client, "_get", lambda path, params: {"results": []})
    assert client.verify_foundational("Nonexistent Paper XYZ", None) is None
```

- [x] **Step 3: 运行测试确认失败**
  Run: `python -m pytest tests/test_openalex_client.py -v`
  Expected: FAIL（`verify_foundational` 不存在）

- [x] **Step 4: 实现 `verify_foundational`**
  在 `OpenAlexClient` 中加入：
```python
def verify_foundational(self, name_hint, year_hint=None):
    """Search OpenAlex by title; return the best-cited matching work or None."""
    if not name_hint:
        return None
    data = self._get("/works", {
        "search": name_hint,
        "select": "id,display_name,publication_year,cited_by_count,referenced_works",
        "per_page": 5,
    })
    results = (data or {}).get("results") or []
    if not results:
        return None
    def _ok(r):
        if year_hint and r.get("publication_year"):
            return abs(int(r["publication_year"]) - int(year_hint)) <= 2
        return True
    cands = [r for r in results if _ok(r)] or results
    best = max(cands, key=lambda r: r.get("cited_by_count", 0))
    oid = (best.get("id") or "").rsplit("/", 1)[-1]
    return OpenAlexWork(
        openalex_id=oid, title=best.get("display_name", ""),
        year=best.get("publication_year") or 0,
        cited_by_count=best.get("cited_by_count", 0),
        referenced_works=best.get("referenced_works", []) or [],
    )
```
  （若移植来的 `OpenAlexWork` 字段名不同,调整以匹配；保持 dataclass 字段一致。）

- [x] **Step 5: 运行测试确认通过**
  Run: `python -m pytest tests/test_openalex_client.py -v` → PASS

- [x] **Step 6: Commit**
```bash
git add src/openalex_client.py tests/test_openalex_client.py
git commit -m "feat(openalex): port OpenAlex client + add verify_foundational"
```

---

### Task 2: 数据模型

**Files:**
- Create: `src/figure1_models.py`
- Create: `tests/test_figure1_models.py`

**Interfaces:**
- Produces: dataclasses `Milestone, Branch, Era, MilestoneGraph`(字段见 spec §4);`FOUND = "__found__"` 常量。

- [x] **Step 1: 写失败测试**
```python
# tests/test_figure1_models.py
from src.figure1_models import Milestone, Branch, Era, MilestoneGraph, FOUND

def test_models_construct():
    m = Milestone(name="FlashAttention", authors="Dao et al", year=2022, branch=FOUND,
                  contrib="IO-aware 精确注意力", paper_index=None,
                  full_title="FlashAttention: ...", venue="NeurIPS 2022",
                  cited_by=3500, has_code=True, abstract="…", openalex_id="W1")
    g = MilestoneGraph(topic="t", milestones=[m], branches=[Branch("A","压缩","COMPRESSION")],
                       eras=[Era("奠基","FOUNDATIONS",2017,2023)], enough=True, metrics={})
    assert g.milestones[0].branch == FOUND and g.enough is True
```

- [x] **Step 2: 运行确认失败** → `python -m pytest tests/test_figure1_models.py -v` FAIL

- [x] **Step 3: 实现** `src/figure1_models.py`（按 spec §4 的 dataclass 定义,`from dataclasses import dataclass, field`,`FOUND="__found__"`）。

- [x] **Step 4: 运行确认通过** → PASS

- [x] **Step 5: Commit**
```bash
git add src/figure1_models.py tests/test_figure1_models.py
git commit -m "feat(figure1): add milestone graph data models"
```

---

### Task 3: LLM 规划器(选里程碑/分支/时代/奠基候选)

**Files:**
- Create: `src/milestone_planner.py`
- Create: `tests/test_milestone_planner.py`

**Interfaces:**
- Consumes: `papers`(含 `title, first_author, year, method_category, key_innovation, citation_count, abstract, has_code`),`topic`,`llm_call(prompt)->str`。
- Produces: `plan_milestones(papers, topic, llm_call) -> dict`,返回 `{"milestones":[{paper_index,name,branch,contrib}], "branches":[{id,name_zh,name_en}], "eras":[{name_zh,name_en,y0,y1}], "foundational":[{name,year}]}`(已解析的 JSON)。解析容错:截取首个 `{`…末个 `}`。

- [x] **Step 1: 写失败测试**(stub llm_call 返回固定 JSON,断言解析结构)
```python
# tests/test_milestone_planner.py
import json
from src.milestone_planner import plan_milestones

def _fake_llm(_prompt):
    return '前缀```json\n' + json.dumps({
        "milestones":[{"paper_index":1,"name":"Ada-KV","branch":"A","contrib":"自适应 KV 淘汰"}],
        "branches":[{"id":"A","name_zh":"KV Cache 压缩与淘汰","name_en":"COMPRESSION / EVICTION"}],
        "eras":[{"name_zh":"奠基","name_en":"FOUNDATIONS","y0":2017,"y1":2023}],
        "foundational":[{"name":"Attention Is All You Need","year":2017}]
    }) + '\n``` 后缀'

def test_plan_parses_json():
    papers=[type("P",(),{"title":"Ada-KV ...","first_author":"Feng","year":2024,
            "method_category":"系统优化类","key_innovation":"自适应","citation_count":40,
            "abstract":"...","has_code":True})()]
    plan = plan_milestones(papers, "KV Cache", _fake_llm)
    assert plan["branches"][0]["id"] == "A"
    assert plan["foundational"][0]["year"] == 2017
    assert plan["milestones"][0]["paper_index"] == 1
```

- [x] **Step 2: 运行确认失败** → FAIL

- [x] **Step 3: 实现 `plan_milestones`**
  构造 prompt(明确要求:从给定论文里**选里程碑并分配 branch**;branch 数与里程碑数**由模型按主题决定**;给每个里程碑写 <=24 字中文 `contrib`;划分 2–4 个 `eras`;提名 3–8 个**领域公认奠基经典**到 `foundational`,只给 name+year,不编造检索集里的论文;**只输出 JSON**)。把 papers 编号列表(index/title/year/author/category/innovation)放进 prompt。调用 `llm_call`,用 `raw.find('{')`…`raw.rfind('}')+1` 截取并 `json.loads`。异常时返回 `{"milestones":[],"branches":[],"eras":[],"foundational":[]}` 并 log warning。

- [x] **Step 4: 运行确认通过** → PASS

- [x] **Step 5: Commit**
```bash
git add src/milestone_planner.py tests/test_milestone_planner.py
git commit -m "feat(figure1): add LLM milestone/branch/era planner"
```

---

### Task 4: 图组装(奠基验证 + enough 判定 + metrics)

**Files:**
- Create: `src/milestone_graph.py`
- Create: `tests/test_milestone_graph.py`

**Interfaces:**
- Consumes: Task1 `OpenAlexClient.verify_foundational`,Task2 models,Task3 `plan_milestones`。
- Produces: `build_milestone_graph(papers, topic, *, llm_call, client=None, min_milestones=5) -> MilestoneGraph`。

- [x] **Step 1: 写失败测试**(stub `plan_milestones` via monkeypatch + fake client)
```python
# tests/test_milestone_graph.py
import src.milestone_graph as mg
from src.openalex_client import OpenAlexWork
from src.figure1_models import FOUND

class FakeClient:
    def verify_foundational(self, name, year=None):
        if "Attention" in name:
            return OpenAlexWork(openalex_id="W1", title="Attention Is All You Need",
                                year=2017, cited_by_count=130000, referenced_works=[])
        return None  # 解析失败 → 丢弃

def _paper(i):
    return type("P",(),{"title":f"Paper {i}","first_author":f"A{i}","year":2024,
        "method_category":"系统优化类","key_innovation":"x","citation_count":i,
        "abstract":"...","has_code":True,"openalex_id":"","oa_cited_by_count":0})()

def test_build_graph_verifies_foundational_and_enough(monkeypatch):
    papers=[_paper(i) for i in range(1,7)]
    monkeypatch.setattr(mg, "plan_milestones", lambda p,t,l: {
        "milestones":[{"paper_index":i,"name":f"M{i}","branch":"A","contrib":"c"} for i in range(1,7)],
        "branches":[{"id":"A","name_zh":"压缩","name_en":"COMPRESSION"}],
        "eras":[{"name_zh":"奠基","name_en":"F","y0":2017,"y1":2024}],
        "foundational":[{"name":"Attention Is All You Need","year":2017},
                        {"name":"Ghost Paper","year":1999}]})
    g = mg.build_milestone_graph(papers, "KV", llm_call=lambda x:"", client=FakeClient())
    founds=[m for m in g.milestones if m.branch==FOUND]
    assert len(founds)==1 and founds[0].year==2017       # Ghost 被丢弃
    assert g.enough is True                                # 6 里程碑 ≥ 5
    assert g.metrics["num_foundational"]==1
```

- [x] **Step 2: 运行确认失败** → FAIL

- [x] **Step 3: 实现 `build_milestone_graph`**
  - `from src import milestone_graph` 内 `from src.milestone_planner import plan_milestones`(模块级,便于 monkeypatch)。
  - 调 `plan_milestones`;把每个 plan milestone 映射回 `papers[paper_index-1]` 取 full_title/venue/cited_by/has_code/abstract,组装 `Milestone(branch=plan.branch)`。
  - 对 `foundational` 候选逐条 `client.verify_foundational(name, year)`;成功 → 追加 `Milestone(branch=FOUND, name=简称, authors=一作, year=真实年, contrib=简短, full_title=真实标题, cited_by=真实, openalex_id=...)`;失败丢弃。
  - `enough = 有效里程碑数(含奠基) >= min_milestones`。
  - `metrics = {num_milestones, num_foundational, num_branches, openalex_verify_rate}`。
  - venue 来源:paper 若无字段则用 `journal` 或 `f"arXiv {year}"`。

- [x] **Step 4: 运行确认通过** → PASS

- [x] **Step 5: Commit**
```bash
git add src/milestone_graph.py tests/test_milestone_graph.py
git commit -m "feat(figure1): assemble milestone graph with OpenAlex-verified ancestors"
```

---

### Task 5: 布局引擎(纯函数)

**Files:**
- Create: `src/figure1_layout.py`
- Create: `tests/test_figure1_layout.py`

**Interfaces:**
- Produces:
  - `largest_gap(years: list[int]) -> tuple[int,int] | None`(返回最大空白年份段端点,如 (2019,2022);无明显空档返回 None)
  - `group_by_branch_year(milestones) -> dict[(branch,year), list[Milestone]]`
  - `compute_layout(graph, W=1460, H=760, pad=...) -> dict`,返回 `{xs(year)->float, fork_x, elbow_end, lane_y(branch)->float, base_y, gap(None|(gx,)), groups:[{branch,year,x,y,members,side_per_member}]}`,**保证 `elbow_end < min(第一个分支节点 x)`**。

- [x] **Step 1: 写失败测试**(纯逻辑,断言关键不变量)
```python
# tests/test_figure1_layout.py
from src.figure1_layout import largest_gap, group_by_branch_year
from src.figure1_models import Milestone, FOUND

def test_largest_gap():
    assert largest_gap([2017,2019,2022,2023]) == (2019,2022)
    assert largest_gap([2024,2025]) is None     # 无 >=3 年空档

def test_group_by_branch_year():
    ms=[Milestone("FlashInfer","Ye",2025,"B","c",1,"t","v",1,True,"a",None),
        Milestone("LMCache","Liu",2025,"B","c",2,"t","v",1,True,"a",None)]
    g=group_by_branch_year(ms)
    assert len(g[("B",2025)])==2
```

- [x] **Step 2: 运行确认失败** → FAIL

- [x] **Step 3: 实现布局**
  - `largest_gap`:相邻年份差最大且 `>=3` 的区间;否则 None。
  - `group_by_branch_year`:按 `(branch,year)` 聚合。
  - `compute_layout`:
    - 分支顺序:按各分支最早年份排序;`lane_y` 以 base 为中心上下均分(间距随分支数自适应,默认 ~180/对)。
    - `xs`:piecewise —— 把 `largest_gap` 段压缩为窄间隙(放 `···` + 断线),其余年份线性;最右侧爆发区给更多空间;若 `largest_gap` 为 None 则纯线性。
    - `fork_x`:取 奠基最晚年 与 最早分支年 的中点;`elbow_end = min(fork_x + 60, min_branch_node_x - 14)`(确保 < 首分支节点 x)。
    - `groups`:每组算 x=xs(year)、y=lane_y(branch);组内成员 side:1 个用基准侧(按年份组序号交替),多个则一上一下并按 level 错开。
  - 参数与原型 `docs/reference/figure1_embedded_prototype.html` 一致。

- [x] **Step 4: 运行确认通过** → PASS

- [x] **Step 5: Commit**
```bash
git add src/figure1_layout.py tests/test_figure1_layout.py
git commit -m "feat(figure1): pure layout engine (gap detection, lanes, fork, grouping)"
```

---

### Task 6: SVG 渲染器

**Files:**
- Create: `src/figure1_render.py`
- Create: `tests/test_figure1_render.py`

**Interfaces:**
- Consumes: Task5 `compute_layout`,Task2 models。
- Produces: `render_figure1_svg(graph) -> tuple[str, list[dict]]`(svg 字符串 + nodes_json:每个 (branch,year) 组一项,含 x,y,members[论文详情]);`render_insufficient_svg(topic) -> str`。

- [x] **Step 1: 写失败测试**
```python
# tests/test_figure1_render.py
from src.figure1_render import render_figure1_svg, render_insufficient_svg
from src.figure1_models import Milestone, Branch, Era, MilestoneGraph, FOUND

def _graph():
    ms=[Milestone("Transformer","Vaswani",2017,FOUND,"自注意力",None,"Attention...","NeurIPS 2017",130000,True,"a","W1"),
        Milestone("FlashAttention","Dao",2022,FOUND,"IO-aware",None,"Flash...","NeurIPS 2022",3500,True,"a","W2"),
        Milestone("Ada-KV","Feng",2024,"A","自适应淘汰",1,"Ada-KV...","arXiv 2024",40,True,"a",None),
        Milestone("FlashInfer","Ye",2025,"B","引擎",2,"FlashInfer...","MLSys 2025",30,True,"a",None),
        Milestone("LMCache","Liu",2025,"B","缓存层",3,"LMCache...","arXiv 2025",15,True,"a",None)]
    return MilestoneGraph("KV", ms, [Branch("A","压缩","COMP"),Branch("B","系统","SYS")],
                          [Era("奠基","F",2017,2023),Era("爆发","B",2024,2025)], True, {})

def test_render_svg_structure():
    svg, nodes = render_figure1_svg(_graph())
    assert svg.startswith("<svg") and "</svg>" in svg
    assert "Transformer" in svg and "Ada-KV" in svg
    # B,2025 两篇 → nodes 里一项含 2 个 members
    grp=[n for n in nodes if n["branch"]=="B" and n["year"]==2025]
    assert len(grp)==1 and len(grp[0]["members"])==2

def test_insufficient():
    assert "信息不足" in render_insufficient_svg("某冷门主题")
```

- [x] **Step 2: 运行确认失败** → FAIL

- [x] **Step 3: 实现渲染器**
  - 参照 `docs/reference/figure1_embedded_prototype.html` 的 SVG 生成逻辑(spine 两段断线 + `···`、fork 肘形、lane、timeline-dot、knockout 白底标签、时代暖白带 + 底部时代名、页脚 chrome),用 Python 字符串拼 SVG。
  - 颜色/字体按 Global Constraints。背景 `#FFFFFF`。
  - nodes_json:每组 `{branch, year, x, y, members:[{name,authors,year,full_title,venue,cited_by,has_code,abstract,contrib,branch_name,era_name}]}`。
  - `render_insufficient_svg`:白底 + 居中「信息不足:有效里程碑不足,无法构建演进谱系」。

- [x] **Step 4: 运行确认通过** → PASS

- [x] **Step 5: 目视核对(浏览器)**
  写一个临时脚本用真实 `poster_input` 数据跑出 svg 存到 `/tmp/fig1_check.svg`,浏览器打开核对:无文字压线、无节点浮线、`···` 在最大空白段、fork 干净。（用 `run`/playwright skill）

- [x] **Step 6: Commit**
```bash
git add src/figure1_render.py tests/test_figure1_render.py
git commit -m "feat(figure1): SVG renderer + insufficient-data placeholder"
```

---

### Task 7: GUI 管线接入

**Files:**
- Modify: `gui_app.py`（Step 5 演进图段;import）
- Test: `tests/test_gui_pipeline_figure1.py`

**Interfaces:**
- Consumes: Task4 `build_milestone_graph`,Task6 `render_figure1_svg`/`render_insufficient_svg`,现有 `_default_llm_call`(从 clean-slate 移植或在 gui 内构造 DeepSeek client)。
- Produces: 写 `evolution.svg` + `evolution_nodes.json`;job result `files.evolution` 指向 `.svg`,新增 `files.evolution_nodes`。

- [x] **Step 1: 写失败测试**（抽出可测函数 `generate_figure1(papers, topic, job_dir, llm_call, client=None)`）
```python
# tests/test_gui_pipeline_figure1.py
from pathlib import Path
from src.gui_figure1 import generate_figure1   # 见 Step 3:抽到独立模块便于测试
# ... 用 fake llm + fake client(同 Task4)+ 6 篇 fake papers,
# 断言 job_dir 下生成 evolution.svg 与 evolution_nodes.json
```

- [x] **Step 2: 运行确认失败** → FAIL

- [x] **Step 3: 实现**
  - 新建 `src/gui_figure1.py`:`generate_figure1(papers, topic, job_dir, *, llm_call, client=None)` → `build_milestone_graph` → `enough?` → `render_figure1_svg` 或 `render_insufficient_svg` → 写 `evolution.svg`、`evolution_nodes.json`(`json.dump(nodes)`)。返回 graph.metrics。
  - `gui_app.py`:`from src.gui_figure1 import generate_figure1`;Step 5 用它替换 `generate_evolution_diagram(...)`;`evo_path` 改 `evolution.svg`;job result `files.evolution=/output/<id>/evolution.svg`、`files.evolution_nodes=/output/<id>/evolution_nodes.json`。移植 `_default_llm_call`(从 clean-slate `src/lineage_graph.py`)或在 gui 内构造。

- [x] **Step 4: 运行确认通过** → PASS

- [x] **Step 5: Commit**
```bash
git add src/gui_figure1.py gui_app.py tests/test_gui_pipeline_figure1.py
git commit -m "feat(figure1): wire milestone graph + SVG into GUI pipeline"
```

---

### Task 8: 前端内联渲染 + 点击详情

**Files:**
- Modify: `templates/index.html`（演进 Tab 区 + 新增 JS + CSS）

**Interfaces:**
- Consumes: `/output/<job_id>/evolution_nodes.json`(Task7 产物)与 `evolution.svg`。

- [x] **Step 1: 实现**
  - 演进 Tab:把 `<img id="img-evolution">` 改为 `<div id="evo-figure"></div>` + 下方 `<div id="evo-detail" class="detail empty">…</div>`。
  - 加载结果后,fetch `evolution.svg` 内联插入(`#evo-figure`),并 fetch `evolution_nodes.json`;为每个 node 组的 dot(在 svg 中用 `data-key` 标识)绑定点击 → 渲染 `#evo-detail`(单/多篇,toggle 取消),交互逻辑直接移植 `docs/reference/figure1_embedded_prototype.html` 的 `showDetail/clearDetail/分组/toggle`。
  - CSS 移植原型的 `.detail / .badge / .d-*`,使用框架 token。
  - 兼容回退:若无 nodes_json(占位情况),仅显示 SVG。

- [x] **Step 2: 浏览器验证**(run/playwright)
  启动 `python gui_app.py`(本 worktree,改端口避免冲突,如 7862),跑一个主题,演进 Tab:SVG 正常、点击节点弹详情、同位置多篇全列、再次点击取消。

- [x] **Step 3: Commit**
```bash
git add templates/index.html
git commit -m "feat(figure1): inline interactive SVG + click-to-detail in Evolution tab"
```

---

### Task 9: 海报嵌入静态 SVG

**Files:**
- Modify: `src/svg_poster_generator.py`
- Test: `tests/test_poster_embed_svg.py`

- [x] **Step 1: 写失败测试**:用一个最小 `evolution.svg` 调用海报生成,断言输出 SVG 内含演进图内容(或正确引用)。

- [x] **Step 2: 运行确认失败** → FAIL

- [x] **Step 3: 实现**:`generate_svg_poster` 中将原本嵌 png 的位置改为嵌入静态 `evolution.svg`(读取并内联为 `<g>`/`<image>`,或按现有机制)。保持海报为静态。

- [x] **Step 4: 运行确认通过** → PASS

- [x] **Step 5: Commit**
```bash
git add src/svg_poster_generator.py tests/test_poster_embed_svg.py
git commit -m "feat(figure1): embed static evolution SVG into poster"
```

---

### Task 10: 端到端校验 + 清理

- [x] **Step 1:** 全量测试 `python -m pytest tests/ -v` 全绿。
- [x] **Step 2:** 真实跑一个主题(KV Cache / Flash Attention)完整管线,核对 review.md、evolution.svg、poster、GUI 交互。
- [x] **Step 3:** `evolution_diagram.py` 不再被 gui 调用(保留文件以便回滚);确认无悬挂 import。
- [x] **Step 4: Commit**(若有清理)
```bash
git add -A && git commit -m "chore(figure1): end-to-end verification + cleanup"
```

---

## Self-Review 注记
- Spec §5 管线 → Task 3/4/6/7 覆盖;§3 视觉 → Task 5/6/8;§6 集成 → Task 7/8/9;§2 决策 #10 交互 → Task 8;#6 奠基验证 → Task 1/4;#9 信息不足 → Task 6/7。
- 类型一致:`OpenAlexWork`(Task1)→ `build_milestone_graph`(Task4);`MilestoneGraph`(Task2)贯穿 4/5/6/7;`render_figure1_svg` 返回 `(svg, nodes)` 在 6/7/8 一致。
