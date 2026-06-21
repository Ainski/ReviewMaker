from src.figure1_render import render_figure1_svg, render_insufficient_svg
from src.figure1_models import Milestone, Branch, Era, MilestoneGraph, FOUND


def _graph():
    ms = [
        Milestone("Transformer", "Vaswani", 2017, FOUND, "自注意力", None, "Attention Is All You Need", "NeurIPS 2017", 130000, True, "a", "W1"),
        Milestone("FlashAttention", "Dao", 2022, FOUND, "IO-aware", None, "FlashAttention ...", "NeurIPS 2022", 3500, True, "a", "W2"),
        Milestone("Ada-KV", "Feng", 2024, "A", "自适应淘汰", 1, "Ada-KV ...", "arXiv 2024", 40, True, "a", None),
        Milestone("FlashInfer", "Ye", 2025, "B", "引擎", 2, "FlashInfer ...", "MLSys 2025", 30, True, "a", None),
        Milestone("LMCache", "Liu", 2025, "B", "缓存层", 3, "LMCache ...", "arXiv 2025", 15, True, "a", None),
    ]
    return MilestoneGraph("KV", ms,
                          [Branch("A", "压缩", "COMP"), Branch("B", "系统", "SYS")],
                          [Era("奠基", "FOUNDATIONS", 2017, 2023), Era("爆发", "BOOM", 2024, 2025)],
                          True, {})


def test_render_svg_structure():
    svg, nodes = render_figure1_svg(_graph())
    assert svg.startswith("<svg") and "</svg>" in svg
    assert "Transformer" in svg and "Ada-KV" in svg
    # (B, 2025) carries two papers under one node
    grp = [n for n in nodes if n["branch"] == "B" and n["year"] == 2025]
    assert len(grp) == 1 and len(grp[0]["members"]) == 2
    # node members expose detail fields for the GUI panel
    m0 = grp[0]["members"][0]
    for key in ("name", "authors", "year", "full_title", "venue", "cited_by", "has_code", "abstract", "branch_name"):
        assert key in m0


def test_node_dots_have_keys():
    svg, nodes = render_figure1_svg(_graph())
    # each group dot is addressable by the frontend
    assert 'data-key="B|2025"' in svg


def test_insufficient():
    assert "信息不足" in render_insufficient_svg("某冷门主题")
    assert render_insufficient_svg("x").startswith("<svg")
