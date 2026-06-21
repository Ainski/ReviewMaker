from tests._poster_fixtures import sample_graph, SAMPLE_REVIEW
from src.poster_data import build_stats, build_taxonomy, select_excerpts, extract_highlight


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


def test_select_excerpts_finds_background_and_conclusion():
    ex = select_excerpts(SAMPLE_REVIEW)
    assert len(ex) == 2
    assert "KV Cache 技术应运而生" in ex[0].text
    assert "深度融合" in ex[1].text
    assert "结论" in ex[1].source


def test_select_excerpts_fallback_when_no_sections():
    ex = select_excerpts("只有一段没有标题的纯文本，作为兜底。")
    assert len(ex) == 2
    assert ex[0].text  # non-empty fallback


def test_extract_highlight_is_first_conclusion_sentence():
    hl = extract_highlight(SAMPLE_REVIEW)
    assert hl.startswith("本综述梳理")
    assert hl.endswith("。")
