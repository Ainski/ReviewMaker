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


def test_select_excerpts_thicker_and_deduped():
    ex = select_excerpts(SAMPLE_REVIEW, budget=320,
                         exclude="未来的突破将更依赖多种优化技术的深度融合、对任务动态特性的在线感知。")
    assert len(ex) == 2
    assert "KV Cache 技术应运而生" in ex[0].text
    assert len(ex[0].text) > 150                 # 做厚:超过旧的 150 截断
    assert "量化类方法" in ex[1].text             # 核心结论换源到「横向对比」
    assert "深度融合" not in ex[1].text           # 去重:highlight 那句不重复出现


def test_build_lineage_excerpt_from_section_and_fallback_none():
    from src.poster_data import build_lineage_excerpt
    ex = build_lineage_excerpt(SAMPLE_REVIEW, budget=320)
    assert ex is not None
    assert "演进" in ex.heading
    assert "自注意力" in ex.text or "FlashAttention" in ex.text
    # 没有演进脉络/方法分类节 -> None
    assert build_lineage_excerpt("# 标题\n\n## 引言\n\n正文。") is None


def test_select_excerpts_fallback_when_no_sections():
    ex = select_excerpts("只有一段没有标题的纯文本，作为兜底。")
    assert len(ex) == 2
    assert ex[0].text  # non-empty fallback


def test_extract_highlight_picks_most_impactful_sentence():
    hl = extract_highlight(SAMPLE_REVIEW)
    # 含"未来/突破/融合"三个趋势词的那句,胜过仅含"关键"的首句
    assert "深度融合" in hl
    assert "本综述梳理" not in hl
    assert hl.endswith("。")


from tests._poster_fixtures import sample_graph as _sg
from src.poster_data import build_tradeoff, build_poster_data


def test_build_tradeoff_dims_and_rows():
    t = build_tradeoff("", _sg())
    assert t.dims == ["性能·效率", "可复现", "适用场景"]
    assert len(t.rows) == 3
    assert t.rows[0].name == "KV Cache 压缩与淘汰"
    assert t.rows[0].marks[2] == "长上下文"   # EVICTION scenario
    assert all(len(r.marks) == 3 for r in t.rows)


def test_build_poster_data_full():
    papers = [_P(True)] * 4
    d = build_poster_data("我的主题", SAMPLE_REVIEW, papers, _sg())
    assert d.title == "我的主题"
    assert len(d.stats) == 4 and len(d.excerpts) == 2
    assert len(d.taxonomy) == 4 and len(d.tradeoff.rows) == 3
    assert d.highlight and d.foot_left


from src.poster_data import _budget


def test_budget_scales_with_paper_count_and_caps():
    assert _budget(10) == 220
    assert _budget(20) == 320
    assert _budget(25) == 420
    assert _budget(100) == 420  # 硬上限


from src.poster_data import _extract_block


def test_extract_block_joins_paragraphs_up_to_budget():
    body = "第一段甲乙丙。\n\n第二段丁戊己。\n\n| 表格行 | 不要 |\n\n第三段庚辛壬。"
    out = _extract_block(body, 200)
    assert "第一段甲乙丙" in out
    assert "第二段丁戊己" in out
    assert "表格行" not in out          # 跳过表格行
    assert len(out) > len("第一段甲乙丙。")  # 比单段更厚


def test_extract_block_respects_budget():
    body = "。".join(f"句子{i}" for i in range(50)) + "。"
    out = _extract_block(body, 60)
    assert len(out) <= 62  # budget + 收尾标点容差
