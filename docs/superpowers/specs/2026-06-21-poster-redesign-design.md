# 海报生成重构 — GUI 嵌入式「图文并茂」学术海报

> Spec · 2026-06-21 · branch `feat/poster-optimization` (基于 `feat(figure1)` commit `17af1b0`)
> 视觉基准: [`docs/reference/poster_redesign_mockup.html`](../../reference/poster_redesign_mockup.html)（即 brainstorm 中确认的 v3）

## 1. 背景与问题

当前海报由 [`src/svg_poster_generator.py`](../../../src/svg_poster_generator.py) 生成（管线入口 [`src/agents.py`](../../../src/agents.py) 调 `generate_svg_poster`）：它把综述 **全文 markdown 原样铺进**一张超长 SVG（标题 + 摘要 + 全部章节 + 统计 + top 论文 + 15 行论文表），经 cairosvg 转 PNG。结果信息密度极高、无版面结构、纯文字堆砌。

目标：把海报重做成 **一张竖版、可嵌入 ReviewMaker GUI、图文并茂、结构清晰、信息密度低**的学术海报，内容**源自已生成的综述报告**。海报的唯一标准：以图片 + 结构化形式生动展现综述内容。

## 2. 已锁定的设计决策（brainstorm 产出）

| # | 决策 | 取值 |
|---|------|------|
| D1 | 形态 | 单视图 **竖版 A 系列** 海报 |
| D2 | 视觉系统 | **DESIGN.md（GUI 系统）整合**：暖灰底 `#F6F5F3` + 白色 surface 卡片 + 克制紫色 accent `#6D5DF6`；内容排版沿用编辑风（Jost / Lora / JetBrains Mono + 1px 发丝线）。〔注：因海报需嵌入 GUI，从最初的纯 Ivory Ledger 调整为 DESIGN.md 背景 + 编辑风内容的融合〕 |
| D3 | 内容 | **图文并茂**：可视化 + **1~2 段综述原文节选**穿插 |
| D4 | 内容选取 | **demo 级简单截取**（直接切取段落，如 摘要/研究背景 + 结论），**不做严格 LLM 筛选** |
| D5 | 渲染 | **HTML/CSS 编排（内嵌 figure1 静态 SVG）→ Playwright 栅格化 PNG/PDF**；静态、非交互、高分辨率，Web 字体保真。理由见 §6（已确认）。 |
| D6 | hero | **figure1 里程碑谱系图**为视觉主角（复用 `figure1_render`） |
| D7 | 辅助可视化 | **方法体系分类（柱状）** + **横向对比（矩阵）** 两个 |

## 3. 版面结构（自上而下，对应 v3 mockup）

```
┌─────────────────────────────────────────────┐
│ chrome:  ReviewMaker·文献综述海报  |  AUTO-GEN·date │  mono
│ ───────────────────────────────────────────── │  hairline
│ kicker (紫, mono):  ALGORITHM LINEAGE·算法演进谱系 │
│ TITLE (Jost300 / CJK500):  <综述 topic>          │
│ ▌ 36px 紫色 rule                                │
│ STATS:  15 论文 | 80% 开源 | 3 谱系 | 9 跨年      │  4× stat-cell
│ ┌─ figwrap (白卡, border, radius) ───────────┐  │
│ │   HERO: figure1 lineage SVG (embed mode)   │  │
│ │   caption (mono)                           │  │
│ └────────────────────────────────────────────┘  │
│ ▌ serif highlight: “<结论一句话>”  (Lora, 紫左线) │
│ band1:  [研究背景 摘要节选 prose] | [分类柱]      │  图文穿插
│ ───────────────────────────────────────────── │
│ band2:  [横向对比 矩阵] | [核心结论 结论节选 prose] │  图文穿插
│ ───────────────────────────────────────────── │
│ chrome foot:  文献综述 Agent·DeepSeek | OpenAlex │  mono
└─────────────────────────────────────────────┘
```

DESIGN.md 落点：页面 `--bg` + 顶部淡紫径向光；海报 = `--surface` 白卡（圆角 `--radius-xl`、`--border`、`--shadow-lg`）；紫色 accent 仅用于 kicker / 首条 stat 顶线 / 首个分类柱 / 谱系图爆发期节点 / 矩阵符号 / prose 左线 / highlight 左线。

