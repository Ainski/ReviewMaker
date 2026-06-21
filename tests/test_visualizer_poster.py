import types
import src.agents as agents
from tests._poster_fixtures import sample_graph


def test_build_poster_uses_graph_and_generate_poster(tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(agents, "build_milestone_graph",
                        lambda papers, topic, llm_call=None: sample_graph())
    monkeypatch.setattr(agents, "_default_llm_call", lambda: (lambda p: ""))

    def fake_generate_poster(topic, review_summary, papers, graph, out_dir, **kw):
        calls["graph"] = graph
        calls["out_dir"] = out_dir
        return {"html": out_dir + "/poster.html", "png": out_dir + "/poster.png"}

    monkeypatch.setattr(agents, "generate_poster", fake_generate_poster)

    state = types.SimpleNamespace(
        papers=[object()], topic="T", review_text="R",
        output_dir=str(tmp_path), no_poster=False, poster_path=None)

    agents.VisualizerAgent()._build_poster(state)

    assert calls["graph"] is not None
    assert state.poster_path.endswith("poster.png")
