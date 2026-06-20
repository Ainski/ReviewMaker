from src.models import Paper
from src.openalex_client import OpenAlexWork
from src import lineage_graph as lg


def _paper(arxiv, title, year, oa_id, refs, family=None, idx_cited=0):
    p = Paper(arxiv_id=arxiv, title=title, abstract="", year=year)
    p.openalex_id = oa_id
    p.referenced_works = refs
    p.oa_cited_by_count = idx_cited
    p.method_category = family
    return p


def test_select_nodes_marks_papers_and_ancestors():
    papers = [_paper("a", "Paper A", 2023, "W10", ["W1"], family="Transformer类")]
    ancestors = [OpenAlexWork(openalex_id="W1", title="Foundational Net", year=2017, cited_by_count=999)]
    nodes = lg.select_nodes(papers, ancestors)
    paper_node = next(n for n in nodes if n.key == "W10")
    anc_node = next(n for n in nodes if n.key == "W1")
    assert paper_node.is_ancestor is False and paper_node.paper_index == 1
    assert paper_node.family == "Transformer类"
    assert anc_node.is_ancestor is True and anc_node.family == "奠基"


def test_select_nodes_unresolved_paper_uses_arxiv_key():
    papers = [_paper("2305.1", "No OA", 2023, None, [])]
    nodes = lg.select_nodes(papers, [])
    assert nodes[0].key == "2305.1"


def test_pick_ancestors_filters_by_share_then_citations():
    # W1 cited by both papers (share=2), W9 cited by one (share=1 -> excluded at min_share=2)
    papers = [
        _paper("a", "A", 2023, "W10", ["W1", "W9"]),
        _paper("b", "B", 2024, "W11", ["W1"]),
    ]
    class FakeClient:
        def fetch_works_by_ids(self, ids):
            return {"W1": OpenAlexWork("W1", "Anc1", 2017, 500),
                    "W9": OpenAlexWork("W9", "Anc9", 2019, 5)}
    anc = lg.pick_ancestors(papers, FakeClient(), min_share=2, max_ancestors=8)
    assert [a.openalex_id for a in anc] == ["W1"]


def test_cap_nodes_keeps_papers_drops_low_share_ancestors():
    papers = [lg.LineageNode(key=f"P{i}", label="", title="", year=2023,
                             family="x", cited_by=0, is_ancestor=False, paper_index=i)
              for i in range(3)]
    ancestors = [lg.LineageNode(key=f"A{i}", label="", title="", year=2017,
                                family="奠基", cited_by=100 - i, is_ancestor=True)
                 for i in range(5)]
    capped = lg._cap_nodes(papers + ancestors, max_nodes=4)
    assert sum(1 for n in capped if not n.is_ancestor) == 3   # all papers kept
    assert sum(1 for n in capped if n.is_ancestor) == 1       # only top-cited ancestor


def _node(key, year, ancestor=False):
    return lg.LineageNode(key=key, label=key, title=key, year=year,
                          family="奠基" if ancestor else "x", cited_by=1,
                          is_ancestor=ancestor)


def test_build_edges_real_citation_old_to_new():
    nodes = [_node("W1", 2017, True), _node("W2", 2023)]
    refs = {"W2": ["W1"], "W1": []}     # W2 cites W1
    edges, dropped = lg.build_edges(nodes, refs)
    assert dropped == 0
    assert [(e.src, e.dst) for e in edges] == [("W1", "W2")]


def test_build_edges_drops_time_violation():
    # Newer node listed as a reference of an older node => year(src) > year(dst): must drop
    nodes = [_node("Wold", 2017), _node("Wnew", 2023)]
    refs = {"Wold": ["Wnew"]}           # impossible-but-dirty: old cites new
    edges, dropped = lg.build_edges(nodes, refs)
    assert edges == [] and dropped == 1


def test_to_dag_and_reduce_removes_transitive_edge():
    nodes = [_node("A", 2018), _node("B", 2020), _node("C", 2022)]
    edges = [lg.LineageEdge("A", "B"), lg.LineageEdge("B", "C"), lg.LineageEdge("A", "C")]
    _, reduced = lg.to_dag_and_reduce(nodes, edges)
    pairs = {(e.src, e.dst) for e in reduced}
    assert ("A", "C") not in pairs
    assert ("A", "B") in pairs and ("B", "C") in pairs


def test_compute_metrics_reports_chain_and_counts():
    nodes = [_node("A", 2018, True), _node("B", 2020), _node("C", 2022)]
    edges = [lg.LineageEdge("A", "B"), lg.LineageEdge("B", "C")]
    g, reduced = lg.to_dag_and_reduce(nodes, edges)
    m = lg.compute_metrics("t", nodes, reduced, dropped=0, resolve_rate="2/2", reduced_graph=g)
    assert m["num_ancestor_nodes"] == 1 and m["num_paper_nodes"] == 2
    assert m["num_real_edges"] == 2 and m["dropped_time_violations"] == 0
    assert m["is_dag"] is True and m["longest_chain_len"] == 3


def test_label_edges_applies_llm_labels_by_index():
    nodes = [_node("W1", 2017, True), _node("W2", 2023)]
    edges = [lg.LineageEdge("W1", "W2")]
    papers = []

    def fake_llm(prompt):
        return '[{"index": 1, "relation": "改进", "label": "改进注意力"}]'

    labeled = lg.label_edges(edges, nodes, papers, fake_llm)
    assert labeled[0].relation == "改进" and labeled[0].label == "改进注意力"


def test_label_edges_survives_bad_json():
    edges = [lg.LineageEdge("W1", "W2")]
    labeled = lg.label_edges(edges, [_node("W1", 2017), _node("W2", 2023)], [], lambda p: "not json")
    assert labeled[0].relation == "承接"  # default preserved


def test_build_lineage_end_to_end_with_fakes():
    papers = [
        _paper("a", "Paper A", 2023, "W10", ["W1"]),
        _paper("b", "Paper B", 2024, "W11", ["W1", "W10"]),
    ]
    class FakeClient:
        def enrich_papers(self, ps):
            return ps  # already enriched in _paper()
        def fetch_works_by_ids(self, ids):
            return {"W1": OpenAlexWork("W1", "Foundation", 2017, 999)}
    graph = lg.build_lineage(papers, "topic", client=FakeClient(),
                             llm_call=lambda p: "[]")
    assert graph.metrics["is_dag"] is True
    assert graph.metrics["num_ancestor_nodes"] == 1
    assert all(  # every edge old -> new
        next(n.year for n in graph.nodes if n.key == e.src)
        <= next(n.year for n in graph.nodes if n.key == e.dst)
        for e in graph.edges
    )


def test_build_edges_skips_unknown_year_nodes():
    # OpenAlex publication_year can be null -> year 0; such nodes must not produce
    # spurious "oldest ancestor" edges nor be counted as time violations.
    nodes = [_node("Wanc", 0, True), _node("P1", 2020)]
    edges, dropped = lg.build_edges(nodes, {"P1": ["Wanc"], "Wanc": ["P1"]})
    assert edges == [] and dropped == 0


def test_select_nodes_dedups_papers_by_key():
    # Two papers resolving to the same OpenAlex work must collapse to one node.
    papers = [_paper("a", "A", 2023, "W10", ["W1"]),
              _paper("bv2", "A v2", 2023, "W10", ["W2"])]
    nodes = lg.select_nodes(papers, [])
    assert sum(1 for n in nodes if n.key == "W10") == 1
