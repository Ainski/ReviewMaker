import os
from src import lineage_graph as lg
from src import lineage_render as lr


def _graph():
    nodes = [
        lg.LineageNode("W1", "Vaswani 2017", "Attention", 2017, "奠基", 999, True),
        lg.LineageNode("W10", "Fu 2022", "MECCH", 2022, "图神经网络类", 10, False, 1),
        lg.LineageNode("W11", "Joshi 2025", "Transformers are GNNs", 2025, "Transformer类", 3, False, 2),
    ]
    edges = [lg.LineageEdge("W1", "W10", "改进", "改进卷积"),
             lg.LineageEdge("W1", "W11", "扩展", "统一视角")]
    return lg.LineageGraph(nodes=nodes, edges=edges, metrics={})


def test_render_lineage_writes_nonempty_png(tmp_path):
    out = tmp_path / "evolution.png"
    path = lr.render_lineage(_graph(), "Graph Neural Networks", output_path=str(out))
    assert os.path.exists(path) and os.path.getsize(path) > 1000


def test_render_lineage_empty_graph_still_writes(tmp_path):
    out = tmp_path / "evolution.png"
    path = lr.render_lineage(lg.LineageGraph(), "topic", output_path=str(out))
    assert os.path.exists(path)
