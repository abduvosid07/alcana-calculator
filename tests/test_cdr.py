import pytest
from alcana_bot.cdr import parse_svg_page_size, CdrExtractionError

def test_parse_svg_page_size_mm():
    svg = '<svg width="680mm" height="80mm" xmlns="http://www.w3.org/2000/svg"></svg>'
    width_cm, height_cm = parse_svg_page_size(svg)
    assert width_cm == pytest.approx(68.0)
    assert height_cm == pytest.approx(8.0)

def test_parse_svg_page_size_px_assumes_96dpi():
    # 96px = 1 inch = 2.54cm
    svg = '<svg width="96px" height="192px" xmlns="http://www.w3.org/2000/svg"></svg>'
    width_cm, height_cm = parse_svg_page_size(svg)
    assert width_cm == pytest.approx(2.54)
    assert height_cm == pytest.approx(5.08)

def test_parse_svg_page_size_pt():
    # 72pt = 1 inch = 2.54cm
    svg = '<svg width="72pt" height="144pt" xmlns="http://www.w3.org/2000/svg"></svg>'
    width_cm, height_cm = parse_svg_page_size(svg)
    assert width_cm == pytest.approx(2.54)
    assert height_cm == pytest.approx(5.08)

def test_parse_svg_page_size_missing_dimensions_raises():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    with pytest.raises(CdrExtractionError, match="width/height"):
        parse_svg_page_size(svg)

def test_parse_svg_page_size_malformed_numeric_value_raises():
    # Malformed numeric value like "1.2.3cm" passes regex but fails float()
    svg = '<svg width="1.2.3cm" height="80mm" xmlns="http://www.w3.org/2000/svg"></svg>'
    with pytest.raises(CdrExtractionError, match="Invalid numeric value"):
        parse_svg_page_size(svg)
