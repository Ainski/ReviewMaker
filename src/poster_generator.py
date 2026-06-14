"""Poster generator module — creates an academic poster from review content."""

import base64
import dataclasses
import json
import logging
import os
import textwrap
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from src.models import Paper

logger = logging.getLogger(__name__)

# A3 landscape at 300 DPI (print quality)
POSTER_WIDTH = 9921   # 841mm
POSTER_HEIGHT = 7016  # 594mm

# Color scheme (academic, high contrast)
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

# ---- CJK Font Setup ----
_PILLOW_CJK_FONT_PATH = None
_pillow_candidates = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:\\Windows\\Fonts\\msyh.ttc",
    "C:\\Windows\\Fonts\\simhei.ttf",
]
for _pf in _pillow_candidates:
    if os.path.exists(_pf):
        _PILLOW_CJK_FONT_PATH = _pf
        break


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Get a CJK-capable font."""
    if _PILLOW_CJK_FONT_PATH:
        try:
            return ImageFont.truetype(_PILLOW_CJK_FONT_PATH, size)
        except Exception:
            pass
    fallbacks = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in fallbacks:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text_block(
    draw: ImageDraw.Draw,
    xy: tuple[int, int],
    max_width: int,
    max_height: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    color: str = TEXT_COLOR,
    line_spacing: int = 8,
) -> int:
    """Draw text with word wrapping. Returns y after last line."""
    x, y = xy
    char_w = font.getbbox("X")[2] if hasattr(font, "getbbox") else font.size
    if char_w <= 0:
        char_w = 1
    chars_per_line = max(1, int(max_width / char_w))

    lines = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        for line in textwrap.wrap(para, width=chars_per_line):
            lines.append(line)

    line_h = font.size + line_spacing
    for line in lines:
        if y + line_h > xy[1] + max_height:
            break
        draw.text((x, y), line, fill=color, font=font)
        y += line_h
    return y


def _draw_section_header(
    draw: ImageDraw.Draw,
    x: int, y: int, width: int,
    title: str,
    font: ImageFont.FreeTypeFont,
) -> int:
    """Draw a colored section header bar. Returns y after header."""
    bar_h = font.size + 20
    # Header background
    draw.rectangle([x, y, x + width, y + bar_h], fill=SECTION_HEADER_BG)
    # Accent line at top
    draw.rectangle([x, y, x + width, y + 6], fill=ACCENT_COLOR)
    # Title text
    draw.text((x + 24, y + 10), title, fill=SECTION_HEADER_FG, font=font)
    return y + bar_h + 32


def _create_table_image(
    papers: list[Paper],
    width: int,
    font_size: int = 32,
) -> Image.Image:
    """Create a summary table image."""
    hdr_font = _get_font(font_size)
    cel_font = _get_font(font_size - 4)

    col_widths = [
        80,                              # 序号
        int(width * 0.32),               # 标题
        70,                              # 年份
        int(width * 0.30),               # 创新
        int(width * 0.15),               # 数据集
        70,                              # 代码
    ]
    headers = ["序号", "论文标题", "年份", "主要创新点", "数据集", "代码"]

    row_h = font_size + 22
    hdr_h = font_size + 28
    n = len(papers) + 1
    tbl_h = hdr_h + n * row_h

    img = Image.new("RGB", (width, tbl_h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Headers
    cx = 0
    for hdr, cw in zip(headers, col_widths):
        draw.rectangle([cx, 0, cx + cw, hdr_h], fill=TABLE_HEADER_BG)
        bb = hdr_font.getbbox(hdr) if hasattr(hdr_font, "getbbox") else (0, 0, hdr_font.size, hdr_font.size)
        tw = bb[2] - bb[0]
        th = bb[3] - bb[1]
        draw.text((cx + (cw - tw) // 2, (hdr_h - th) // 2 - 2), hdr, fill="#FFFFFF", font=hdr_font)
        cx += cw

    # Rows
    for ri, p in enumerate(papers):
        ry = hdr_h + ri * row_h
        bg = TABLE_ROW_ALT if ri % 2 == 0 else BG_COLOR
        row_data = [
            str(ri + 1),
            p.short_title[:55],
            str(p.year),
            (p.key_innovation or "")[:50],
            ", ".join(p.datasets_used[:2]) if p.datasets_used else "—",
            "✓" if p.has_code else "—",
        ]
        cx = 0
        for d, cw in zip(row_data, col_widths):
            draw.rectangle([cx, ry, cx + cw, ry + row_h], fill=bg, outline=BORDER_COLOR)
            text = str(d)[:35]
            bb = cel_font.getbbox(text) if hasattr(cel_font, "getbbox") else (0, 0, cel_font.size, cel_font.size)
            tw = bb[2] - bb[0]
            th = bb[3] - bb[1]
            color = "#4CAF50" if d == "✓" else TEXT_COLOR
            draw.text((cx + 6, ry + (row_h - th) // 2), text, fill=color, font=cel_font)
            cx += cw

    return img


def _save_input_snapshot(
    papers: list[Paper],
    topic: str,
    review_summary: str,
    evolution_diagram_path: str,
    output_path: str,
    dpi: int,
    paper_figures: Optional[list[dict]],
) -> None:
    """保存 generate_poster 的输入参数为 JSON 文件，便于测试和复现。"""

    # 1) Paper → dict
    papers_data = [dataclasses.asdict(p) for p in papers]

    # 2) paper_figures: image_bytes → base64 字符串
    figs_data = None
    if paper_figures:
        figs_data = []
        for fd in paper_figures:
            fd_copy = {k: v for k, v in fd.items() if k != "image_bytes"}
            img_bytes = fd.get("image_bytes")
            if isinstance(img_bytes, bytes):
                fd_copy["image_bytes_base64"] = base64.b64encode(img_bytes).decode("ascii")
            else:
                fd_copy["image_bytes_base64"] = None
            figs_data.append(fd_copy)

    snapshot = {
        "topic": topic,
        "review_summary": review_summary,
        "evolution_diagram_path": evolution_diagram_path,
        "output_path": output_path,
        "dpi": dpi,
        "papers": papers_data,
        "paper_figures": figs_data,
    }

    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"poster_input_{ts}.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f"快照已保存: {json_path}")


def generate_poster(
    papers: list[Paper],
    topic: str,
    review_summary: str,
    evolution_diagram_path: str,
    output_path: str = "output/poster.png",
    dpi: int = 200,
    paper_figures: Optional[list[dict]] = None,
) -> str:
    """
    Generate an A3 academic poster with larger fonts and clear layout.

    Layout (landscape):
    ┌──────────────────────────────────────────────────────────────┐
    │                    TITLE BANNER (deep blue)                    │
    ├──────────────────────────┬───────────────────────────────────┤
    │  摘要  (Abstract)         │  算法演进时间线 (wide)              │
    │                          │  (embedded evolution.png)          │
    ├──────────────────────────┤                                   │
    │  关键统计 (Stats cards)    │                                   │
    ├──────────────────────────┼───────────────────────────────────┤
    │  重点论文 (Top papers)     │  论文摘要表                        │
    │                          │  (sortable table)                  │
    ├──────────────────────────┼───────────────────────────────────┤
    │                          │  原文图片 (Paper figures)           │
    │                          │  (extracted from PDFs)              │
    └──────────────────────────┴───────────────────────────────────┘
    │                         FOOTER                                 │
    └────────────────────────────────────────────────────────────────┘
    """
    logger.info(f"生成海报: '{topic}'")

    # ---- 保存函数输入为 JSON（用于测试/复现） ----
    # _save_input_snapshot(
    #     papers=papers, topic=topic, review_summary=review_summary,
    #     evolution_diagram_path=evolution_diagram_path, output_path=output_path,
    #     dpi=dpi, paper_figures=paper_figures,
    # )

    poster = Image.new("RGB", (POSTER_WIDTH, POSTER_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(poster)

    # ---- Fonts (300 DPI optimized) ----
    title_font = _get_font(96)          # 主标题
    subtitle_font = _get_font(44)       # 副标题
    section_font = _get_font(54)        # 区块标题
    body_font = _get_font(38)           # 正文
    small_font = _get_font(32)          # 辅助文字
    table_font_size = 38                # 表格字号

    # ---- Layout Geometry ----
    MARGIN = 120
    GAP = 80
    LEFT_W = int((POSTER_WIDTH - 2 * MARGIN - GAP) * 0.40)
    RIGHT_W = int(POSTER_WIDTH - 2 * MARGIN - GAP - LEFT_W)

    left_x = MARGIN
    right_x = int(MARGIN + LEFT_W + GAP)

    # ---- 1. HEADER BANNER ----
    HEADER_H = 380
    draw.rectangle([0, 0, POSTER_WIDTH, HEADER_H], fill=HEADER_BG)
    draw.rectangle([0, HEADER_H - 12, POSTER_WIDTH, HEADER_H], fill=ACCENT_COLOR)

    title_text = f"文献综述: {topic}"
    bb = title_font.getbbox(title_text)
    tw = bb[2] - bb[0] if hasattr(title_font, "getbbox") else len(title_text) * 50
    draw.text(((POSTER_WIDTH - tw) // 2, 70), title_text, fill=HEADER_FG, font=title_font)

    num_code = sum(1 for p in papers if p.has_code)
    yr_min = min((p.year for p in papers if p.year > 0), default=0)
    yr_max = max((p.year for p in papers if p.year > 0), default=0)
    subtitle = (
        f"{len(papers)} 篇论文 | {num_code} 篇含开源代码 | "
        f"{yr_min}–{yr_max} | "
        f"{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}"
    )
    bb2 = subtitle_font.getbbox(subtitle)
    sw = bb2[2] - bb2[0] if hasattr(subtitle_font, "getbbox") else len(subtitle) * 24
    draw.text(((POSTER_WIDTH - sw) // 2, 240), subtitle, fill="#B0BEC5", font=subtitle_font)

    content_top = HEADER_H + 50

    # ---- 2. LEFT: ABSTRACT ----
    ly = content_top
    ly = _draw_section_header(draw, left_x, ly, int(LEFT_W), "📄 摘要", section_font)

    if review_summary:
        ly = _draw_text_block(
            draw, (left_x + 16, ly), int(LEFT_W - 32), 500,
            review_summary[:500], body_font, TEXT_COLOR,
        )
        ly += 24

    # ---- 3. LEFT: KEY STATS ----
    ly = _draw_section_header(draw, left_x, ly, int(LEFT_W), "📊 关键统计", section_font)

    stat_lines = [
        f"综述论文: {len(papers)} 篇    含开源代码: {num_code} 篇 ({num_code * 100 // max(len(papers), 1)}%)",
        f"年份范围: {yr_min} – {yr_max}    总引用: {sum(p.citation_count for p in papers):,} 次",
        f"方法类别: {len(set(p.method_category for p in papers if p.method_category))} 类",
    ]
    for s in stat_lines:
        draw.text((left_x + 16, ly), s, fill=TEXT_COLOR, font=body_font)
        ly += 56

    ly += 16

    # ---- 4. LEFT: TOP PAPERS ----
    ly = _draw_section_header(draw, left_x, ly, int(LEFT_W), "⭐ 重点论文", section_font)

    for p in papers[:5]:
        line = f"[{p.first_author} {p.year}] {p.short_title[:55]}"
        draw.text((left_x + 16, ly), line, fill=TEXT_COLOR, font=small_font)
        ly += 48
        if p.key_innovation:
            inno_line = f"      💡 {p.key_innovation[:80]}"
            draw.text((left_x + 16, ly), inno_line, fill=TEXT_SECONDARY, font=_get_font(28))
            ly += 40
        ly += 10

    # ---- 5. RIGHT: EVOLUTION DIAGRAM ----
    ry = content_top
    ry = _draw_section_header(draw, right_x, ry, int(RIGHT_W), "📈 算法演进时间线", section_font)

    evo_embedded = False
    if evolution_diagram_path and os.path.exists(evolution_diagram_path):
        try:
            evo_img = Image.open(evolution_diagram_path)
            evo_w = int(RIGHT_W)
            evo_h = int(evo_img.height * (int(RIGHT_W) / evo_img.width))
            max_evo_h = 1400
            if evo_h > max_evo_h:
                evo_w = int(evo_w * max_evo_h / evo_h)
                evo_h = max_evo_h
            evo_img = evo_img.resize((evo_w, evo_h), Image.LANCZOS)
            poster.paste(evo_img, (right_x, ry))
            ry += evo_h + 20
            evo_embedded = True
        except Exception as e:
            logger.warning(f"演进图嵌入失败: {e}")

    if not evo_embedded:
        draw.text((right_x + 10, ry), "[无法嵌入演进图]", fill="#9E9E9E", font=body_font)
        ry += 40

    # ---- 6. RIGHT: PAPER TABLE ----
    ry = _draw_section_header(draw, right_x, ry, int(RIGHT_W), "📋 论文摘要表", section_font)

    table_img = _create_table_image(papers[:10], int(RIGHT_W), font_size=table_font_size)
    table_max_h = min(table_img.height, 1000)
    poster.paste(table_img, (right_x, ry))
    ry += min(table_img.height, table_max_h) + 20

    # ---- 7. RIGHT: ORIGINAL PAPER FIGURES ----
    if paper_figures and len(paper_figures) > 0:
        ry = _draw_section_header(draw, right_x, ry, int(RIGHT_W), "🖼️ 原文图片（来自论文PDF）", section_font)

        num_figs = min(len(paper_figures), 6)
        cols = min(num_figs, 3)
        rows = (num_figs + cols - 1) // cols
        fig_w = (int(RIGHT_W) - 24) // cols
        remaining = POSTER_HEIGHT - ry - 180
        fig_h = min(600, remaining // rows)

        for idx in range(num_figs):
            try:
                fd = paper_figures[idx]
                fig_img = Image.open(BytesIO(fd["image_bytes"])).convert("RGB")
                fig_img.thumbnail((fig_w - 20, fig_h - 50), Image.LANCZOS)

                col = idx % cols
                row = idx // cols
                fx = right_x + col * fig_w + 4
                fy = ry + row * fig_h + 4

                draw.rectangle(
                    [fx, fy, fx + fig_w - 8, fy + fig_h - 8],
                    fill=CARD_BG, outline=BORDER_COLOR, width=3,
                )
                poster.paste(fig_img, (fx + 10, fy + 10))
                cap = f"图{idx+1}: {fd['first_author']} ({fd['year']})"
                draw.text((fx + 10, fy + fig_h - 50), cap, fill=TEXT_SECONDARY, font=_get_font(28))
            except Exception as e:
                logger.debug(f"嵌入图片 {idx} 失败: {e}")

    # ---- 8. FOOTER ----
    FOOTER_H = 100
    draw.rectangle([0, POSTER_HEIGHT - FOOTER_H, POSTER_WIDTH, POSTER_HEIGHT], fill="#E8EAF6")
    footer_text = "文献综述 Agent 工具  |  AI 驱动自动生成  |  基于 DeepSeek 大模型"
    bb3 = small_font.getbbox(footer_text)
    fw = bb3[2] - bb3[0] if hasattr(small_font, "getbbox") else len(footer_text) * 18
    draw.text(
        ((POSTER_WIDTH - fw) // 2, POSTER_HEIGHT - FOOTER_H + 32),
        footer_text, fill=TEXT_SECONDARY, font=small_font,
    )

    # ---- SAVE ----
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    poster.save(output_path, dpi=(dpi, dpi))
    logger.info(f"海报已保存: {output_path}")

    return output_path
