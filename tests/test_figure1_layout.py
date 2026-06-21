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
        assert "x" in grp and "y" in grp and len(grp["sides"]) == len(grp["members"])
    # the (B,2025) group carries both papers under one node
    b2025 = [g for g in L["groups"] if g["branch"] == "B" and g["year"] == 2025]
    assert len(b2025) == 1 and len(b2025[0]["members"]) == 2
