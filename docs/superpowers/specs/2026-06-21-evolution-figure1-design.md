# 算法演进图重构 — Figure-1 谱系图 设计文档 (Spec)

> 2026-06-21。替换 ReviewMaker 现有的散点演进图,改为面向「计算机领域前沿研究主题」的 Figure-1 风格里程碑谱系图。
> 分支:`feat/evolution-figure1`,基于 `origin/main`。

---

## 1. 目标与背景

**问题**:现有 `evolution_diagram.py` 是按方法类别分泳道的散点图;`lineage_render.py`(clean-slate)依赖 OpenAlex 引用边,但前沿主题的新预印本在 OpenAlex 里**普遍没有 referenced_works**,导致图退化成无边、无奠基的散点。

**目标**:做一张论文 Figure-1 风格的横向时间轴谱系图 —— 中央奠基主轴沿时间向右,在合适位置**分叉**成多条子主题沿线,每条线上是**精选里程碑**(名+作者+年+一句贡献),关系靠「分支 + 时代 + 先后位置」的**结构**表达(不画论文间连线)。GUI 中点击节点弹出论文详情。

## 2. 已确认决策(全部来自 brainstorm 收敛)

| # | 维度 | 决定 |
|---|------|------|
| 1 | 关系骨架 | **引用 + LLM 混合**:有 OpenAlex 真引用就用真引用作依据,否则由 LLM 从标题/摘要推断演进结构 |
| 2 | 节点粒度 | **精选里程碑**,数量由 LLM 按主题复杂度决定(非写死) |
| 3 | 分叉 | **是**,按子主题分成并行沿线,条数由 LLM 决定;解决「多 query/多关注点」 |
| 4 | 连线 | **不画**论文间连线,关系靠结构(分支 + 时代 + 时间先后) |
| 5 | 产物形态 | **静态 SVG 矢量图**(印刷级,嵌海报);GUI 中为可点击的 inline SVG |
| 6 | 奠基补充 | LLM 提名领域经典奠基作 → **逐篇 OpenAlex 验证存在 + 取真实元数据**后才加入 |
| 7 | 节点信息 | 方法名 + 一作 et al + 年份 + 一句话关键贡献 |
| 8 | 旗标层 | **不要**(与节点贡献重复) |
| 9 | 改动范围 | **完全替换**;新分支基于 origin/main;论文太少时显示「信息不足」 |
| 10 | 交互 | GUI 点击节点 → 图注下方详情面板;**同 (分支,年份) 一个点对应多篇,点击列出全部**;再次点击同节点 → 取消选中 |
| 11 | 视觉风格 | **Ivory Ledger**(docs/design.md)单色编辑风,但**背景用框架白色 surface**(不用米白),贴合 ReviewMaker DESIGN.md,不与框架冲突 |

## 3. 视觉规范(Ivory Ledger × 框架)

- **背景**:`#FFFFFF`(框架 --surface),非米白。整图嵌在框架白卡片内。
- **配色**:纯墨黑单色 —— ink `#171717`、graphite `#55514A`、graphite-light `#96918A`。**分支不用彩色**,靠位置 + 标签区分(与目标检测 Figure-1 一致)。交互「选中」用框架主色 `#6D5DF6`。
- **字体**:方法名 Jost(`Jost, "Noto Sans SC"`,weight 400,混排);作者·年份 JetBrains Mono 大写 + 0.1em tracking,graphite-light;一句贡献 Noto Sans SC,graphite。标题区 kicker 用 Mono,标题用 Jost 细体。
- **线**:主轴与分支均 1px 墨黑细线;fork 用 1px 肘形曲线(cubic)。
- **节点**:timeline-dot —— 4px 实心墨黑圆 + 2px 白色(framework surface)描边环;选中时 6px、填充主色。
- **标签 knockout**:每个标签块下垫一个白色圆角矩形(选中时主色淡背景 `#F0EEFF`),防止文字与线/其他元素混叠。
- **时代分段**:在主轴**最大空白年份段**处擦除主轴线 + 居中 `···`;爆发区用极淡暖白带 `#FAFAF8` 标识;底部居中标注时代名(中文 + Mono 英文)。
- **fork 约束**:第一个分支节点的 x 必须 > 肘形曲线终点(`elbow_end = min(默认宽度, 首节点x − 余量)`),否则节点会浮在曲线上。
- **页脚 chrome**:Mono 小字(FIG.1 — METHOD EVOLUTION TIMELINE / N MILESTONES · K FOUNDATIONAL · B LINEAGES)。

