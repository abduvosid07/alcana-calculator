import json
import pytest
from alcana_bot.price_data import load_price_list, PriceDataError

REAL_PRICE_LIST_PATH = "data/price_list.json"

def test_load_real_price_list():
    price_list = load_price_list(REAL_PRICE_LIST_PATH)
    assert "banner_300gr" in price_list.categories
    banner = price_list.categories["banner_300gr"]
    assert banner.pricing_type == "per_sqm"
    assert banner.price == 30000

    letters = price_list.categories["letters_acrylic_led"]
    assert letters.pricing_type == "per_letter_by_height"
    assert letters.height_prices == [
        {"height_cm": 60, "price": 8500},
        {"height_cm": 80, "price": 9500},
        {"height_cm": 100, "price": 13000},
        {"height_cm": 120, "price": 16000},
    ]

    assert price_list.workshop_origin["latitude"] == 41.291234
    assert "design_service" in price_list.bundle_defaults["always_include"]

def test_load_price_list_missing_pricing_type_field(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({
        "categories": [{"id": "x", "unit": "pc"}],
        "bundle_defaults": {"always_include": []},
        "workshop_origin": {"latitude": 0, "longitude": 0},
    }))
    with pytest.raises(PriceDataError, match="pricing_type"):
        load_price_list(str(bad_file))
