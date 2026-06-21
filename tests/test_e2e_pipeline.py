"""End-to-end / pipeline-integration tests for the redesigned poster.

⚠️  THESE HIT EXTERNAL SERVICES (arXiv search, OpenAlex citations, DeepSeek LLM)
    and launch headless Chrome. They are SKIPPED BY DEFAULT and were authored
    but intentionally NOT run yet (to avoid arXiv rate-limiting). Run them later,
    one at a time, when the arXiv limit has cooled down:

        RUN_E2E=1 DEEPSEEK_API_KEY=sk-... \
          /opt/homebrew/anaconda3/envs/reviewmaker/bin/python3 \
          -m pytest tests/test_e2e_pipeline.py -v -s

    They use max_papers=3 to stay gentle on arXiv. Each test takes minutes
    (real fetch + LLM + browser render).

What they verify: all three poster entry points produce the *redesigned* poster
(figure1 lineage hero + 图文并茂 sections), not the old dense SVG dump:
  1. run_agent_pipeline(...)        — the programmatic agent pipeline
  2. `main.py <topic>`              — the CLI default (inline) pipeline
  3. `main.py <topic> --agent`      — the CLI multi-agent pipeline
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.poster_rasterize import find_chrome

# ---- Guards: skip the whole module unless explicitly opted in ----------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_HAS_CHROME = find_chrome() is not None

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_E2E") or not os.getenv("DEEPSEEK_API_KEY"),
    reason="e2e: set RUN_E2E=1 and DEEPSEEK_API_KEY to run (hits arXiv/OpenAlex/"
           "DeepSeek + headless Chrome)",
)

# Markers of the REDESIGNED poster (from src/poster_render.py); the OLD dense
# poster contained none of these section labels.
_NEW_POSTER_MARKERS = ['class="poster"', "<svg", "方法体系分类", "横向对比", "节选自综述"]

_TOPIC = "KV cache compression for LLM inference"


def _assert_is_new_poster(html_path: Path):
    assert html_path.exists(), f"poster.html missing at {html_path}"
    html = html_path.read_text(encoding="utf-8")
    for marker in _NEW_POSTER_MARKERS:
        assert marker in html, f"poster.html missing redesigned marker: {marker!r}"


# ---- 1. Programmatic agent pipeline -----------------------------------------
def test_run_agent_pipeline_produces_redesigned_poster(tmp_path):
    """run_agent_pipeline drives fetch→rank→review→figure1→poster and writes the
    redesigned poster.html (+ poster.png when Chrome is present)."""
    from src.agents import run_agent_pipeline

    state = run_agent_pipeline(_TOPIC, max_papers=3, year_range=5,
                               output_dir=str(tmp_path))

    assert not state.errors, f"pipeline reported errors: {state.errors}"
    assert state.review_text, "review_text should be populated"
    assert (tmp_path / "evolution.svg").exists(), "figure1 evolution.svg expected"

    _assert_is_new_poster(tmp_path / "poster.html")
    assert state.poster_path, "state.poster_path should be set"
    if _HAS_CHROME:
        assert (tmp_path / "poster.png").exists(), "poster.png expected when Chrome present"
        assert (tmp_path / "poster.png").stat().st_size > 10_000


# ---- 2. CLI default (inline) pipeline ---------------------------------------
def test_cli_default_pipeline_produces_redesigned_poster(tmp_path):
    """`python main.py <topic> --max-papers 3` (the inline CLI path that main.py
    was rewired to call generate_poster) writes the redesigned poster."""
    out = tmp_path / "cli_out"
    proc = subprocess.run(
        [sys.executable, "main.py", _TOPIC,
         "--max-papers", "3", "--output-dir", str(out)],
        cwd=str(_REPO_ROOT), env=os.environ.copy(),
        capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, f"CLI failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    _assert_is_new_poster(out / "poster.html")
    if _HAS_CHROME:
        assert (out / "poster.png").exists()


# ---- 3. CLI multi-agent pipeline --------------------------------------------
def test_cli_agent_mode_produces_redesigned_poster(tmp_path):
    """`python main.py <topic> --agent` routes through OrchestratorAgent →
    VisualizerAgent._build_poster → generate_poster."""
    out = tmp_path / "agent_out"
    proc = subprocess.run(
        [sys.executable, "main.py", _TOPIC, "--agent",
         "--max-papers", "3", "--output-dir", str(out)],
        cwd=str(_REPO_ROOT), env=os.environ.copy(),
        capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, f"CLI --agent failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    _assert_is_new_poster(out / "poster.html")
    if _HAS_CHROME:
        assert (out / "poster.png").exists()


# ---- 4. Real MilestoneGraph → generate_poster (no fixtures) ------------------
def test_generate_poster_from_real_graph(tmp_path):
    """Build a real MilestoneGraph (OpenAlex + DeepSeek) from freshly run
    pipeline papers, then render the poster from it — verifies the hero embeds a
    real lineage and the excerpts come from the real review."""
    from src.agents import run_agent_pipeline
    from src.milestone_graph import build_milestone_graph
    from src.gui_figure1 import _default_llm_call
    from src.poster_generator import generate_poster

    # Reuse one real run to get papers + review (avoids a second arXiv fetch).
    state = run_agent_pipeline(_TOPIC, max_papers=3, year_range=5,
                               no_poster=True, output_dir=str(tmp_path / "seed"))
    assert state.papers, "expected fetched papers"

    graph = build_milestone_graph(state.papers, _TOPIC, llm_call=_default_llm_call())
    out = tmp_path / "poster_from_graph"
    result = generate_poster(_TOPIC, state.review_text, state.papers, graph,
                             str(out), rasterize=_HAS_CHROME)

    _assert_is_new_poster(Path(result["html"]))
    html = Path(result["html"]).read_text(encoding="utf-8")
    # the real topic title should appear (CJK-wrapped or not)
    assert "KV" in html or "cache" in html.lower()
    if _HAS_CHROME:
        assert result["png"] and Path(result["png"]).exists()
