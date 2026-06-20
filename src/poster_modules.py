"""Poster modules generator — compresses papers into 4 knowledge modules for poster display.

Produces a structured JSON that the frontend PosterMap component renders as
a poster-style knowledge evolution diagram (center theme + diamond module cards).

Uses an LLM call to distill papers + review text into 4 method stages with
evolution arrows, following the dual-view design spec.
"""

import json
import logging
import re
from typing import Optional

from src.models import Paper

logger = logging.getLogger(__name__)

# Module count per spec: 4 knowledge modules + center theme
NUM_MODULES = 4

# System prompt for module compression
SYSTEM_PROMPT = """You are an academic knowledge architect. Your task is to compress a set of
research papers into a poster-style knowledge evolution diagram.

Given a topic and a list of papers (with titles, years, abstracts, and method categories),
you must produce exactly 4 knowledge modules that tell the evolution story.

Rules:
1. Each module represents a METHOD STAGE or KNOWLEDGE DOMAIN, not individual papers.
2. Modules must form a clear evolution narrative (Problem → Core → Optimization → Generalization).
3. Each module has: id, num, title (Chinese), en (English short), tag (3-5 keywords),
   a 1-sentence core idea, and 2-3 representative papers.
4. Between modules, define evolution arrows with 5-8 character Chinese labels
   expressing WHY the field moved from one stage to the next.
5. Each paper in the input list should be assigned to exactly one module via paperIds.
6. Include the topic as the center theme label.

Return ONLY valid JSON — no explanation, no markdown fences."""

USER_PROMPT_TEMPLATE = """Topic: {topic}

Papers:
{papers_text}

Please compress these into exactly 4 knowledge modules. Return JSON:
{{
  "topic": "Center theme label (Chinese, short)",
  "modules": [
    {{
      "id": "m1",
      "num": "1",
      "title": "模块中文标题",
      "en": "English Name",
      "tag": "关键词1 · 关键词2",
      "color": "#166534",
      "idea": "一句中文核心思想",
      "papers": ["Author et al. Year: Short Title", "..."],
      "paperIds": ["arxiv_id_1", "arxiv_id_2"]
    }},
    ...
  ],
  "arrows": [
    {{ "from": "m1", "to": "m2", "label": "5-8字动因" }},
    ...
  ]
}}

Module colors: m1=#166534, m2=#2F9E71, m3=#059669, m4=#0F766E
Module structure should follow: Problem → Core Breakthrough → Efficiency/Optimization → Generalization/Extension"""


def _build_papers_text(papers: list[Paper]) -> str:
    """Build a compact text representation of papers for the LLM prompt."""
    lines = []
    for i, p in enumerate(papers, start=1):
        auth = p.first_author or "Unknown"
        title = (p.title or "Untitled")[:80]
        year = p.year or "?"
        cat = p.method_category or "未分类"
        abs_brief = (p.abstract or "")[:150]
        lines.append(
            f"[{i}] arxiv_id={p.arxiv_id} | {auth} et al. ({year}) "
            f'"{title}" | cat={cat} | citations={p.citation_count}'
            f" | {abs_brief}"
        )
    return "\n".join(lines)


def _parse_llm_response(raw: str) -> Optional[dict]:
    """Extract JSON from LLM response and validate structure."""
    if not raw:
        return None
    # Find first { and last }
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        logger.warning("No JSON object found in LLM response")
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        return None

    # Validate required fields
    if "modules" not in data or not isinstance(data["modules"], list):
        return None
    if len(data["modules"]) < 3:
        logger.warning(f"Too few modules: {len(data['modules'])}")
        return None

    # Ensure each module has paperIds
    for m in data["modules"]:
        if "paperIds" not in m:
            m["paperIds"] = []
        if "color" not in m:
            m["color"] = "#2F9E71"
        if "en" not in m:
            m["en"] = ""
        if "tag" not in m:
            m["tag"] = ""

    if "arrows" not in data:
        data["arrows"] = []

    data["topic"] = data.get("topic", "Algorithm Evolution")
    return data


