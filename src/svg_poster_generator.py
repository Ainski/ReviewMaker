"""SVG poster generator — creates an academic poster as pure SVG (no PIL dependency).

Uses ``xml.etree.ElementTree`` (stdlib) to produce a self-contained SVG with
embedded images (base64) and CJK-friendly ``<foreignObject>`` text blocks that
let the browser handle word wrapping automatically.
"""

import base64
import dataclasses
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import Paper

logger = logging.getLogger(__name__)

# ===========================================================================
# Canvas
# ===========================================================================
CANVAS_WIDTH = 1600
CANVAS_MIN_HEIGHT = 700

# ===========================================================================
# Colors
# ===========================================================================
BG_COLOR = "#FFFFFF"
HEADER_BG = "#1A237E"
HEADER_FG = "#FFFFFF"
HEADER_ACCENT = "#FFD54F"
SECTION_HEADER_BG = "#283593"
SECTION_HEADER_FG = "#FFFFFF"
TEXT_COLOR = "#1A1A1A"
TEXT_SECONDARY = "#546E7A"
ACCENT_COLOR = "#FF5722"
TABLE_HEADER_BG = "#3949AB"
TABLE_ROW_ALT = "#F0F4FF"
BORDER_COLOR = "#C5CAE9"
CARD_BG = "#F8FAFE"
FOOTER_BG = "#E8EAF6"

FONT_FAMILY = (
    "'Microsoft YaHei', 'SimHei', 'PingFang SC', 'Hiragino Sans GB', "
    "'Noto Sans CJK SC', 'WenQuanYi Zen Hei', sans-serif"
)

# ===========================================================================
# Layout geometry
# ===========================================================================
MARGIN = 40
GAP = 24
FULL_W = CANVAS_WIDTH - 2 * MARGIN                    # full content width
HEADER_H = 110
FOOTER_H = 40
SECTION_GAP = 18

# ===========================================================================
# Font sizes (viewBox px)
# ===========================================================================
TITLE_SIZE = 34
SUBTITLE_SIZE = 16
SECTION_SIZE = 20
BODY_SIZE = 15
SMALL_SIZE = 13
TABLE_SIZE = 12
MINI_SIZE = 11

# ===========================================================================
# SVG element builders
# ===========================================================================

def _attrib(extra: dict | None = None) -> dict:
    base = {"xmlns": "http://www.w3.org/2000/svg"}
    if extra:
        base.update(extra)
    return base


def _rect(x, y, w, h, fill, stroke=None, stroke_width=0) -> ET.Element:
    attr = {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "fill": fill}
    if stroke:
        attr["stroke"] = stroke
        attr["stroke-width"] = str(stroke_width)
    return ET.Element("rect", _attrib(attr))


def _text(x, y, content, *, font_size=BODY_SIZE, fill=TEXT_COLOR,
          anchor="start", bold=False) -> ET.Element:
    style = (f"font-family: {FONT_FAMILY}; font-size: {font_size}px; "
             f"font-weight: {'bold' if bold else 'normal'};")
    el = ET.Element("text", _attrib({
        "x": str(x), "y": str(y), "fill": fill,
        "text-anchor": anchor, "style": style,
    }))
    el.text = content
    return el


def _foreign_div(x, y, w, h, body_html, *, font_size=BODY_SIZE,
                 color=TEXT_COLOR, extra_style="") -> ET.Element:
    """Wrap XHTML in ``<foreignObject>`` for auto-wrapping text."""
    fo = ET.Element("foreignObject", _attrib({
        "x": str(x), "y": str(y), "width": str(w), "height": str(h),
    }))
    style = (f"font-family: {FONT_FAMILY}; font-size: {font_size}px; "
             f"line-height: 1.6; color: {color}; "
             f"width: {w - 8}px; word-wrap: break-word; {extra_style}")
    xhtml = (f'<div xmlns="http://www.w3.org/1999/xhtml" style="{_escape_attr(style)}">'
             f'{body_html}</div>')
    fo.append(ET.fromstring(xhtml))
    return fo