## 4. 数据 → 版面 映射

所有内容从 **已生成的综述 + 已构建的 `MilestoneGraph`** 派生（**复用** figure1 步骤已 build 的 graph，不重复构建）：

| 版面槽位 | 来源 | 处理 |
|---------|------|------|
| Title | `topic` | 直接 |
| Stats（4） | `graph.metrics` / `papers` | 论文数、含代码占比、`len(graph.branches)`、年份跨度 |
| Hero 谱系图 | `MilestoneGraph` | `render_figure1_svg(graph, embed=True)`（见 §5） |
| Serif highlight | 综述「结论」节 | 取首句（demo：正则定位 `## ...结论`，切首句） |
| 背景 prose 节选 | 综述「摘要/研究背景」节 | 取首段（demo：定位章节，切第一非空段，截断到 ~140 字） |
| 结论 prose 节选 | 综述「结论」节 | 取一段（同上） |
| 分类柱 | `graph.branches` + 各 branch milestone 计数（含 Foundational） | 计数 → 条宽归一化 |
| 横向对比矩阵 | 维度固定（性能·效率 / 可复现 / 适用场景）；每类评级 | demo 级：从「横向对比」节做轻量启发式映射；缺失时给默认。**不做严格 LLM 判定** |

**章节定位**：综述为带 `## 一、… ## 九、…` 的中文 markdown。用容错匹配（关键词「摘要/研究背景」「结论」「横向对比」），定位失败时回退到「正文首段 / 末段」，保证任何综述都能出图文。

## 5. 组件设计（小而隔离，各自可测）

| 单元 | 职责 | 接口 | 依赖 |
|------|------|------|------|
| `poster_data.py` | 纯数据装配，无 IO/无渲染 | `build_poster_data(topic, review_summary, papers, graph) -> PosterData`；内含 `select_excerpts(review_summary)`、`build_taxonomy(graph)`、`build_tradeoff(review_summary, graph)` | models |
| `poster_render.py` | 纯字符串模板，DESIGN.md tokens；内嵌 hero SVG | `render_poster_html(data: PosterData, hero_svg: str) -> str` | 无 |
| `poster_rasterize.py` | 唯一接触浏览器的单元 | `rasterize(html: str, png_path, pdf_path=None) -> dict` (Playwright) | playwright |
| `figure1_render.py` | hero 复用 + **新增 embed 模式** | `render_figure1_svg(graph, embed=False)`：`embed=True` 时去掉自带 kicker/title/footer chrome，仅出谱系图本体（海报另给标题/页脚） | 现成 |
| `poster_generator.py`（重构/新入口） | 编排 data→render→rasterize | `generate_poster(topic, review_summary, papers, graph, out_dir) -> {html, png, pdf}` | 上述 |
| `agents.py` | 管线集成 | 用 `generate_poster(...)` 取代 `generate_svg_poster(...)`，**透传 figure1 步骤已建的 graph** | — |

`PosterData`（dataclass）：`title, stats: list[Stat], highlight: str, excerpts: list[Excerpt(heading, source, text)], taxonomy: list[TaxonomyBar(name_zh, name_en, count, accent)], tradeoff: Tradeoff(dims, rows), foot_left, foot_right`。

> 上表组件名假定 §6 推荐的 HTML 路线（`render_poster_html`）。若 spec review 改选 SVG 路线，对应改为 `render_poster_svg`，`poster_rasterize` 改为 SVG→PNG，其余单元边界不变。

旧 `svg_poster_generator.py` / PIL `poster_generator.py` 标记为 legacy：管线切到新生成器后保留代码但不再调用；相关旧测试按需退役（见 §7）。

## 6. 渲染决策（已确认 2026-06-21）

**结论：HTML/CSS 编排（内嵌 figure1 静态 SVG）→ Playwright 栅格化 PNG（+ 可选 PDF 矢量）。**