def _build_fallback_modules(papers: list[Paper], topic: str) -> dict:
    """Build a reasonable fallback when LLM generation fails.

    Tries method_category first; if all papers share one category,
    splits by year range to ensure at least 3-4 modules.
    """
    from collections import Counter

    cats = Counter(p.method_category or "未分类" for p in papers)
    # If too few categories, split by year instead
    unique_cats = [c for c, _ in cats.most_common()]
    if len(unique_cats) <= 1 and len(papers) >= 4:
        # Split papers into 4 groups by year
        years = sorted([p.year or 2024 for p in papers])
        q1, q2, q3 = years[len(years)//4], years[len(years)//2], years[3*len(years)//4]
        groups = {
            f"早期研究 (≤{q1})": [],
            f"中期发展 ({q1+1}–{q2})": [],
            f"近期突破 ({q2+1}–{q3})": [],
            f"前沿方向 (≥{q3+1})": [],
        }
        keys = list(groups.keys())
        for p in papers:
            y = p.year or 2024
            if y <= q1: groups[keys[0]].append(p)
            elif y <= q2: groups[keys[1]].append(p)
            elif y <= q3: groups[keys[2]].append(p)
            else: groups[keys[3]].append(p)
        # Remove empty groups
        groups = {k: v for k, v in groups.items() if v}
        top_cats = list(groups.keys())
        cat_papers = groups
    else:
        top_cats = unique_cats[:4]
        cat_papers = {c: [] for c in top_cats}
        for p in papers:
            cat = p.method_category or "未分类"
            if cat in cat_papers:
                cat_papers[cat].append(p)
            else:
                cat_papers[top_cats[0]].append(p)

    modules = []
    colors = ["#166534", "#2F9E71", "#059669", "#0F766E"]
    labels = ["范式奠基", "效率优化", "理论扩展", "跨领域泛化"]
    for i, (cat, cat_ps) in enumerate(cat_papers.items()):
        if i >= 4:
            break
        if not cat_ps:
            continue
        sorted_ps = sorted(cat_ps, key=lambda p: p.citation_count or 0, reverse=True)
        top2 = sorted_ps[:2]
        papers_list = [
            f"{p.first_author or 'Unknown'} et al. {p.year or '?'}: {(p.title or 'Untitled')[:50]}"
            for p in top2
        ]
        modules.append({
            "id": f"m{i + 1}",
            "num": str(i + 1),
            "title": cat,
            "en": f"Stage {i + 1}",
            "tag": labels[i % len(labels)] if i < len(labels) else f"{len(cat_ps)} 篇论文",
            "color": colors[i % len(colors)],
            "idea": f"该阶段包含 {len(cat_ps)} 篇论文，围绕 {topic[:40]} 展开研究",
            "papers": papers_list,
            "paperIds": [p.arxiv_id for p in sorted_ps],
        })

    # Simple linear arrows
    arrows = []
    for i in range(len(modules) - 1):
        arrows.append({
            "from": f"m{i + 1}",
            "to": f"m{i + 2}",
            "label": "方法演进",
        })

    logger.info(f"Fallback produced {len(modules)} modules from {len(papers)} papers")
    return {
        "topic": topic,
        "modules": modules,
        "arrows": arrows,
    }


def generate_modules(
    papers: list[Paper],
    topic: str,
    *,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> dict:
    """Generate poster knowledge modules from papers and topic using LLM.

    Args:
        papers: List of paper objects with metadata
        topic: Research topic string
        api_key: LLM API key
        model: LLM model name
        base_url: LLM API base URL

    Returns:
        dict with keys: topic, modules, arrows
    """
    if not papers or len(papers) < 4:
        logger.warning("Too few papers for module generation, using fallback")
        return _build_fallback_modules(papers, topic)

    papers_text = _build_papers_text(papers)
    user_prompt = USER_PROMPT_TEMPLATE.format(topic=topic, papers_text=papers_text)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2048,
            temperature=0.3,
            timeout=15.0,  # fail fast, fallback is acceptable
        )
        raw = response.choices[0].message.content or ""

        result = _parse_llm_response(raw)
        if result:
            logger.info(f"LLM generated {len(result['modules'])} poster modules")
            return result
    except Exception as e:
        logger.warning(f"LLM module generation failed: {e}")

    logger.info("Using fallback heuristic module generation")
    return _build_fallback_modules(papers, topic)
