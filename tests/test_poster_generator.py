import os
from tests._poster_fixtures import sample_graph, SAMPLE_REVIEW
from src.poster_generator import generate_poster


class _P:
    has_code = True
    year = 2024


def test_generate_poster_writes_html(tmp_path):
    res = generate_poster("主题 X", SAMPLE_REVIEW, [_P()] * 4, sample_graph(),
                          str(tmp_path), rasterize=False)
    assert os.path.exists(res["html"])
    html = open(res["html"], encoding="utf-8").read()
    assert "主题" in html and "<svg" in html and "方法体系分类" in html
    assert res["png"] is None
