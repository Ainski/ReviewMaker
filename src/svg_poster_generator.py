"""SVG poster generator — creates an academic poster as pure SVG.

Uses ``xml.etree.ElementTree`` (stdlib) to produce a self-contained SVG with
embedded images (base64) and ``<text>`` elements with manual word-wrapping
(no ``<foreignObject>``, so cairosvg PNG conversion works correctly).

PNG generation
    If ``generate_png=True`` (default), a PNG is produced alongside the SVG
    using cairosvg.
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

# cairosvg is optional — used for PNG generation
try:
    import cairosvg  # noqa: F401
    _CAIROSVG_OK = True
except Exception as exc:
    _CAIROSVG_OK = False
    cairosvg = None  # type: ignore
    _CAIROSVG_IMPORT_ERROR = exc
else:
    _CAIROSVG_IMPORT_ERROR = None

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
    "'Noto Sans CJK SC', 'WenQuanYi Zen Hei', "
    "'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif"
)

# ===========================================================================
# Layout geometry
# ===========================================================================
MARGIN = 40
GAP = 24
FULL_W = CANVAS_WIDTH - 2 * MARGIN
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

_LINE_SPACING = 1.6


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
          anchor="start", bold=False,
          text_length=None, length_adjust=None) -> ET.Element:
    style = (f"font-family: {FONT_FAMILY}; font-size: {font_size}px; "
             f"font-weight: {'bold' if bold else 'normal'};")
    attr = {
        "x": str(x), "y": str(y), "fill": fill,
        "text-anchor": anchor, "style": style,
    }
    if text_length is not None:
        attr["textLength"] = str(int(text_length))
        attr["lengthAdjust"] = length_adjust or "spacing"
    el = ET.Element("text", attr)
    el.text = content
    return el


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
# Text wrapping (replaces foreignObject — cairosvg-compatible)
# ===========================================================================

# CJK Unicode ranges — characters that are roughly 1 em wide
_CJK_RANGES = [
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0x3400, 0x4DBF),    # CJK Extension A
    (0x20000, 0x2A6DF),  # CJK Extension B
    (0x2A700, 0x2B73F),  # CJK Extension C
    (0x2B740, 0x2B81F),  # CJK Extension D
    (0x2B820, 0x2CEAF),  # CJK Extension E
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0x2F800, 0x2FA1F),  # CJK Compatibility Supplement
    (0x3000, 0x303F),    # CJK Symbols and Punctuation
    (0xFF00, 0xFFEF),    # Halfwidth and Fullwidth Forms
    (0xFE30, 0xFE4F),    # CJK Compatibility Forms
    (0x2E80, 0x2EFF),    # CJK Radicals Supplement
    (0x31C0, 0x31EF),    # CJK Strokes
    (0x3200, 0x32FF),    # Enclosed CJK Letters and Months
    (0x3300, 0x33FF),    # CJK Compatibility
]


def _is_cjk(code: int) -> bool:
    """Return True if *code* is a CJK / full-width Unicode point."""
    for lo, hi in _CJK_RANGES:
        if lo <= code <= hi:
            return True
    return False


def _char_px(ch: str, font_size: int) -> float:
    """Approximate pixel width of a single character.

    CJK / full-width → 1 em; Latin / digits → 1/3 em (user's ratio).
    """
    if _is_cjk(ord(ch)):
        return font_size
    return font_size / 3.0


def _wrap_text(text: str, max_width: int, font_size: int) -> list[tuple[str, bool]]:
    """Wrap text into ``(line_text, is_last_of_para)`` tuples.

    Paragraphs are separated by double newlines (``\\n\\n``).  Only the last
    line of each paragraph is left unjustified.  CJK ≈ 1 em, Latin ≈ 1/3 em.
    10 CJK chars of right margin.
    """
    margin = font_size * 10
    limit = max_width - margin
    if limit < font_size * 3:
        limit = max_width - font_size * 2

    result: list[tuple[str, bool]] = []
    paragraphs = text.split("\n\n")

    for pi, para in enumerate(paragraphs):
        # Collapse whitespace and single newlines within a paragraph
        para = "".join(para.splitlines())
        para = para.strip()
        if not para:
            # Add a blank line spacer between paragraphs
            if pi > 0 and pi < len(paragraphs) - 1:
                result.append(("", False))
            continue

        para_lines: list[str] = []
        current_line: list[str] = []
        current_w = 0.0
        for ch in para:
            cw = _char_px(ch, font_size)
            if current_w + cw > limit and current_line:
                para_lines.append("".join(current_line).strip())
                current_line = []
                current_w = 0.0
            current_line.append(ch)
            current_w += cw
        if current_line:
            para_lines.append("".join(current_line).strip())

        if not para_lines:
            continue

        for i, line in enumerate(para_lines):
            is_last = (i == len(para_lines) - 1)
            result.append((line, is_last))

    return result


def _text_block(x, y, w, text, *, font_size=BODY_SIZE, color=TEXT_COLOR,
                bold=False, max_lines=0,
                justify=True) -> tuple[ET.Element, int]:
    """Render wrapped *text* as ``<text>`` elements.

    Non-terminal lines are justified via SVG ``textLength`` /
    ``lengthAdjust="spacing"`` so the right edge is flush.
    """
    g = ET.Element("g", _attrib())
    pairs = _wrap_text(text, w, font_size)
    if max_lines > 0:
        pairs = pairs[:max_lines]

    # Justification target: column width minus left padding
    justify_target = w - 8 if justify else None

    line_h = int(font_size * _LINE_SPACING)
    for i, (line, is_last) in enumerate(pairs):
        kwargs = {}
        if justify and justify_target and not is_last and len(line) > 5:
            kwargs["text_length"] = justify_target
            kwargs["length_adjust"] = "spacing"
        g.append(_text(x, y + i * line_h + font_size, line,
                       font_size=font_size, fill=color, bold=bold, **kwargs))

    total_h = len(pairs) * line_h
    return g, total_h


def _draw_heading(x, y, w, heading_text, level, font_size) -> tuple[ET.Element, int]:
    """Draw a markdown heading (## or ###) as bold text."""
    g = ET.Element("g", _attrib())
    color = HEADER_BG if level <= 2 else TEXT_COLOR
    fs = font_size + 4 if level <= 2 else font_size + 1
    h, _ = _text_block(x, y, w, heading_text, font_size=fs, color=color, bold=True)
    g.append(h)
    return g, fs * _LINE_SPACING


# ===========================================================================
# Markdown → plain text with bold markers
# ===========================================================================

def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _strip_md(text: str) -> str:
    """Remove markdown formatting, keep plain text."""
    # Remove bold markers
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    # Remove italic markers
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    return text


def _md_text_to_lines(md_text: str) -> list[dict]:
    """Parse markdown into a list of {type, text, level} dicts.

    Types: 'h2', 'h3', 'h4', 'table', 'p', 'blank'
    """
    blocks = md_text.split("\n\n")
    result = []

    for block in blocks:
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            result.append({"type": "blank", "text": "", "level": 0})
            continue

        first = lines[0]
        rest = lines[1:]

        # ## heading
        if first.startswith("## "):
            result.append({"type": "h2", "text": _strip_md(first[3:].strip()), "level": 2})
            if rest:
                body = "\n".join(_strip_md(l) for l in rest)
                result.append({"type": "p", "text": body, "level": 0})
            continue

        # ### heading
        if first.startswith("### "):
            result.append({"type": "h3", "text": _strip_md(first[4:].strip()), "level": 3})
            # Check if rest is a table
            if rest and len(rest) >= 2 and all("|" in l for l in rest):
                result.append({"type": "table", "text": "\n".join(rest), "level": 0,
                               "rows": rest})
            elif rest:
                body = "\n".join(_strip_md(l) for l in rest)
                result.append({"type": "p", "text": body, "level": 0})
            continue

        # Pure table
        if all("|" in l for l in lines) and len(lines) >= 2:
            result.append({"type": "table", "text": "\n".join(lines), "level": 0,
                           "rows": lines})
            continue

        # **bold heading** + table
        if (re.match(r"^\*\*.+\*\*$", first)
                and len(rest) >= 2
                and all("|" in l for l in rest)):
            result.append({"type": "h4", "text": _strip_md(first), "level": 4})
            result.append({"type": "table", "text": "\n".join(rest), "level": 0,
                           "rows": rest})
            continue

        # **bold heading**
        if re.match(r"^\*\*.+\*\*$", first):
            result.append({"type": "h4", "text": _strip_md(first), "level": 4})
            if rest:
                body = "\n".join(_strip_md(l) for l in rest)
                result.append({"type": "p", "text": body, "level": 0})
            continue

        # Regular paragraph
        body = "\n".join(_strip_md(l) for l in lines)
        result.append({"type": "p", "text": body, "level": 0})

    return result


# ===========================================================================
# Table rendering as <text> elements
# ===========================================================================

def _calc_col_widths(ncols: int, headers: list[str],
                     data_lines: list[str], total_w: int,
                     font_size: int) -> list[int]:
    """Calculate adaptive column widths based on content length.

    Narrow columns (≤5 chars: years, counts, checkmarks) get tight fit.
    Wider columns share remaining space proportionally.  Works for any
    number of columns and any column headers.
    """
    char_w = font_size * 0.55
    # Estimate max content width per column (in characters)
    col_max_chars = [0] * ncols
    for ci in range(ncols):
        texts = [headers[ci]] if ci < len(headers) else []
        for row in data_lines:
            cells = [c.strip() for c in row.split("|")[1:-1]]
            if ci < len(cells):
                texts.append(_strip_md(cells[ci]))
        if texts:
            col_max_chars[ci] = max(len(t) for t in texts)
        else:
            col_max_chars[ci] = 3

    # Classify: narrow (≤5 chars, e.g. year, count, checkmark) vs wide
    narrow_mask = [c <= 5 for c in col_max_chars]
    # Narrow cols get content width + minimal padding
    narrow_widths = [int(c * char_w) + 8 for c in col_max_chars]
    narrow_total = sum(w if narrow_mask[i] else 0 for i, w in enumerate(narrow_widths))

    # Remaining width for wide columns
    avail = total_w - narrow_total - ncols * 4  # 4px padding per column
    wide_indices = [i for i in range(ncols) if not narrow_mask[i]]
    wide_weights = [col_max_chars[i] * char_w for i in wide_indices]
    wide_total = sum(wide_weights) if wide_weights else 1

    result = [0] * ncols
    for i in range(ncols):
        if narrow_mask[i]:
            result[i] = narrow_widths[i]
        else:
            # Proportionally distribute, cap at 35% of available width
            wgt = col_max_chars[i] * char_w
            cap = int(avail * 0.35)
            result[i] = max(40, min(int(wgt / wide_total * avail) + 4, cap))

    return result


def _render_table_svg(x, y, w, rows: list[str], font_size: int) -> tuple[ET.Element, int]:
    """Render a markdown table as a grid of ``<text>`` elements.

    Column widths adapt to content so long tables don't overflow vertically.
    Returns ``(group, total_height)``.
    """
    g = ET.Element("g", _attrib())
    if len(rows) < 2:
        return g, 0

    header_cells = [c.strip() for c in rows[0].split("|")[1:-1]]
    data_lines = rows[2:] if len(rows) > 2 else []
    ncols = len(header_cells)
    if ncols == 0:
        return g, 0

    # Adaptive column widths
    col_widths = _calc_col_widths(ncols, header_cells, data_lines, w, font_size)

    fs = font_size
    header_h = int(fs * _LINE_SPACING) + 10
    y0 = y

    # Header background
    g.append(_rect(x, y, w, header_h, TABLE_HEADER_BG))

    # Header cells — left-aligned, single-line
    cx = x + 4
    for ci, hdr in enumerate(header_cells):
        cw = col_widths[ci]
        avg_cw = fs * 0.55
        max_chars = max(2, int((cw - 8) / avg_cw))
        hdr_text = hdr if len(hdr) <= max_chars else hdr[:max_chars]
        g.append(_text(cx + 2, y + fs + 2, hdr_text,
                       font_size=fs, fill="#FFFFFF", bold=True))
        cx += cw

    y += header_h
    content_start_y = y

    # Data rows — wrap long text to multiple lines
    line_h = int(fs * _LINE_SPACING)
    for ri, row in enumerate(data_lines):
        raw_cells = [c.strip() for c in row.split("|")[1:-1]]
        while len(raw_cells) < ncols:
            raw_cells.append("")

        # Wrap each cell, find max lines for this row
        cell_lines: list[list[str]] = []
        max_lines = 1
        for ci, raw in enumerate(raw_cells):
            cw = col_widths[ci]
            # Narrow columns: single line
            if cw < 80:
                cell_lines.append([str(raw)])
            else:
                pairs = _wrap_text(_strip_md(str(raw)), cw - 8, fs)
                lines = [p[0] for p in pairs if p[0]]
                if not lines:
                    lines = [str(raw)]
                cell_lines.append(lines)
                max_lines = max(max_lines, len(lines))

        this_row_h = max_lines * line_h + 8

        bg = TABLE_ROW_ALT if ri % 2 == 0 else BG_COLOR
        g.append(_rect(x, y, w, this_row_h, bg))
        g.append(_rect(x, y + this_row_h - 1, w, 1, BORDER_COLOR))

        cx = x + 4
        for ci in range(len(raw_cells)):
            lines = cell_lines[ci]
            color = "#4CAF50" if lines[0].strip() == "✓" else TEXT_COLOR
            for li, line in enumerate(lines):
                g.append(_text(cx + 2, y + fs + 3 + li * line_h, line,
                               font_size=fs, fill=color))
            cx += col_widths[ci]

        y += this_row_h

    return g, y - y0 + 4


# ===========================================================================
# Abstract rendering (<text> with two-column layout approximation)
# ===========================================================================

def _render_abstract_svg(x, y, w, summary: str) -> tuple[ET.Element, int]:
    """Render the abstract as wrapped ``<text>`` elements.

    Uses a simple single-column layout (two-column is too complex for <text>).
    """
    g = ET.Element("g", _attrib())
    items = _md_text_to_lines(summary)
    cy = y

    for item in items:
        if item["type"] == "blank":
            cy += BODY_SIZE
            continue

        elif item["type"] == "h2":
            hdr_g, hdr_h = _text_block(x, cy, w - 8, item["text"],
                                       font_size=BODY_SIZE + 4,
                                       color=HEADER_BG, bold=True,
                                       justify=False)
            g.append(hdr_g)
            cy += hdr_h + 4

        elif item["type"] == "h3":
            hdr_g, hdr_h = _text_block(x + 8, cy, w - 16, item["text"],
                                       font_size=BODY_SIZE + 1,
                                       color=TEXT_COLOR, bold=True,
                                       justify=False)
            g.append(hdr_g)
            cy += hdr_h + 2

        elif item["type"] == "h4":
            hdr_g, hdr_h = _text_block(x, cy, w - 8, item["text"],
                                       font_size=BODY_SIZE + 1,
                                       color=HEADER_BG, bold=True,
                                       justify=False)
            g.append(hdr_g)
            cy += hdr_h + 2

        elif item["type"] == "table":
            tbl_g, tbl_h = _render_table_svg(x + 4, cy, w - 8,
                                             item.get("rows", []), MINI_SIZE)
            g.append(tbl_g)
            cy += tbl_h + 8

        elif item["type"] == "p":
            para_g, para_h = _text_block(x + 4, cy, w - 8, item["text"],
                                         font_size=BODY_SIZE, color=TEXT_COLOR)
            g.append(para_g)
            cy += para_h + 6

    total_h = cy - y + 8
    return g, total_h


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
    g, new_y = _section_header(x, y, w, "\U0001F4C4 摘要")
    if summary:
        content_g, content_h = _render_abstract_svg(x + 10, new_y, w - 20, summary)
        g.append(content_g)
        new_y += content_h + 12
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
    justify_w = w - 8  # target width for justification
    for p in papers[:5]:
        # Title line — justify
        line = f"[{p.first_author} {p.year}] {p.short_title}"
        bg, bh = _text_block(x + 8, new_y, justify_w, line,
                             font_size=SMALL_SIZE, color=TEXT_COLOR, bold=True,
                             justify=True)
        g.append(bg)
        new_y += bh
        # Innovation line — justify
        if p.key_innovation:
            inno = f"    \U0001F4A1 {p.key_innovation or ''}"
            ig, ih = _text_block(x + 8, new_y, justify_w, inno,
                                 font_size=MINI_SIZE, color=TEXT_SECONDARY,
                                 justify=True)
            g.append(ig)
            new_y += ih
        new_y += 4
    new_y += 8
    return g, new_y


def _build_evolution(x, y, w, evo_path: str, lineage_caption: str = "") -> tuple[ET.Element, int]:
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

    # Lineage caption
    if lineage_caption and lineage_caption.strip():
        caption_lines = _wrap_text(lineage_caption.strip(), w - 12, SMALL_SIZE)
        for line, _ in caption_lines[:3]:  # at most 3 lines
            g.append(_text(x + 6, new_y + 6, line,
                           font_size=SMALL_SIZE, fill=TEXT_SECONDARY))
            new_y += SMALL_SIZE + 4

    return g, new_y


def _build_paper_table(x, y, w, papers: list[Paper]) -> tuple[ET.Element, int]:
    """Paper summary table — rendered as <text> elements."""
    g, new_y = _section_header(x, y, w, "\U0001F4CB 论文摘要表")

    fs = TABLE_SIZE
    headers = ["#", "论文标题", "年份", "主要创新点", "数据集", "代码"]
    # Simple layout: narrow cols get tight fit, two main cols split remaining
    char_w = fs * 0.55
    fixed = {0: 28, 2: 40, 4: 80, 5: 32}  # #, year, datasets, code (px)
    fixed_total = sum(fixed.values())
    col_widths = [0] * 6
    for i, w_px in fixed.items():
        col_widths[i] = w_px
    # Remaining space split equally between title and innovation
    avail = w - fixed_total - 6 * 4  # 4px padding per column
    col_widths[1] = avail // 2
    col_widths[3] = avail - col_widths[1]

    line_h = int(fs * _LINE_SPACING)
    header_h = line_h + 10

    # Header row — left-aligned (truncate by column width)
    g.append(_rect(x, new_y, w, header_h, TABLE_HEADER_BG))
    cx = x + 4
    for ci, hdr in enumerate(headers):
        cw = col_widths[ci]
        avg_cw = fs * 0.55
        max_chars = max(2, int((cw - 8) / avg_cw))
        hdr_text = hdr if len(hdr) <= max_chars else hdr[:max_chars]
        g.append(_text(cx + 2, new_y + fs + 4, hdr_text,
                       font_size=fs, fill="#FFFFFF", bold=True))
        cx += cw
    new_y += header_h

    # Data rows — wrap long text to multiple lines
    for ri, p in enumerate(papers):
        bg = TABLE_ROW_ALT if ri % 2 == 0 else BG_COLOR

        # Prepare raw cell text
        raw_cells = [
            str(ri + 1),
            p.short_title,
            str(p.year),
            (p.key_innovation or "—"),
            ", ".join(p.datasets_used[:2]) if p.datasets_used else "—",
            "✓" if p.has_code else "—",
        ]

        # Wrap each wide cell by column pixel width, collect lines
        cell_lines: list[list[str]] = []
        max_lines = 1
        for ci, raw in enumerate(raw_cells):
            cw = col_widths[ci]
            # Narrow columns: single line, no wrapping
            if cw < 80:
                cell_lines.append([str(raw)])
            else:
                # Use _wrap_text for CJK-aware wrapping within column width
                pairs = _wrap_text(str(raw), cw - 8, fs)
                lines = [p[0] for p in pairs if p[0]]  # unwrap tuples, skip blanks
                if not lines:
                    lines = [str(raw)]
                cell_lines.append(lines)
                max_lines = max(max_lines, len(lines))

        # Dynamic row height
        line_h = int(fs * _LINE_SPACING)
        this_row_h = max_lines * line_h + 8

        # Row background
        g.append(_rect(x, new_y, w, this_row_h, bg))
        g.append(_rect(x, new_y + this_row_h - 1, w, 1, BORDER_COLOR))

        # Render cells
        cx = x + 4
        for ci in range(len(raw_cells)):
            lines = cell_lines[ci]
            color = "#4CAF50" if raw_cells[ci].strip() == "✓" else TEXT_COLOR
            for li, line in enumerate(lines):
                g.append(_text(cx + 2, new_y + fs + 3 + li * line_h, line,
                               font_size=fs, fill=color))
            cx += col_widths[ci]

        new_y += this_row_h

    new_y += 8
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
                         output_path, paper_figures, lineage_caption: str = "") -> None:
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
        "lineage_caption": lineage_caption,
    }
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"poster_input_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f"快照已保存: {json_path}")


