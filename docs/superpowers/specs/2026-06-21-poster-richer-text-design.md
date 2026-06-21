# 海报文字丰富化 (poster richer text) — Design Spec

**Date:** 2026-06-21
**Branch:** `feat/poster-richer-text` (off `feat/evolution-figure1`)

## 问题

海报的"研究背景"和"核心结论"文字太少且重复,20–25 篇综述时海报显空。根因(`src/poster_data.py`):
- `select_excerpts` 用 `_truncate(_first_para(...), 150)` → 只取章节首段、砍到 150 字。
- `extract_highlight` 取"结论"章节首句,而"核心结论"摘录取同一"结论"章节首段 → 同源重复(那句 LongBench)。
- 全程纯抽取,不调 LLM(里程碑图才用 LLM)。

## 目标

在**不增加任何 LLM 调用**的前提下,让海报文字更厚、不重复、随论文数自适应,并新增一个"算法演进脉络"板块把 centerpiece 谱系图讲活。

## 设计

### 四块文字的来源与处理(全部从综述正文抽取)

| 海报块 | 来源章节(优先级) | 处理 |
|---|---|---|
| 顶部金句 `highlight` | 对比分析 → 结论/总结 → 末节 | 启发式选**最有冲击力的一句**(含数字/百分比/趋势词如 首次/显著/主流/趋势/普遍/一致 优先;否则首句)。此句会从"核心结论"中剔除以去重。 |
| 研究背景 `excerpts[0]` | 引言/研究背景/摘要 → 首节 | 多段抽取至字数预算(不再只取首段、不再砍 150) |
| 核心结论与趋势 `excerpts[1]` | 对比分析 → 结论/总结 → 末节 | 多段抽取至预算,**剔除 highlight 那句**(去重),一段更厚散文 |
| 算法演进脉络 `lineage`(新) | 演进脉络/算法演进脉络 → 方法分类(回退) | 多段抽取至预算;该章节缺失则为 None(板块省略) |

### 自适应字数预算 `_budget(n_papers)`
- `n ≤ 14` → 220 字;`15 ≤ n ≤ 22` → 320 字;`n ≥ 23` → 420 字(硬上限,防溢出)。
- 抽取器 `_extract_block(body, budget)`:从章节正文按段落累加(跳过表格/标题/列表行,沿用 `_first_para` 的过滤),累计到接近 budget 时在句末(。;！？)收尾。

### 渲染(`src/poster_render.py`)
- 在 `figwrap`(Fig.1)**正下方、`highlight` 之前**插入全宽"演进脉络"块(复用 `.sec-h` + `.excerpt` 样式,仅当 `data.lineage` 存在)。
- 现有 band 布局不变;`excerpts[0]`/`[1]` 索引不变。

### 数据结构(`src/poster_data.py`)
- `PosterData` 新增 `lineage: Excerpt | None = None`。
- `build_poster_data(topic, review_summary, papers, graph)`:`n=len(papers)`;先取 `highlight`,再 `select_excerpts(review_summary, n, exclude=highlight)`,再 `build_lineage_excerpt(review_summary, n)`。

### 容错
- 任一章节缺失 → 回退到指定后备章节或末节;演进脉络缺失 → `lineage=None`,渲染省略该块。空 `review_summary` 不报错。

## 改动文件
- `src/poster_data.py` — `_budget`、`_extract_block`、改写 `select_excerpts`/`extract_highlight`、新增 `build_lineage_excerpt`、`PosterData.lineage`、`build_poster_data`。
- `src/poster_render.py` — 渲染 `lineage` 块。
- `tests/test_poster_data.py`(或现有海报测试)— 见下。

## 测试(poster_data 纯函数,易测)
- 背景/结论比旧版更长(> 150 字阈值,给足正文时)。
- highlight 文本不出现在"核心结论"文本里(去重)。
- 演进脉络从"算法演进脉络"章节抽到;缺失时 `lineage is None`。
- `_budget`:篇数越多预算越大,且 ≤ 硬上限。
- 缺章节/空输入不抛异常。
- 渲染:`data.lineage` 存在时 HTML 含演进脉络块;为 None 时不含。

## 非目标
- 不加 LLM 调用;不改里程碑图/SVG;不改 taxonomy/tradeoff 逻辑;不做复杂分页排版(HTML 自然下流、海报变高即可)。
