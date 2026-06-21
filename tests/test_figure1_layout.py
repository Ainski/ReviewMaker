from src.figure1_layout import largest_gap, group_by_branch_year, compute_layout
from src.figure1_models import Milestone, Branch, Era, MilestoneGraph, FOUND


def _ms(name, year, branch):
    return Milestone(name=name, authors=f"{name} a", year=year, branch=branch,
                     contrib="c", paper_index=None, full_title=name, venue="v",
                     cited_by=1, has_code=False, abstract="a", openalex_id=None)


def test_largest_gap():
    assert largest_gap([2017, 2019, 2022, 2023]) == (2019, 2022)
    assert largest_gap([2024, 2025]) is None      # no >=3y gap
    assert largest_gap([]) is None


def test_group_by_branch_year():
    ms = [_ms("FlashInfer", 2025, "B"), _ms("LMCache", 2025, "B"), _ms("Ada", 2024, "A")]
    g = group_by_branch_year(ms)
    assert len(g[("B", 2025)]) == 2
    assert len(g[("A", 2024)]) == 1


def _graph():
    ms = [
        _ms("Transformer", 2017, FOUND), _ms("MQA", 2019, FOUND),
        _ms("FlashAttention", 2022, FOUND), _ms("GQA", 2023, FOUND),
        _ms("Ada-KV", 2024, "A"), _ms("KeepKV", 2025, "A"),
        _ms("FlashInfer", 2025, "B"), _ms("LMCache", 2025, "B"),
        _ms("VecInfer", 2025, "C"),
    ]
    return MilestoneGraph("KV", ms,
                          [Branch("A", "压缩", "C"), Branch("B", "系统", "S"), Branch("C", "量化", "Q")],
                          [Era("奠基", "F", 2017, 2023), Era("爆发", "B", 2024, 2025)], True, {})


def test_compute_layout_invariants():
    L = compute_layout(_graph())
    # fork elbow must finish before the first branch node (else dot floats off the curve)
    branch_years = [m.year for m in _graph().milestones if m.branch != FOUND]
    first_branch_x = L["xs"][min(branch_years)]
    assert L["elbow_end"] < first_branch_x
    # gap detected on the sparse 2019->2022 stretch
    assert L["gap"] is not None and L["gap"][0] == 2019 and L["gap"][1] == 2022
    # every group has a position and a side per member
    for grp in L["groups"]:
        assert "x" in grp and "y" in grp and len(grp["placements"]) == len(grp["members"])
    # the (B,2025) group carries both papers under one node
    b2025 = [g for g in L["groups"] if g["branch"] == "B" and g["year"] == 2025]
    assert len(b2025) == 1 and len(b2025[0]["members"]) == 2


def _dense_graph():
    """~18 milestones, 3 lanes, several 3-4-paper nodes in mid-canvas — the
    overlap-prone case the corner layout must handle."""
    ms = [
        _ms("F1", 2018, FOUND), _ms("F2", 2020, FOUND),
        _ms("A1", 2022, "A"),
        _ms("A2", 2024, "A"), _ms("A3", 2024, "A"), _ms("A4", 2024, "A"),   # 3 papers
        _ms("A5", 2025, "A"), _ms("A6", 2025, "A"),
        _ms("B1", 2024, "B"), _ms("B2", 2024, "B"),
        _ms("B3", 2025, "B"), _ms("B4", 2025, "B"), _ms("B5", 2025, "B"),   # 3 papers
        _ms("C2", 2024, "C"), _ms("C3", 2024, "C"), _ms("C4", 2024, "C"), _ms("C5", 2024, "C"),  # 4 papers
        _ms("Z", 2026, "A"),                                                 # keeps 2024/25 off the edge
    ]
    return MilestoneGraph("Dense", ms,
                          [Branch("A", "压缩淘汰", "C"), Branch("B", "系统引擎", "S"),
                           Branch("C", "量化存储", "Q")],
                          [Era("奠基", "F", 2018, 2022), Era("爆发", "B", 2024, 2026)], True, {})


def test_dense_graph_no_label_overlap():
    """Core invariant: collision-aware corner placement yields no overlapping
    label boxes on a dense graph (nodes with up to 4 papers)."""
    from src.figure1_layout import _boxes_overlap
    L = compute_layout(_dense_graph())
    boxes = [p["bbox"] for g in L["groups"] for p in g["placements"]]
    assert boxes
    overlaps = [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))
                if _boxes_overlap(boxes[i], boxes[j])]
    assert not overlaps, f"{len(overlaps)} overlapping label pairs out of {len(boxes)} labels"


def test_isolated_four_paper_node_uses_all_four_corners():
    """A 4-paper node in open space spreads its labels across all four corners."""
    ms = [_ms("Anc", 2020, FOUND), _ms("Late", 2026, FOUND),
          _ms("X1", 2023, "A"), _ms("X2", 2023, "A"),
          _ms("X3", 2023, "A"), _ms("X4", 2023, "A")]
    g = MilestoneGraph("Iso", ms, [Branch("A", "lane", "L")],
                       [Era("e", "E", 2020, 2026)], True, {})
    node = next(gr for gr in compute_layout(g)["groups"] if gr["branch"] == "A")
    assert len(node["placements"]) == 4
    sigs = {(p["ty"] < node["y"], p["anchor"]) for p in node["placements"]}
    assert sigs == {(True, "start"), (True, "end"), (False, "start"), (False, "end")}
