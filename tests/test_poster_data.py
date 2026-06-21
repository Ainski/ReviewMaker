from tests._poster_fixtures import sample_graph
from src.poster_data import build_stats, build_taxonomy


class _P:
    def __init__(self, has_code): self.has_code = has_code; self.year = 2024


def test_build_stats_counts_papers_and_code_pct():
    papers = [_P(True), _P(True), _P(True), _P(False)]  # 3/4 = 75%
    stats = build_stats(sample_graph(), papers)
    assert [s.value for s in stats] == ["4", "75%", "3", "10"]  # 2017..2026 -> 10 yrs
    assert stats[0].accent is True


def test_build_taxonomy_counts_and_normalizes():
    bars = build_taxonomy(sample_graph())
    names = {b.name: b.count for b in bars}
    assert names["KV Cache 压缩与淘汰"] == 2  # Ada-KV + ReST-KV
    assert names["奠基性工作 Foundational"] == 2  # Transformer + FlashAttention
    assert max(b.width_pct for b in bars) == 100
