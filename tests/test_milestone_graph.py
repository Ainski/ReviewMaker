import src.milestone_graph as mg
from src.openalex_client import OpenAlexWork
from src.figure1_models import FOUND


class FakeClient:
    def verify_foundational(self, name, year=None):
        if "Attention" in name:
            return OpenAlexWork(openalex_id="W1", title="Attention Is All You Need",
                                year=2017, cited_by_count=130000, referenced_works=[])
        return None  # unresolved -> dropped


def _paper(i):
    return type("P", (), {
        "title": f"Paper {i}: a method", "first_author": f"A{i}", "year": 2024,
        "method_category": "系统优化类", "key_innovation": "x", "citation_count": i,
        "abstract": "abstract text", "has_code": True, "journal": "arXiv",
        "openalex_id": "", "oa_cited_by_count": 0,
    })()


def _plan(papers):
    return {
        "milestones": [{"paper_index": i, "name": f"M{i}", "branch": "A", "contrib": "c"}
                       for i in range(1, len(papers) + 1)],
        "branches": [{"id": "A", "name_zh": "压缩", "name_en": "COMPRESSION"}],
        "eras": [{"name_zh": "奠基", "name_en": "F", "y0": 2017, "y1": 2024}],
        "foundational": [{"name": "Attention Is All You Need", "year": 2017},
                         {"name": "Ghost Paper", "year": 1999}],
    }


def test_build_graph_verifies_foundational_and_enough(monkeypatch):
    papers = [_paper(i) for i in range(1, 7)]
    monkeypatch.setattr(mg, "plan_milestones", lambda p, t, l: _plan(papers))
    g = mg.build_milestone_graph(papers, "KV", llm_call=lambda x: "", client=FakeClient())

    founds = [m for m in g.milestones if m.branch == FOUND]
    assert len(founds) == 1 and founds[0].year == 2017   # Ghost dropped, Attention kept
    assert founds[0].cited_by == 130000                   # real OpenAlex metadata
    assert g.enough is True                               # 6 paper milestones >= 5
    assert g.metrics["num_foundational"] == 1
    assert g.metrics["num_branches"] == 1


def test_foundational_dedup(monkeypatch):
    """Two foundational candidates resolving to the same OpenAlex work -> one node."""
    papers = [_paper(i) for i in range(1, 7)]

    class DupClient:
        def verify_foundational(self, name, year=None):
            return OpenAlexWork("W1", "Attention Is All You Need", 2017, 130000, [])

    monkeypatch.setattr(mg, "plan_milestones", lambda p, t, l: {
        "milestones": [{"paper_index": i, "name": f"M{i}", "branch": "A", "contrib": "c"} for i in range(1, 7)],
        "branches": [{"id": "A", "name_zh": "压缩", "name_en": "C"}],
        "eras": [],
        "foundational": [{"name": "Attention Is All You Need", "year": 2017},
                         {"name": "Transformer paper", "year": 2017}]})
    g = mg.build_milestone_graph(papers, "KV", llm_call=lambda x: "", client=DupClient())
    founds = [m for m in g.milestones if m.branch == FOUND]
    assert len(founds) == 1                 # deduped by openalex_id
    assert g.metrics["num_foundational"] == 1


def test_not_enough_when_few(monkeypatch):
    papers = [_paper(1)]
    monkeypatch.setattr(mg, "plan_milestones", lambda p, t, l: {
        "milestones": [{"paper_index": 1, "name": "M1", "branch": "A", "contrib": "c"}],
        "branches": [{"id": "A", "name_zh": "压缩", "name_en": "COMPRESSION"}],
        "eras": [], "foundational": []})
    g = mg.build_milestone_graph(papers, "KV", llm_call=lambda x: "", client=FakeClient())
    assert g.enough is False
