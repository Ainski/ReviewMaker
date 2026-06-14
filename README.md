# 文献综述 Agent 工具

> AI-Powered Literature Review Agent Tool — 自动抓取最新论文、生成结构化中文综述与可视化图表。

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## ✨ 核心功能

| 功能模块 | 说明 |
|----------|------|
| 🔍 **论文自动抓取** | 从 arXiv + Semantic Scholar 双重搜索，获取指定主题的最新论文元数据（标题/摘要/作者/引用数） |
| 📦 **代码仓库发现** | GitHub API 自动搜索论文关联的开源实现，优先推荐含公开代码的论文 |
| 📊 **智能排序** | 多维度评分（相关性×40% + 代码可用性×30% + 引用数×15% + 新近度×15%）自动筛选高质量论文 |
| 📝 **AI 综述生成** | 基于 DeepSeek 大模型生成结构化中文综述（引言→方法分类→详细分析→对比分析→未来展望），杜绝幻觉 |
| 📎 **引用管理** | 自动生成 BibTeX 参考文献 + 文中 [1][2] 标注 + 引用完整性校验 |
| 📈 **算法演进图** | matplotlib 绘制方法类别时间线图（按年份组织、节点大小表引用量、颜色区分类别） |
| 🎨 **学术海报** | A3 横幅海报（摘要+统计+论文表+演进图），Pillow 300 DPI 输出 |
| 🖥️ **Web GUI** | Flask 前端，美观简洁，左右分栏交互，实时进度反馈 |

## 📁 项目架构

```
Agent_for_Papers/
├── main.py                      # CLI 命令行入口
├── gui_app.py                   # Web GUI (Flask) 入口
├── config.py                    # 全局配置管理（API Key、默认参数）
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
│
├── src/                         # 核心模块
│   ├── models.py                # Paper / Author 数据模型
│   ├── paper_fetcher.py         # arXiv + Semantic Scholar API 论文抓取
│   ├── code_finder.py           # GitHub API 代码仓库匹配
│   ├── paper_ranker.py          # 多维评分排序 + 相关性过滤
│   ├── review_generator.py      # DeepSeek API 综述生成（Prompt Engineering）
│   ├── citation_manager.py      # BibTeX 生成 + 引用验证 + 参考文献列表
│   ├── evolution_diagram.py     # matplotlib 算法演进时间线图
│   └── poster_generator.py      # Pillow A3 学术海报合成
│
├── templates/
│   └── index.html               # Web GUI 前端页面
│
├── tests/                       # 单元测试
│   ├── test_paper_fetcher.py
│   ├── test_review_generator.py
│   └── test_evolution_diagram.py
│
└── output/                      # 输出目录（运行时自动生成）
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
cd Agent_for_Papers

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env 填入 DeepSeek API Key
```

`.env` 内容：
```
DEEPSEEK_API_KEY=sk-xxxxxxxx
GITHUB_TOKEN=              # 可选
SEMANTIC_SCHOLAR_API_KEY=  # 可选
```

### 3. 运行

```bash
# 方式一：命令行
python main.py "Transformer attention mechanisms" --max-papers 15

# 方式二：Web GUI（推荐）
python gui_app.py
# 打开浏览器访问 http://127.0.0.1:5000
```

### CLI 参数说明

```
python main.py <主题> [选项]

选项:
  --max-papers N      最大论文数量（默认: 20）
  --year-range N      年份范围（默认: 5）
  --sort-by {relevance,recency,citations}  排序方式
  --output-dir DIR    输出目录（默认: output）
  --no-code-search    跳过 GitHub 代码搜索
  --no-poster         跳过海报生成
  --model MODEL       DeepSeek 模型（默认: deepseek-chat）
  --verbose, -v       详细日志
```

### 输出文件

运行完成后在 `output/` 目录下生成：

| 文件 | 说明 |
|------|------|
| `review.md` | 中文文献综述（Markdown，含引用标注） |
| `references.bib` | BibTeX 格式参考文献 |
| `evolution.png` | 算法演进时间线图 |
| `distribution.png` | 方法类别分布图 |
| `poster.png` | 学术海报（A3横幅） |

## 🧪 运行测试

```bash
python -m pytest tests/ -v
```

```
============================== 14 passed in 1.10s ==============================
```

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────┐
│                    用户交互层                          │
│   ┌─────────────┐    ┌───────────────────────┐       │
│   │  CLI (main)  │    │  Web GUI (Flask + JS)  │      │
│   └──────┬──────┘    └───────────┬───────────┘       │
├──────────┼───────────────────────┼───────────────────┤
│          │        调度层           │                   │
│          └──────────┬─────────────┘                   │
│                     ▼                                  │
├──────────────────────────────────────────────────────┤
│                   核心处理层                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ 论文抓取  │  │ 代码发现  │  │ 排序与过滤        │   │
│  │ arXiv+SS │→│ GitHub   │→│ 多维评分+去重     │   │
│  └──────────┘  └──────────┘  └────────┬─────────┘   │
│                                        ▼              │
│  ┌──────────────────────────────────────────────────┐ │
│  │             AI 综述生成 (DeepSeek)                 │ │
│  │  • Prompt Engineering (System + User Prompt)      │ │
│  │  • 结构化输出 (引言/方法分类/分析/对比/展望)        │ │
│  │  • 论文详情提取 (JSON 结构化解析)                  │ │
│  └────────────────────┬─────────────────────────────┘ │
│                        ▼                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ 引用管理  │  │ 演进图    │  │ 海报生成          │   │
│  │ BibTeX  │  │ matplotlib│  │ Pillow 合成       │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
├──────────────────────────────────────────────────────┤
│                    外部服务层                          │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐ ┌─────────┐  │
│  │arXiv │ │Sem.  │ │GitHub│ │DeepSeek│ │PaperWith│  │
│  │ API  │ │Scholar│ │ API  │ │  API   │ │Code API │  │
│  └──────┘ └──────┘ └──────┘ └────────┘ └─────────┘  │
└──────────────────────────────────────────────────────┘
```

## 🔑 关键技术

| 技术点 | 实现方案 |
|--------|----------|
| 论文搜索 | arXiv REST API + Semantic Scholar Graph API 双源合并去重 |
| 代码匹配 | GitHub Search API 关键词匹配 + 语义相关性评分 |
| 论文排序 | 加权复合评分公式 `relevance×0.4 + code×0.3 + citations×0.15 + recency×0.15` |
| 综述生成 | DeepSeek Chat API + 双重 Prompt 策略（System Prompt 防幻觉 + User Prompt 结构化输出） |
| 引用管理 | 正则提取文中引用 → 校验索引范围 → 自动生成 BibTeX |
| 演进图 | matplotlib 散点图 + 水平分类底色带 + 对数标度节点尺寸 |
| 海报 | Pillow ImageDraw 直接绘制 + 表格逐行渲染 + 图片嵌入 |

## 📄 License

MIT License
