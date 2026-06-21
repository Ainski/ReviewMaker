from tests._poster_fixtures import sample_graph, SAMPLE_REVIEW
from src.poster_data import build_poster_data
from src.poster_render import render_poster_html


class _P:
    has_code = True
    year = 2024


def test_render_contains_all_regions():
    data = build_poster_data("我的主题 TopicX", SAMPLE_REVIEW, [_P()] * 4, sample_graph())
    html = render_poster_html(data, '<svg id="hero"><circle/></svg>')
    for needle in ["TopicX", "综述论文", "<svg id=\"hero\"",
                   "方法体系分类", "横向对比", "节选自综述",
                   "性能·效率", "class=\"poster\"", "Jost"]:
        assert needle in html, needle
    # CJK auto-wrapped for title weight
    assert 'class="zh"' in html


def test_render_escapes_text():
    data = build_poster_data("A & B <x>", SAMPLE_REVIEW, [_P()] * 2, sample_graph())
    html = render_poster_html(data, "<svg/>")
    assert "A &amp; B" in html