# ===========================================================================
# PNG generation (cairosvg)
# ===========================================================================


def _svg_to_png(svg_path: str, png_path: str, scale: float = 3.0) -> bool:
    """Convert SVG to PNG using cairosvg.  Returns True on success."""
    if not _CAIROSVG_OK:
        logger.warning(
            "cairosvg/cairo is unavailable — skipping PNG generation: %s",
            _CAIROSVG_IMPORT_ERROR,
        )
        return False

    try:
        cairosvg.svg2png(url=svg_path, write_to=png_path, scale=scale)  # type: ignore[name-defined]  # noqa: F821
        size_kb = os.path.getsize(png_path) / 1024
        logger.info(f"PNG poster saved: {png_path} ({size_kb:.1f} KB)")
        return True
    except Exception as exc:
        logger.warning(f"PNG generation failed: {exc}")
        return False


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
    generate_png: bool = True,
    png_scale: float = 3.0,
    lineage_caption: str = "",
) -> str:
    """Generate a self-contained SVG academic poster (and optionally PNG).

    Parameters
    ----------
    generate_png : bool
        If True (default), also produce a PNG via cairosvg.
    png_scale : float
        Viewport scale factor for PNG output (3.0 → ~4800 px wide).
    lineage_caption : str
        Optional one-line summary of the algorithm lineage for the evolution panel.
    """
    logger.info(f"生成 SVG 海报: '{topic}'")

    # Snapshot
    _save_input_snapshot(papers, topic, review_summary, evolution_diagram_path,
                         output_path, paper_figures, lineage_caption)

    content_top = HEADER_H + 24
    _x = MARGIN

    svg = ET.Element("svg", _attrib({
        "width": "100%", "height": "100%",
        "viewBox": f"0 0 {CANVAS_WIDTH} {CANVAS_MIN_HEIGHT}",
    }))
    svg.set("xmlns:xlink", "http://www.w3.org/1999/xlink")

    # 1. Header
    svg.append(_build_header(topic, papers))

    # 2. Abstract (full-width)
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
    g_evo, y3 = _build_evolution(c3, yc, col_w, evolution_diagram_path, lineage_caption)
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

    # ---- PNG generation ----
    if generate_png:
        png_path = output_path.rsplit(".", 1)[0] + ".png"
        ok = _svg_to_png(output_path, png_path, scale=png_scale)
        if ok:
            logger.info(f"PNG 海报已保存: {png_path}")
        else:
            logger.warning("PNG 海报生成失败（SVG 仍可用）")

    return output_path
