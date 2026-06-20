"""Lineage render — draws a year-layered, family-swimlane citation DAG with matplotlib."""

import logging
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from matplotlib.lines import Line2D
import numpy as np

from src.evolution_diagram import FONT_PROPS, CATEGORY_COLORS, _get_category_color
from src.lineage_graph import LineageGraph

logger = logging.getLogger(__name__)


def _node_size(cited_by: int, max_cited: int) -> float:
    lo, hi = 250, 1600
    if max_cited <= 0:
        return lo
    return lo + np.log1p(cited_by) / np.log1p(max_cited) * (hi - lo)


def render_lineage(graph: LineageGraph, topic: str,
                   output_path: str = "output/evolution.png",
                   figsize: tuple = (18, 11), dpi: int = 150) -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    nodes = graph.nodes
    if not nodes:
        ax.text(0.5, 0.5, "无足够引用数据生成谱系图", ha="center", va="center",
                fontproperties=FONT_PROPS, fontsize=16)
        ax.axis("off")
        fig.savefig(output_path, dpi=dpi, facecolor=fig.get_facecolor())
        plt.close(fig)
        return output_path

    # Family swimlanes ordered by earliest year (奠基 tends to sit at the bottom).
    families = defaultdict(list)
    for n in nodes:
        families[n.family].append(n)
    fam_order = sorted(families, key=lambda f: min(n.year for n in families[f]))
    fam_y = {f: i for i, f in enumerate(fam_order)}
    color_map: dict = {}

    years = [n.year for n in nodes if n.year > 0] or [2020, 2024]
    ymin, ymax = min(years), max(years)
    ax.set_xlim(ymin - 1, ymax + 1)
    ax.set_ylim(-0.8, len(fam_order) - 0.2)
    max_cited = max((n.cited_by for n in nodes), default=1)

    # Position each node; stack same (family, year) nodes with a vertical offset.
    pos: dict = {}
    bucket = defaultdict(list)
    for n in nodes:
        bucket[(n.family, n.year)].append(n)
    for (fam, yr), group in bucket.items():
        base_y = fam_y[fam]
        for k, n in enumerate(group):
            off = (k - (len(group) - 1) / 2) * 0.22
            pos[n.key] = (n.year if n.year > 0 else ymin, base_y + off)

    # Family bands.
    for fam, y in fam_y.items():
        color = _get_category_color(fam, color_map)
        ax.axhspan(y - 0.45, y + 0.45, alpha=0.06, color=color, zorder=1)

    # Edges (old -> new) with labels.
    for e in graph.edges:
        if e.src not in pos or e.dst not in pos:
            continue
        x0, y0 = pos[e.src]
        x1, y1 = pos[e.dst]
        arrow = FancyArrowPatch(
            (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12,
            connectionstyle="arc3,rad=0.12", color="#90A4AE", alpha=0.7,
            linewidth=1.2, zorder=3,
        )
        ax.add_patch(arrow)
        if e.label:
            ax.annotate(e.label, ((x0 + x1) / 2, (y0 + y1) / 2),
                        fontsize=7, color="#546E7A", alpha=0.9,
                        fontproperties=FONT_PROPS, ha="center", zorder=4)

    # Nodes.
    for n in nodes:
        x, y = pos[n.key]
        color = _get_category_color(n.family, color_map)
        marker = "D" if n.is_ancestor else "o"
        face = "#FFD54F" if n.is_ancestor else color
        ax.scatter(x, y, s=_node_size(n.cited_by, max_cited), c=face,
                   marker=marker, alpha=0.9, edgecolors="white", linewidth=1.5, zorder=5)
        ax.annotate(n.label, (x, y), textcoords="offset points", xytext=(9, 6),
                    fontsize=7.5, fontproperties=FONT_PROPS, zorder=6)

    ax.set_yticks(list(fam_y.values()))
    ax.set_yticklabels(list(fam_y.keys()), fontsize=11, fontweight="bold", fontproperties=FONT_PROPS)
    ax.set_xticks(list(range(int(ymin), int(ymax) + 1)))
    ax.set_xticklabels([str(y) for y in range(int(ymin), int(ymax) + 1)], fontsize=9)
    ax.grid(axis="x", alpha=0.2, linestyle="--")
    ax.set_title(f"算法演进谱系: {topic}", fontsize=16, fontweight="bold",
                 pad=18, fontproperties=FONT_PROPS)

    legend = [mpatches.Patch(color=_get_category_color(f, color_map), alpha=0.8, label=f)
              for f in fam_order]
    legend.append(Line2D([0], [0], marker="D", color="w", markerfacecolor="#FFD54F",
                         markersize=10, label="奠基论文(被引祖先)"))
    ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(1.01, 1),
              fontsize=8, prop=FONT_PROPS, framealpha=0.9)

    plt.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    logger.info(f"Lineage diagram saved to {output_path}")
    return output_path
