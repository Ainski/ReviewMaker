"""Orchestrate the redesigned poster: data -> HTML -> PNG.

Pipeline-agnostic and LLM-free: the caller passes an already-built
MilestoneGraph (see src/agents.py). Visual spec: docs/superpowers/specs/
2026-06-21-poster-redesign-design.md.
"""
import logging
import os

from src.poster_data import build_poster_data
from src.poster_render import render_poster_html
from src.figure1_render import render_figure1_svg, render_insufficient_svg
from src.poster_rasterize import rasterize_html

logger = logging.getLogger(__name__)


def generate_poster(topic, review_summary, papers, graph, out_dir, *, rasterize=True):
    os.makedirs(out_dir, exist_ok=True)
    data = build_poster_data(topic, review_summary, papers, graph)
    if getattr(graph, "enough", True):
        hero_svg = render_figure1_svg(graph, embed=True)[0]
    else:
        hero_svg = render_insufficient_svg(topic)
    html = render_poster_html(data, hero_svg)
    html_path = os.path.join(out_dir, "poster.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    result = {"html": html_path, "png": None}
    if rasterize:
        try:
            result["png"] = rasterize_html(html, os.path.join(out_dir, "poster.png"))
        except Exception as e:  # browser missing / render failure — keep HTML, don't break pipeline
            logger.warning("poster rasterize skipped: %s", e)
    logger.info("poster written: %s (png=%s)", html_path, result["png"])
    return result
