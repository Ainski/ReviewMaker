"""GUI/pipeline glue for the Figure-1 lineage diagram.

`generate_figure1` is the single entry point the GUI pipeline calls: it builds the
milestone graph, renders the SVG (or a placeholder), and writes both the static
`evolution.svg` and the interactive `evolution_nodes.json` into the job directory.
"""

import json
import logging
from pathlib import Path

from src.milestone_graph import build_milestone_graph
from src.figure1_render import render_figure1_svg, render_insufficient_svg

logger = logging.getLogger(__name__)


def _default_llm_call():
    """Build a DeepSeek-backed llm_call(prompt)->str from config."""
    from config import config
    from openai import OpenAI
    client = OpenAI(api_key=config.deepseek_api_key, base_url=config.deepseek_base_url)
    model = config.deepseek_model

    def call(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model, max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    return call


def generate_figure1(papers, topic, job_dir, *, llm_call=None, client=None):
    """Build + render the Figure-1 lineage; write evolution.svg + evolution_nodes.json.

    Returns the built MilestoneGraph (use .metrics for the metrics dict).
    """
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    if llm_call is None:
        llm_call = _default_llm_call()

    graph = build_milestone_graph(papers, topic, llm_call=llm_call, client=client)

    if graph.enough:
        svg, nodes = render_figure1_svg(graph)
    else:
        svg, nodes = render_insufficient_svg(topic), []

    (job_dir / "evolution.svg").write_text(svg, encoding="utf-8")
    (job_dir / "evolution_nodes.json").write_text(
        json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Figure-1 lineage written to {job_dir} (enough={graph.enough}, "
                f"milestones={graph.metrics.get('num_milestones')})")
    return graph
