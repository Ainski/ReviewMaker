"""Evolution diagram module — generates algorithm timeline visualizations."""

import logging
import os
from collections import defaultdict
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import numpy as np

from src.models import Paper

logger = logging.getLogger(__name__)

# ---- Chinese font setup ----
# Try to find a CJK font on the system and set it globally for matplotlib
_CJK_FONT_PATH = None
_CJK_FONT_NAME = None
_candidate_fonts = [
    "/System/Library/Fonts/STHeiti Medium.ttc",         # macOS
    "/System/Library/Fonts/STHeiti Light.ttc",          # macOS
    "/System/Library/Fonts/Hiragino Sans GB.ttc",       # macOS
    "/System/Library/Fonts/Supplemental/Songti.ttc",    # macOS
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",     # Linux
    "C:\\Windows\\Fonts\\msyh.ttc",                     # Windows
    "C:\\Windows\\Fonts\\simhei.ttf",                   # Windows
]

for _fp in _candidate_fonts:
    if os.path.exists(_fp):
        _CJK_FONT_PATH = _fp
        break

# Also search matplotlib's registered font list
if _CJK_FONT_PATH is None:
    for _f in fm.fontManager.ttflist:
        _name = _f.name.lower()
        if any(kw in _name for kw in [
            'heiti', 'hiragino', 'pingfang', 'songti', 'cjk',
            'noto sans cjk', 'wqy', 'microsoft yahei', 'simhei', 'simsun'
        ]):
            _CJK_FONT_PATH = _f.fname
            _CJK_FONT_NAME = _f.name
            break

# Register the font and configure matplotlib
if _CJK_FONT_PATH is not None:
    try:
        fm.fontManager.addfont(_CJK_FONT_PATH)
        _fp_obj = fm.FontProperties(fname=_CJK_FONT_PATH)
        _CJK_FONT_NAME = _fp_obj.get_name()
    except Exception:
        pass