## 4. 数据模型

```python
@dataclass
class Milestone:
    name: str            # 方法简称,如 "FlashAttention"
    authors: str         # 一作 "Dao et al"
    year: int
    branch: str          # 分支 id;"__found__" 表示奠基(在中央主轴)
    contrib: str         # 一句话关键贡献(<= ~24 中文字)
    paper_index: int | None   # 对应检索论文的下标;奠基补充作为 None
    full_title: str
    venue: str
    cited_by: int
    has_code: bool
    abstract: str        # 详情面板用,一两句
    openalex_id: str | None

@dataclass
class Branch:
    id: str              # "A"/"B"/...
    name_zh: str         # "KV Cache 压缩与淘汰"
    name_en: str         # "COMPRESSION / EVICTION"

@dataclass
class Era:
    name_zh: str
    name_en: str
    y0: int
    y1: int

@dataclass
class MilestoneGraph:
    topic: str
    milestones: list[Milestone]
    branches: list[Branch]
    eras: list[Era]
    enough: bool         # False → 渲染「信息不足」占位
    metrics: dict        # 统计:milestone/foundational/branch 计数,openalex 验证率等
```

## 5. 处理管线

```
papers(已检索+排序+extract_paper_details) + topic
        │
        ▼
build_milestone_graph(papers, topic, llm_call, openalex_client)
  1. LLM 规划:从 papers 选里程碑、分配 branch、划分 era、提名奠基经典作
     —— 单次结构化 JSON 输出(milestones/branches/eras/foundational_candidates)
  2. OpenAlex 验证:对 foundational_candidates 逐条解析,存在则取真实
     year/cited_by/title,加入为 branch="__found__" 的 Milestone;解析失败则丢弃
  3. 真引用增强(可选,非阻断):若 papers 已有 referenced_works,用于校正
     里程碑重要度/排序;无则跳过
  4. 组装 MilestoneGraph;若 milestone 数 < 阈值(默认 5)→ enough=False
        │
        ▼
render_figure1_svg(graph) → (svg_str, nodes_json)
  - 计算布局:piecewise x(含最大空白段压缩+断线)、lane 分配、fork 肘形、
    节点上下交错、knockout
  - 输出静态 SVG 字符串 + 一份 nodes_json(节点坐标+论文详情,供 GUI 交互)
        │
        ├── 写 evolution.svg(静态,供海报)
        ├── 写 evolution_nodes.json(供 GUI 交互渲染)
        └── svg_poster_generator 嵌入 evolution.svg
```

## 6. 集成与产物

- `gui_app.py`:Step 5 用 `build_milestone_graph` + `render_figure1_svg` 替换 `generate_evolution_diagram`;产出 `evolution.svg` + `evolution_nodes.json`;`enough=False` 时写占位 SVG(「信息不足:有效里程碑不足,无法构建演进谱系」)。
- `templates/index.html`:演进 Tab 由 `<img>` 改为**内联渲染 SVG**(fetch nodes_json,用前端 JS 画 + 绑定点击),图注下方加详情面板;交互行为同 `figure1_embedded.html` 原型(分组节点、点击弹详情、再次点击取消)。
- `svg_poster_generator.py`:嵌入静态 `evolution.svg`(矢量,无交互)。

## 7. 非目标 / 取舍

- 不画论文间引用连线(决策 4)。
- 不做 matplotlib 渲染(改 SVG)。
- 海报中的图为静态(无交互);交互仅在 GUI。
- 不追求 OpenAlex 全解析;奠基验证失败就丢弃该候选,不阻断主流程。
- 不保留旧散点 `evolution_diagram.py` 作为运行路径(完全替换);但文件可暂留以便回滚,不在 gui 调用。

## 8. 验收标准

1. 对「KV Cache / Flash Attention」主题,生成的 SVG 含:中央奠基主轴、≥2 条分叉子主题、里程碑(名+作者+年+贡献)、最大空白段断线+`···`、时代标注;**无文字压线、无节点浮线**。
2. 奠基节点均来自 OpenAlex 验证通过的经典作。
3. GUI 演进 Tab 点击节点弹出详情;同 (分支,年份) 多篇时全部列出;再次点击取消。
4. 海报正确嵌入静态 SVG。
5. 论文 < 5 篇有效里程碑时显示「信息不足」占位,不崩溃。
6. 全部新单元测试通过。
