import os
import pytest
from src.poster_rasterize import find_chrome, rasterize_html

pytestmark = pytest.mark.skipif(find_chrome() is None, reason="no chrome/chromium")


def test_rasterize_produces_nonempty_png(tmp_path):
    html = ('<!DOCTYPE html><html><body style="margin:0">'
            '<div style="width:400px;height:300px;background:#6D5DF6"></div></body></html>')
    out = str(tmp_path / "out.png")
    rasterize_html(html, out, width=500, height=500)
    assert os.path.exists(out) and os.path.getsize(out) > 1000