if _CJK_FONT_NAME is not None:
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = [_CJK_FONT_NAME, 'DejaVu Sans', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False
    FONT_PROPS = fm.FontProperties(fname=_CJK_FONT_PATH)
    logger.info(f"CJK 字体已配置: {_CJK_FONT_NAME} ({_CJK_FONT_PATH})")
else:
    logger.warning("未找到 CJK 字体 — 图表中文可能显示为方块")
    FONT_PROPS = None

# Color palette for method categories
CATEGORY_COLORS = [
    "#2196F3",  # Blue
    "#FF5722",  # Deep Orange
    "#4CAF50",  # Green
    "#9C27B0",  # Purple
    "#FF9800",  # Orange
    "#00BCD4",  # Cyan
    "#E91E63",  # Pink
    "#607D8B",  # Blue Grey
    "#795548",  # Brown
    "#CDDC39",  # Lime
]


def _get_category_color(category: str, color_map: dict[str, str]) -> str:
    """Get consistent color for a method category."""
    if category not in color_map:
        idx = len(color_map) % len(CATEGORY_COLORS)
        color_map[category] = CATEGORY_COLORS[idx]
    return color_map[category]


def _shorten_title(title: str, max_len: int = 60) -> str:
    """Truncate a paper title for display."""
    if len(title) <= max_len:
        return title
    return title[:max_len - 3] + "..."


def generate_evolution_diagram(
    papers: list[Paper],
    topic: str,
    output_path: str = "output/evolution.png",
    figsize: tuple = (18, 10),
    dpi: int = 150,
) -> str:
    """
    Generate an algorithm evolution timeline diagram.

    Shows papers as nodes on a timeline, grouped by method category,
    with citation count represented by node size.

    Args:
        papers: Ranked list of papers
        topic: Research topic
        output_path: Path to save the PNG
        figsize: Figure size (width, height) in inches
        dpi: Resolution

    Returns:
        Path to the generated PNG file
    """
    if not papers:
        logger.warning("No papers to generate evolution diagram")
        return ""

    logger.info(f"Generating evolution diagram: {len(papers)} papers")

    # ---- Data preparation ----
    # Group papers by method category
    categories: dict[str, list[Paper]] = defaultdict(list)
    for p in papers:
        cat = p.method_category or "未分类"
        categories[cat].append(p)

    # Sort categories by average year (older first = bottom)
    cat_avg_years = {}
    for cat, cat_papers in categories.items():
        years = [p.year for p in cat_papers if p.year > 0]
        cat_avg_years[cat] = sum(years) / len(years) if years else 0

    sorted_categories = sorted(cat_avg_years.items(), key=lambda x: x[1])
    category_order = {cat: i for i, (cat, _) in enumerate(sorted_categories)}

    # Color map
    color_map: dict[str, str] = {}

    # ---- Plot ----
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    # Determine year range
    valid_years = [p.year for p in papers if p.year > 0]
    if not valid_years:
        valid_years = [2020, 2024]
    min_year, max_year = min(valid_years), max(valid_years)
    year_padding = max(1, (max_year - min_year) * 0.1)
    ax.set_xlim(min_year - year_padding, max_year + year_padding)
    ax.set_ylim(-1, len(sorted_categories))

    # Size range for nodes (based on citation count)
    max_citations = max((p.citation_count for p in papers), default=1)
    min_size, max_size = 80, 600

    def _node_size(citations: int) -> float:
        if max_citations == 0:
            return min_size
        log_val = np.log1p(citations) / np.log1p(max_citations)
        return min_size + log_val * (max_size - min_size)

    # Draw nodes
    for cat, cat_papers in categories.items():
        y_pos = category_order.get(cat, 0)
        color = _get_category_color(cat, color_map)

        for paper in cat_papers:
            year = paper.year if paper.year > 0 else min_year
            # Add small jitter to y for papers in same category in same year
            same_year_papers = [p for p in cat_papers if p.year == paper.year]
            if len(same_year_papers) > 1:
                idx = same_year_papers.index(paper)
                jitter = (idx - (len(same_year_papers) - 1) / 2) * 0.15
            else:
                jitter = 0

            size = _node_size(paper.citation_count)
            ax.scatter(
                year,
                y_pos + jitter,
                s=size,
                c=color,
                alpha=0.8,
                edgecolors="white",
                linewidth=1.5,
                zorder=5,
            )

            # Label: first author + year
            label = f"{paper.first_author} ({paper.year})"
            ax.annotate(
                label,
                (year, y_pos + jitter),
                textcoords="offset points",
                xytext=(8, 5),
                fontsize=7,
                alpha=0.8,
                fontproperties=FONT_PROPS,
                rotation=20,
            )

    # Draw category bands
    for cat, y_pos in category_order.items():
        color = _get_category_color(cat, color_map)
        ax.axhspan(y_pos - 0.4, y_pos + 0.4, alpha=0.06, color=color, zorder=1)

    # Y-axis: category labels
    ax.set_yticks(list(category_order.values()))
    ax.set_yticklabels(list(category_order.keys()), fontsize=11, fontweight="bold", fontproperties=FONT_PROPS)

    # X-axis: year ticks
    all_years = list(range(int(min_year), int(max_year) + 1))
    ax.set_xticks(all_years)
    ax.set_xticklabels([str(y) for y in all_years], fontsize=9)

    # Grid
    ax.grid(axis="x", alpha=0.2, linestyle="--")
    ax.grid(axis="y", alpha=0.1, linestyle="--")

    # Title
    ax.set_title(
        f"算法演进时间线: {topic}",
        fontsize=16,
        fontweight="bold",
        pad=20,
        fontproperties=FONT_PROPS,
    )

    # Legend for node size
    legend_elements = []
    sizes = [10, 100, 500, 1000]
    for s in sizes:
        if s <= max_citations:
            legend_elements.append(
                Line2D(
                    [0], [0],
                    marker="o",
                    color="w",
                    markerfacecolor="gray",
                    markersize=np.sqrt(_node_size(s)) / 5,
                    label=f"{s} 次引用",
                )
            )

    # Legend for categories
    for cat, color in color_map.items():
        legend_elements.append(
            mpatches.Patch(color=color, alpha=0.8, label=f"类别: {cat}")
        )

    ax.legend(
        handles=legend_elements,
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        fontsize=8,
        framealpha=0.9,
        prop=FONT_PROPS,
    )

    plt.tight_layout()

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    logger.info(f"Evolution diagram saved to {output_path}")
    return output_path


def generate_category_distribution_chart(
    papers: list[Paper],
    output_path: str = "output/category_distribution.png",
) -> str:
    """
    Generate a pie/bar chart showing the distribution of method categories.

    Args:
        papers: List of papers
        output_path: Path to save the chart

    Returns:
        Path to the generated PNG
    """
    if not papers:
        return ""

    from collections import Counter

    cats = Counter(p.method_category or "未分类" for p in papers)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Pie chart
    colors = [CATEGORY_COLORS[i % len(CATEGORY_COLORS)] for i in range(len(cats))]
    wedges, texts, autotexts = ax1.pie(
        cats.values(),
        labels=cats.keys(),
        autopct="%1.1f%%",
        colors=colors,
        startangle=90,
        textprops={'fontproperties': FONT_PROPS} if FONT_PROPS else {},
    )
    ax1.set_title("方法类别分布", fontsize=13, fontweight="bold", fontproperties=FONT_PROPS)

    # Bar chart of papers per year
    years = [p.year for p in papers if p.year > 0]
    if years:
        year_counts = Counter(years)
        year_range = range(min(years), max(years) + 1)
        counts = [year_counts.get(y, 0) for y in year_range]
        bars = ax2.bar(list(year_range), counts, color="#2196F3", alpha=0.7, edgecolor="white")
        ax2.set_xlabel("年份", fontsize=10, fontproperties=FONT_PROPS)
        ax2.set_ylabel("论文数量", fontsize=10, fontproperties=FONT_PROPS)
        ax2.set_title("年度论文分布", fontsize=13, fontweight="bold", fontproperties=FONT_PROPS)
        ax2.set_xticks(list(year_range))
        ax2.set_xticklabels([str(y) for y in year_range], rotation=45)

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return output_path
