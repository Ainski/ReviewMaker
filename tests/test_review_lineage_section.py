from src import lineage_graph as lg
from src.review_generator import generate_lineage_narrative, insert_lineage_section


def test_generate_lineage_narrative_empty_when_no_edges():
    g = lg.LineageGraph(nodes=[], edges=[], metrics={})
    assert generate_lineage_narrative(g, lambda p: "anything") == ""


def test_generate_lineage_narrative_uses_llm():
    nodes = [lg.LineageNode("W1", "Vaswani 2017", "Attention", 2017, "奠基", 9, True),
             lg.LineageNode("W2", "Fu 2022", "MECCH", 2022, "GNN", 1, False, 1)]
    g = lg.LineageGraph(nodes=nodes, edges=[lg.LineageEdge("W1", "W2", "改进", "改进卷积")], metrics={})
    out = generate_lineage_narrative(g, lambda p: "注意力机制[1]推动了后续方法。")
    assert "注意力" in out


def test_insert_section_renumbers_future_outlook():
    review = "## 四、对比分析\n比较内容\n\n## 五、未来展望\n展望内容"
    out = insert_lineage_section(review, "脉络正文。")
    assert "## 五、算法演进脉络" in out
    assert "## 六、未来展望" in out
    assert out.index("算法演进脉络") < out.index("未来展望")


def test_insert_section_fallback_appends_when_no_marker():
    review = "## 一、引言\n正文"
    out = insert_lineage_section(review, "脉络正文。")
    assert "算法演进脉络" in out and out.endswith("脉络正文。") is False  # header added


def test_insert_section_noop_on_empty_narrative():
    review = "## 五、未来展望\nx"
    assert insert_lineage_section(review, "") == review
