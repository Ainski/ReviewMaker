import xml.etree.ElementTree as ET

from src.svg_poster_generator import _build_evolution


def test_evolution_embedded_as_nested_svg(tmp_path):
    evo = tmp_path / "evolution.svg"
    evo.write_text(
        '<svg viewBox="0 0 1460 760" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="0" y="0" width="10" height="10"/>'
        '<text>EVOMARKER123</text></svg>',
        encoding="utf-8")
    g, new_y = _build_evolution(0, 0, 400, str(evo))
    xml = ET.tostring(g, encoding="unicode")
    assert "EVOMARKER123" in xml          # evolution content is embedded (vector)
    assert "data:image" not in xml         # not rasterized to a base64 image
    assert new_y > 0


def test_evolution_missing_path_graceful(tmp_path):
    g, new_y = _build_evolution(0, 0, 400, str(tmp_path / "nope.svg"))
    xml = ET.tostring(g, encoding="unicode")
    assert "无法嵌入" in xml
    assert new_y > 0
