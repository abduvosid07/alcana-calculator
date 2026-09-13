from io import BytesIO

import pytest
from pypdf import PdfReader

from alcana_bot.pdf_export import render_quote_pdf, PdfExportError
from alcana_bot.pricing import LineItem
from alcana_bot.price_data import load_price_list

PRICE_LIST = load_price_list("data/price_list.json")


def make_item(label, detail, total):
    return LineItem(label=label, detail=detail, unit_price=total, quantity=1, total=total)


def test_render_quote_pdf_returns_pdf_bytes():
    items = [make_item("banner_300gr", "200x150 см", 90000)]
    pdf_bytes = render_quote_pdf(items, "ru", PRICE_LIST)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_render_quote_pdf_contains_product_name_and_amount():
    items = [make_item("banner_300gr", "200x150 см", 90000)]
    pdf_bytes = render_quote_pdf(items, "ru", PRICE_LIST)
    text = PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()
    assert "Баннер 300 гр" in text
    assert "90" in text and "000" in text


def test_render_quote_pdf_multiple_items_shows_grand_total():
    items = [
        make_item("banner_300gr", "200x150 см", 90000),
        make_item("design_service", "2 hour", 300000),
    ]
    pdf_bytes = render_quote_pdf(items, "uz", PRICE_LIST)
    text = PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()
    assert "390" in text  # 90 000 + 300 000 grand total


def test_render_quote_pdf_empty_items_raises():
    with pytest.raises(PdfExportError):
        render_quote_pdf([], "ru", PRICE_LIST)


def test_render_quote_pdf_unknown_font_path_raises_pdf_export_error(monkeypatch):
    monkeypatch.setattr("alcana_bot.pdf_export._FONT_REGULAR_PATH", r"C:\does\not\exist.ttf")
    monkeypatch.setattr("alcana_bot.pdf_export._registered", False)
    with pytest.raises(PdfExportError):
        render_quote_pdf([make_item("banner_300gr", "x", 1)], "ru", PRICE_LIST)
