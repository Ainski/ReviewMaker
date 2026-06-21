"""LLM planner — selects milestones, assigns branches/eras, proposes foundational works.

A single structured-JSON call turns the retrieved papers + topic into the skeleton
of the Figure-1 lineage: which papers are milestones, which sub-theme branch each
belongs to, how the timeline divides into eras, and which classic foundational works
the LLM recommends anchoring the early timeline with (verified later via OpenAlex).
"""

import json
import logging

logger = logging.getLogger(__name__)

_EMPTY = {"milestones": [], "branches": [], "eras": [], "foundational": []}


def _build_prompt(papers: list, topic: str) -> str:
    lines = []
    for i, p in enumerate(papers, start=1):
        lines.append(
            f'{i}. "{getattr(p, "title", "")}" '
            f'({getattr(p, "first_author", "?")} {getattr(p, "year", "?")}; '
            f'类别={getattr(p, "method_category", "") or "未分类"}; '
            f'创新={(getattr(p, "key_innovation", "") or "")[:50]})'
        )
    papers_block = "\n".join(lines)
    return (
        f"你在为研究主题「{topic}」绘制一张论文 Figure-1 风格的算法演进谱系图。\n"
        "下面是候选论文(带编号)。请完成:\n"
        "1. 从中挑选关键里程碑(数量由你按主题演进复杂度自行决定,不要全选也不要太少),"
        "给每篇写 paper_index、简短方法名 name、所属子主题分支 branch(用 A/B/C... 标识)、"
        "<=24 个中文字的一句话关键贡献 contrib。\n"
        "2. 给出 branches 列表:每条分支 id 与中文名 name_zh、英文名 name_en(大写),"
        "分支数量由你按主题的子方向数决定。\n"
        "3. 把时间线划分为 2-4 个 eras:每个 name_zh、name_en(大写)、起止年 y0/y1。\n"
        "4. 提名 3-8 个该领域**公认的经典奠基之作**到 foundational,每个给 name(论文完整标题,"
        "用于检索核实)、short(简短展示名,如 Transformer/BERT)、year(发表年);"
        "必须是真实存在的经典论文,不要编造,也不要重复上面的候选论文。\n"
        "只输出一个 JSON 对象,形如:\n"
        '{"milestones":[{"paper_index":1,"name":"...","branch":"A","contrib":"..."}],'
        '"branches":[{"id":"A","name_zh":"...","name_en":"..."}],'
        '"eras":[{"name_zh":"...","name_en":"...","y0":2017,"y1":2023}],'
        '"foundational":[{"name":"Attention Is All You Need","short":"Transformer","year":2017}]}\n\n'
        f"候选论文:\n{papers_block}"
    )


def plan_milestones(papers: list, topic: str, llm_call) -> dict:
    """Call the LLM and parse its plan. Returns the empty skeleton on any failure."""
    try:
        raw = llm_call(_build_prompt(papers, topic)) or ""
        start, end = raw.find("{"), raw.rfind("}") + 1
        if not (0 <= start < end):
            raise ValueError("no JSON object found in LLM output")
        plan = json.loads(raw[start:end])
        # normalise: ensure all keys exist
        for k in _EMPTY:
            plan.setdefault(k, [])
        return plan
    except Exception as e:  # noqa: BLE001 — planner must never break the pipeline
        logger.warning(f"plan_milestones failed, returning empty plan: {e}")
        return dict(_EMPTY)