**澄清（回应「减少工作量」）**：figure1 演进图由 `figure1_render.render_figure1_svg(graph)` 以纯 Python 字符串拼装产出**自包含静态 SVG**（无浏览器、无 JS；GUI 点击详情只是 `evolution_nodes.json` 叠加层）。海报**直接内联这段静态 SVG 字符串**即可，零重渲染、零转换——v3 mockup 用 JS 重画只是独立 demo 无后端时的权宜，真实实现不需要。HTML 路线既直接复用该静态 SVG、又用自动排版处理整段 prose（手写 SVG 折行 prose 才是真正费工处），**总工作量最低**，故据「减少工作量」标准选定。

- 理由：海报需 **嵌入 GUI**（GUI 即 HTML，DESIGN.md 玻璃拟态阴影/圆角/径向渐变在 HTML/CSS 天然）；且含 **整段中文 prose**，HTML 自动排版/对齐远优于手写 SVG `<text>` 逐字折行。产物静态、非交互；PDF 即矢量、PNG 高 DPI 即清晰，满足「静态矢量级」诉求。GUI「海报」tab 直接内嵌该 HTML/或其 PNG。
- 与 Q9「SVG 编排」的关系：Q9 选择早于「嵌入 GUI + 图文并茂」两条要求；这两条要求出现后，HTML 明显更省力且效果更好，故建议修订。**若你坚持单文件 SVG 产物**，备选：整张海报手写为一个自包含 SVG（hero 复用 + 辅助可视化用 SVG rect + prose 用现有 SVG 折行逻辑），同样浏览器栅格化——可行但 prose 排版较弱、工作量更大。
- 字体：栅格化时把 HTML/SVG 装进引入 Google Fonts（Jost/Lora/JetBrains Mono/Noto Sans&Serif SC）的页面再截图，保证 `document.fonts.ready` 后渲染。
- 依赖与回退：Playwright 为新增管线依赖（环境已在用）。浏览器不可用时：输出 HTML 并跳过 PNG（warn），不阻断管线。

## 7. 测试策略

- `test_poster_data.py`：给定样例 `MilestoneGraph` + 综述 markdown → 断言 stats 数值、excerpt 切取（含章节缺失回退）、taxonomy 计数、tradeoff 维度。**纯函数、无浏览器、快**。
- `test_poster_render.py`：`render_poster_html` 产物含 title、4 个 stat、hero `<svg`、2 段 excerpt、分类柱、矩阵、foot；无未填充占位。
- `test_figure1_render.py`（扩展）：`embed=True` 不含 kicker/title/footer chrome，仍含节点与分支。
- `test_poster_rasterize.py`：smoke——能生成非空 PNG；`skipif` 无浏览器。
- 集成：`agents.py` 海报步骤调用新生成器（mock rasterize）。
- 既有 figure1/milestone/openalex 测试保持全绿；旧 `svg_poster` 全文版测试若与新管线冲突则退役并注明。

## 8. 风险与边界

- **浏览器依赖**：管线引入 Playwright。缓解：环境已用；提供无浏览器回退（仅 HTML）。
- **节选鲁棒性**：不同综述章节标题/格式差异。缓解：容错匹配 + 首/末段回退；demo 级可接受。
- **自适应版面**：topic 含 >3 谱系 / 超长标题 / 超长 contrib。谱系图本身已支持 N 分支（`lane_y`）；海报槽位固定，prose 截断长度有上限。
- **矩阵评级可信度**：demo 级启发式，非严谨评测；页脚注明「由综述横向对比节归纳」。

## 9. 非目标（YAGNI）

- 交互（点击节点看详情）——属 GUI「演进」tab，非海报。
- 综述全文上海报。
- 严格 LLM 内容筛选 / 多页 / 横版 / 暗色模式 / 国际化。

## 10. 验收

1. 任给一篇已生成综述 + 其 `MilestoneGraph`，产出一张竖版海报（PNG，DESIGN.md 风），版面同 v3：标题/统计/hero 谱系图/serif 高亮/两条图文穿插带/页脚。
2. 海报含 ≥1 段真实综述节选文字 + 谱系图 + 两个辅助可视化。
3. 嵌入 GUI「海报」tab 显示协调（背景/配色随 DESIGN.md）。
4. `pytest` 新增测试全绿，既有 figure1 测试不回归。
```
