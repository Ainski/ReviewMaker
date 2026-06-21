import json

from src.gui_figure1 import generate_figure1
from src.openalex_client import OpenAlexWork


class FakeClient:
    def verify_foundational(self, name, year=None):
        if "Attention" in name:
            return OpenAlexWork("W1", "Attention Is All You Need", 2017, 130000, [])
        return None


def _paper(i):
    return type("P", (), {
        "title": f"Paper {i}: a method", "first_author": f"A{i}", "year": 2024,
        "method_category": "系统优化类", "key_innovation": "x", "citation_count": i,
        "abstract": "abstract", "has_code": True, "journal": "arXiv",
        "openalex_id": "", "oa_cited_by_count": 0,
    })()


def _fake_llm(_prompt):
    return json.dumps({
        "milestones": [{"paper_index": i, "name": f"M{i}", "branch": "A", "contrib": "c"} for i in range(1, 7)],
        "branches": [{"id": "A", "name_zh": "压缩", "name_en": "COMP"}],
        "eras": [{"name_zh": "奠基", "name_en": "F", "y0": 2017, "y1": 2024}],
        "foundational": [{"name": "Attention Is All You Need", "year": 2017}],
    })


def test_generate_figure1_writes_files(tmp_path):
    papers = [_paper(i) for i in range(1, 7)]
    graph = generate_figure1(papers, "KV", tmp_path, llm_call=_fake_llm, client=FakeClient())
    assert (tmp_path / "evolution.svg").exists()
    assert (tmp_path / "evolution_nodes.json").exists()
    svg = (tmp_path / "evolution.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg")
    nodes = json.loads((tmp_path / "evolution_nodes.json").read_text(encoding="utf-8"))
    assert isinstance(nodes, list) and len(nodes) > 0
    assert graph.metrics["num_milestones"] >= 6


def test_generate_figure1_insufficient(tmp_path):
    papers = [_paper(1)]
    graph = generate_figure1(papers, "KV", tmp_path,
                             llm_call=lambda p: '{"milestones":[],"branches":[],"eras":[],"foundational":[]}',
                             client=FakeClient())
    assert (tmp_path / "evolution.svg").exists()
    svg = (tmp_path / "evolution.svg").read_text(encoding="utf-8")
    assert "信息不足" in svg
    assert graph.metrics["num_milestones"] == 0
