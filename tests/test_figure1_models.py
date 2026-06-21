from dataclasses import asdict

from src.figure1_models import Milestone, Branch, Era, MilestoneGraph, FOUND


def test_models_construct():
    m = Milestone(name="FlashAttention", authors="Dao et al", year=2022, branch=FOUND,
                  contrib="IO-aware 精确注意力", paper_index=None,
                  full_title="FlashAttention: ...", venue="NeurIPS 2022",
                  cited_by=3500, has_code=True, abstract="…", openalex_id="W1")
    g = MilestoneGraph(topic="t", milestones=[m],
                       branches=[Branch("A", "压缩", "COMPRESSION")],
                       eras=[Era("奠基", "FOUNDATIONS", 2017, 2023)],
                       enough=True, metrics={})
    assert g.milestones[0].branch == FOUND
    assert g.enough is True
    # dataclasses are asdict-serializable (used when dumping nodes/metrics)
    d = asdict(g)
    assert d["branches"][0]["id"] == "A"
    assert d["eras"][0]["y0"] == 2017


def test_found_constant():
    assert FOUND == "__found__"