def _section_header(x, y, w, title) -> tuple[ET.Element, int]:
    """Colored section header bar. Returns ``(group, new_y)``."""
    g = ET.Element("g", _attrib())
    bar_h = SECTION_SIZE + 10
    g.append(_rect(x, y, w, bar_h, SECTION_HEADER_BG))
    g.append(_rect(x, y, w, 3, ACCENT_COLOR))
    g.append(_text(x + 16, y + bar_h - 12, title, font_size=SECTION_SIZE,
                   fill=SECTION_HEADER_FG, bold=True))
    return g, y + bar_h + SECTION_GAP


def _img_to_data_uri(path_or_bytes) -> str:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        raw = bytes(path_or_bytes)
    else:
        with open(path_or_bytes, "rb") as f:
            raw = f.read()
    if raw[:4] == b"\x89PNG":
        mime = "image/png"
    elif raw[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    elif raw[:4] == b"GIF8":
        mime = "image/gif"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


# ===========================================================================
# Markdown → XHTML
# ===========================================================================

def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _escape_attr(s: str) -> str:
    return _escape(s)


def _inline_md(text: str) -> str:
    """``**bold**`` → ``<b>bold</b>`` (call AFTER _escape)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _md_table_to_html(lines: list[str]) -> str:
    """Convert markdown table lines to a compact XHTML ``<table>``."""
    header_cells = [c.strip() for c in lines[0].split("|")[1:-1]]
    data_lines = lines[2:] if len(lines) > 2 else []
    ncols = len(header_cells)

    html = (
        f'<table style="border-collapse: collapse; width: 100%; '
        f'font-size: {MINI_SIZE}px; margin: 6px 0; '
        f'table-layout: auto; word-break: break-all;">'
        '<thead><tr>'
    )
    for h in header_cells:
        html += (
            f'<th style="background: {TABLE_HEADER_BG}; color: white; '
            f'padding: 3px 4px; text-align: center; font-size: {MINI_SIZE}px; '
            f'white-space: nowrap;">{_inline_md(_escape(h))}</th>'
        )
    html += '</tr></thead><tbody>'
    for ri, row in enumerate(data_lines):
        cells = [c.strip() for c in row.split("|")[1:-1]]
        # Pad if row has fewer cells than header
        while len(cells) < ncols:
            cells.append("")
        bg = TABLE_ROW_ALT if ri % 2 == 0 else BG_COLOR
        html += f'<tr style="background: {bg};">'
        for cell in cells:
            html += (
                f'<td style="padding: 2px 4px; border: 1px solid {BORDER_COLOR}; '
                f'text-align: left; font-size: {MINI_SIZE}px; '
                f'word-break: break-all;">{_inline_md(_escape(cell))}</td>'
            )
        html += '</tr>'
    html += '</tbody></table>'
    return html


def _md_to_html(text: str, font_size: int) -> str:
    """Convert markdown to XHTML: ``##``, ``**bold**``, ``|tables|``, paragraphs."""
    blocks = text.split("\n\n")
    html_parts = []
    for block in blocks:
        lines = [l for l in block.strip().split("\n") if l.strip()]
        if not lines:
            continue
        first = lines[0]
        rest = lines[1:]

        # Table (all lines contain |)
        if all("|" in l for l in lines) and len(lines) >= 2:
            html_parts.append(_md_table_to_html(lines))
            continue

        # **bold sub-heading** + table (e.g. **第1篇：...** followed by |...| rows)
        if (re.match(r"^\*\*.+\*\*$", first)
                and len(rest) >= 2
                and all("|" in l for l in rest)):
            html_parts.append(
                f'<h4 style="font-size: {font_size + 1}px; color: {HEADER_BG}; '
                f'margin: 5px 0 1px;">{_inline_md(_escape(first))}</h4>'
            )
            html_parts.append(_md_table_to_html(rest))
            continue

        # ## heading
        if first.startswith("## "):
            heading = _inline_md(_escape(first[3:].strip()))
            html_parts.append(
                f'<h3 style="font-size: {font_size + 4}px; color: {HEADER_BG}; '
                f'margin: 5px 0 2px;">{heading}</h3>'
            )
            if rest:
                body = "<br/>".join(_inline_md(_escape(l)) for l in rest)
                html_parts.append(f'<p style="margin: 2px 0; line-height: 1.6;">{body}</p>')
            continue

        # **bold sub-heading**
        if re.match(r"^\*\*.+\*\*$", first):
            sub = _inline_md(_escape(first))
            html_parts.append(
                f'<h4 style="font-size: {font_size + 1}px; color: {HEADER_BG}; '
                f'margin: 5px 0 1px;">{sub}</h4>'
            )
            if rest:
                body = "<br/>".join(_inline_md(_escape(l)) for l in rest)
                html_parts.append(f'<p style="margin: 2px 0; line-height: 1.6;">{body}</p>')
            continue

        # Regular paragraph
        body = "<br/>".join(_inline_md(_escape(l)) for l in lines)
        html_parts.append(f'<p style="margin: 2px 0; line-height: 1.6;">{body}</p>')

    return "".join(html_parts)


# ===========================================================================
# Height estimation
# ===========================================================================

def _est_abstract_height(text: str) -> int:
    """Estimate foreignObject height for the abstract block (CSS 2-column)."""
    chars_per_col = 45      # CJK chars per column line at BODY_SIZE
    body_line_h = BODY_SIZE * 1.45
    tbl_line_h = MINI_SIZE * 1.45

    total_h = 0.0
    for block in text.split("\n\n"):
        blines = [l for l in block.strip().split("\n") if l.strip()]
        if not blines:
            continue
        first = blines[0]
        rest = blines[1:]

        # Pure table
        if all("|" in l for l in blines) and len(blines) >= 2:
            total_h += len(blines) * tbl_line_h + 12
            continue
        # Bold heading + table
        if (re.match(r"^\*\*.+\*\*$", first)
                and len(rest) >= 2
                and all("|" in l for l in rest)):
            total_h += body_line_h * 1.5 + len(rest) * tbl_line_h + 12
            continue
        # ## heading
        if first.startswith("## "):
            total_h += body_line_h * 2
            blines = blines[1:]
        # Bold sub-heading
        if blines and re.match(r"^\*\*.+\*\*$", blines[0]):
            total_h += body_line_h * 1.5
            blines = blines[1:]
        # Body lines
        for line in blines:
            total_h += max(1, -(-len(line) // chars_per_col)) * body_line_h

    # CSS columns halve the height; +5 lines breathing room
    return max(280, int(total_h / 2) + int(body_line_h * 5) + 24)


# ===========================================================================
# Section builders
# ===========================================================================

def _build_header(topic: str, papers: list[Paper]) -> ET.Element:
    g = ET.Element("g", _attrib())
    g.append(_rect(0, 0, CANVAS_WIDTH, HEADER_H, HEADER_BG))
    g.append(_rect(0, HEADER_H - 3, CANVAS_WIDTH, 3, ACCENT_COLOR))

    title_text = f"文献综述: {topic}"
    g.append(_text(CANVAS_WIDTH // 2, 48, title_text,
                   font_size=TITLE_SIZE, fill=HEADER_FG, anchor="middle", bold=True))

    num_code = sum(1 for p in papers if p.has_code)
    yr_min = min((p.year for p in papers if p.year > 0), default=0)
    yr_max = max((p.year for p in papers if p.year > 0), default=0)
    subtitle = (f"{len(papers)} 篇论文 | {num_code} 篇含开源代码 | "
                f"{yr_min}–{yr_max} | {datetime.now().strftime('%Y-%m-%d')}")
    g.append(_text(CANVAS_WIDTH // 2, 88, subtitle,
                   font_size=SUBTITLE_SIZE, fill="#B0BEC5", anchor="middle"))
    return g


def _build_abstract(x, y, w, summary: str) -> tuple[ET.Element, int]:
    """区域: Abstract — full-width with CSS 2-column flow."""
    g, new_y = _section_header(x, y, w, "\U0001F4C4 摘要")
    if summary:
        html = _md_to_html(summary, BODY_SIZE)
        block_h = _est_abstract_height(summary)
        g.append(_foreign_div(x + 10, new_y, w - 20, block_h, html,
                              font_size=BODY_SIZE, color=TEXT_COLOR,
                              extra_style=f"column-count: 2; column-gap: {GAP}px;"))
        new_y += block_h + 12
    return g, new_y


def _build_stats(x, y, w, papers: list[Paper]) -> tuple[ET.Element, int]:
    g, new_y = _section_header(x, y, w, "\U0001F4CA 关键统计")
    num_code = sum(1 for p in papers if p.has_code)
    yr_min = min((p.year for p in papers if p.year > 0), default=0)
    yr_max = max((p.year for p in papers if p.year > 0), default=0)
    total_cites = sum(p.citation_count for p in papers)
    num_cats = len(set(p.method_category for p in papers if p.method_category))
    lines = [
        f"论文: {len(papers)} 篇    代码: {num_code} 篇 ({num_code * 100 // max(len(papers), 1)}%)",
        f"年份: {yr_min}–{yr_max}    引用: {total_cites:,}",
        f"方法类别: {num_cats} 类",
    ]
    for line in lines:
        g.append(_text(x + 10, new_y, line, font_size=SMALL_SIZE))
        new_y += 22
    new_y += 6
    return g, new_y


def _build_top_papers(x, y, w, papers: list[Paper]) -> tuple[ET.Element, int]:
    g, new_y = _section_header(x, y, w, "⭐ 重点论文")
    items = ""
    for p in papers[:5]:
        items += (f'<div style="margin-bottom: 6px;"><b>[{p.first_author} {p.year}]</b> '
                  f'{_escape(p.short_title[:50])}')
        if p.key_innovation:
            items += (f'<br/><span style="color: {TEXT_SECONDARY}; font-size: {MINI_SIZE}px;">'
                      f'    \U0001F4A1 {_escape(p.key_innovation[:70])}</span>')
        items += '</div>'
    h = max(80, len(papers[:5]) * 44 + 12)
    g.append(_foreign_div(x + 8, new_y, w - 16, h, items,
                          font_size=SMALL_SIZE, color=TEXT_COLOR))
    new_y += h + 8
    return g, new_y


def _build_evolution(x, y, w, evo_path: str) -> tuple[ET.Element, int]:
    g, new_y = _section_header(x, y, w, "\U0001F4C8 算法演进")
    if evo_path and os.path.exists(evo_path):
        try:
            data_uri = _img_to_data_uri(evo_path)
            evo_h = min(w * 9 // 16, 200)
            g.append(ET.Element("image", _attrib({
                "x": str(x + 4), "y": str(new_y),
                "width": str(w - 8), "height": str(evo_h),
                "href": data_uri, "preserveAspectRatio": "xMidYMid meet",
            })))
            new_y += evo_h + 8
        except Exception as e:
            logger.warning(f"演进图嵌入失败: {e}")
            g.append(_text(x + 10, new_y + 16, "[无法嵌入]",
                           font_size=SMALL_SIZE, fill="#9E9E9E"))
            new_y += 36
    else:
        g.append(_text(x + 10, new_y + 16, "[无法嵌入]",
                       font_size=SMALL_SIZE, fill="#9E9E9E"))
        new_y += 36
    return g, new_y


def _build_paper_table(x, y, w, papers: list[Paper]) -> tuple[ET.Element, int]:
    """Paper summary table — full-width for readability."""
    g, new_y = _section_header(x, y, w, "\U0001F4CB 论文摘要表")
    rows = papers
    headers = ["#", "论文标题", "年份", "主要创新点", "数据集", "代码"]

    rows_html = '<thead><tr>'
    for h in headers:
        rows_html += f'<th>{h}</th>'
    rows_html += '</tr></thead><tbody>'

    for ri, p in enumerate(rows):
        bg = TABLE_ROW_ALT if ri % 2 == 0 else BG_COLOR
        rows_html += (
            f'<tr style="background: {bg};">'
            f'<td>{ri + 1}</td>'
            f'<td style="text-align: left;">{_escape(p.short_title[:50])}</td>'
            f'<td>{p.year}</td>'
            f'<td style="text-align: left; font-size: {MINI_SIZE}px;">'
            f'{_escape((p.key_innovation or "")[:45])}</td>'
            f'<td style="font-size: {MINI_SIZE}px;">'
            f'{_escape(", ".join(p.datasets_used[:2])) if p.datasets_used else "—"}</td>'
            f'<td style="color: #4CAF50;">{"✓" if p.has_code else "—"}</td></tr>'
        )
    rows_html += '</tbody>'

    css = (
        f"table {{ border-collapse: collapse; width: 100%; "
        f"font-family: {FONT_FAMILY}; font-size: {TABLE_SIZE}px; color: {TEXT_COLOR}; "
        f"table-layout: auto; }}"
        f"th {{ background: {TABLE_HEADER_BG}; color: white; padding: 5px 6px; "
        f"font-size: {TABLE_SIZE}px; text-align: center; white-space: nowrap; }}"
        f"td {{ padding: 4px 5px; border: 1px solid {BORDER_COLOR}; "
        f"text-align: center; vertical-align: middle; }}"
        f"tbody tr:nth-child(even) {{ background: {TABLE_ROW_ALT}; }}"
    )
    html = f"<style>{css}</style><table>{rows_html}</table>"
    tbl_h = (len(rows) + 1) * 28 + 32
    g.append(_foreign_div(x + 6, new_y, w - 12, tbl_h, html,
                          font_size=TABLE_SIZE, color=TEXT_COLOR))
    new_y += tbl_h + 8
    return g, new_y


def _build_paper_figures(x, y, w, figures: list[dict]) -> tuple[ET.Element, int]:
    g, new_y = _section_header(x, y, w, "\U0001F5BC️ 原文图片")
    num_figs = min(len(figures), 6)
    cols = min(num_figs, 3)
    rows = (num_figs + cols - 1) // cols
    fig_w = (w - 16) // cols
    fig_h = 200

    for idx in range(num_figs):
        try:
            fd = figures[idx]
            col = idx % cols
            row = idx // cols
            fx = x + col * fig_w + 4
            fy = new_y + row * fig_h + 4
            g.append(_rect(fx, fy, fig_w - 8, fig_h - 8, CARD_BG,
                           stroke=BORDER_COLOR, stroke_width=2))
            g.append(ET.Element("image", _attrib({
                "x": str(fx + 6), "y": str(fy + 6),
                "width": str(fig_w - 20), "height": str(fig_h - 44),
                "href": _img_to_data_uri(fd["image_bytes"]),
                "preserveAspectRatio": "xMidYMid meet",
            })))
            g.append(_text(fx + 6, fy + fig_h - 16,
                           f"图{idx + 1}: {fd['first_author']} ({fd['year']})",
                           font_size=MINI_SIZE, fill=TEXT_SECONDARY))
        except Exception as e:
            logger.debug(f"嵌入图片 {idx} 失败: {e}")
    new_y += rows * fig_h + 8
    return g, new_y


def _build_footer(footer_y: int) -> ET.Element:
    g = ET.Element("g", _attrib())
    g.append(_rect(0, footer_y, CANVAS_WIDTH, FOOTER_H, FOOTER_BG))
    g.append(_text(CANVAS_WIDTH // 2, footer_y + 26,
                   "文献综述 Agent 工具  |  AI 驱动自动生成  |  基于 DeepSeek 大模型",
                   font_size=MINI_SIZE, fill=TEXT_SECONDARY, anchor="middle"))
    return g


# ===========================================================================
# Snapshot
# ===========================================================================

def _save_input_snapshot(papers, topic, review_summary, evolution_diagram_path,
                         output_path, paper_figures) -> None:
    papers_data = [dataclasses.asdict(p) for p in papers]
    figs_data = None
    if paper_figures:
        figs_data = []
        for fd in paper_figures:
            fd_copy = {k: v for k, v in fd.items() if k != "image_bytes"}
            img_bytes = fd.get("image_bytes")
            fd_copy["image_bytes_base64"] = (
                base64.b64encode(img_bytes).decode("ascii") if isinstance(img_bytes, bytes)
                else None
            )
            figs_data.append(fd_copy)
    snapshot = {
        "topic": topic, "review_summary": review_summary,
        "evolution_diagram_path": evolution_diagram_path,
        "output_path": output_path, "papers": papers_data,
        "paper_figures": figs_data,
    }
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"poster_input_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f"快照已保存: {json_path}")


# ===========================================================================
# Public API
# ===========================================================================

def generate_svg_poster(
    papers: list[Paper],
    topic: str,
    review_summary: str,
    evolution_diagram_path: str,
    output_path: str = "output/poster.svg",
    dpi: int = 200,
    paper_figures: Optional[list[dict]] = None,
) -> str:
    """Generate a self-contained SVG academic poster."""
    logger.info(f"生成 SVG 海报: '{topic}'")

    # Snapshot
    _save_input_snapshot(papers, topic, review_summary, evolution_diagram_path,
                         output_path, paper_figures)

    content_top = HEADER_H + 24
    _x = MARGIN

    svg = ET.Element("svg", _attrib({
        "width": "100%", "height": "100%",
        "viewBox": f"0 0 {CANVAS_WIDTH} {CANVAS_MIN_HEIGHT}",
    }))
    svg.set("xmlns:xlink", "http://www.w3.org/1999/xlink")

    # 1. Header
    svg.append(_build_header(topic, papers))

    # 2. Abstract (full-width, CSS 2-column)
    g_abs, yc = _build_abstract(_x, content_top, FULL_W, review_summary)
    svg.append(g_abs)

    # 3. 3-column row: Stats | Top Papers | Evolution
    col_w = (FULL_W - 2 * GAP) // 3
    c1 = _x
    c2 = _x + col_w + GAP
    c3 = _x + 2 * (col_w + GAP)

    g_stats, y1 = _build_stats(c1, yc, col_w, papers)
    svg.append(g_stats)
    g_top, y2 = _build_top_papers(c2, yc, col_w, papers)
    svg.append(g_top)
    g_evo, y3 = _build_evolution(c3, yc, col_w, evolution_diagram_path)
    svg.append(g_evo)

    yc = max(y1, y2, y3)

    # 4. Paper table (full-width)
    g_tbl, yc = _build_paper_table(_x, yc, FULL_W, papers)
    svg.append(g_tbl)

    # 5. Paper figures (full-width)
    if paper_figures and len(paper_figures) > 0:
        g_fig, yc = _build_paper_figures(_x, yc, FULL_W, paper_figures)
        svg.append(g_fig)

    # 6. Footer
    total_h = yc + FOOTER_H + 10
    svg.append(_build_footer(total_h - FOOTER_H))

    # Finalise
    svg.set("viewBox", f"0 0 {CANVAS_WIDTH} {total_h}")
    svg.insert(0, _rect(0, 0, CANVAS_WIDTH, total_h, BG_COLOR))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    ET.indent(ET.ElementTree(svg), space="  ")
    xml_bytes = ET.tostring(svg, encoding="unicode")
    content = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<!-- Generated by svg_poster_generator -->\n' + xml_bytes)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"SVG 海报已保存: {output_path}")
    return output_path