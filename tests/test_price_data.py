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

def test_load_real_price_list_loads_display_names():
    price_list = load_price_list(REAL_PRICE_LIST_PATH)
    letters = price_list.categories["letters_acrylic_photon_led"]
    assert letters.name == "Объёмные буквы Акрил Фотон ДИОД"
    assert letters.display_name("ru") == "Объёмные буквы Акрил Фотон ДИОД"

    travel = price_list.categories["install_travel_fee"]
    assert travel.display_name("ru") == "Выезд на установку (по расстоянию)"
    assert travel.display_name("uz") == "Установкага йўл кира харажати"

def test_display_name_falls_back_to_title_cased_id():
    from alcana_bot.price_data import Category
    category = Category(id="some_unnamed_thing", pricing_type="fixed", unit="pc", price=1)
    assert category.display_name("ru") == "Some Unnamed Thing"

def test_load_price_list_missing_pricing_type_field(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({
        "categories": [{"id": "x", "unit": "pc"}],
        "bundle_defaults": {"always_include": []},
        "workshop_origin": {"latitude": 0, "longitude": 0},
    }))
    with pytest.raises(PriceDataError, match="pricing_type"):
        load_price_list(str(bad_file))

def _write_price_list(tmp_path, category: dict):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({
        "categories": [category],
        "bundle_defaults": {"always_include": []},
        "workshop_origin": {"latitude": 0, "longitude": 0},
    }), encoding="utf-8")
    return str(bad_file)

def test_load_price_list_unknown_pricing_type_raises(tmp_path):
    """A typo'd pricing_type must fail loudly, not fall through to `fixed`."""
    path = _write_price_list(tmp_path, {"id": "x", "unit": "pc", "pricing_type": "per_sqm ", "price": 100})
    with pytest.raises(PriceDataError, match="unknown pricing_type"):
        load_price_list(path)

def test_load_price_list_per_sqm_missing_price_raises(tmp_path):
    path = _write_price_list(tmp_path, {"id": "x", "unit": "sqm", "pricing_type": "per_sqm"})
    with pytest.raises(PriceDataError, match="missing required field: price"):
        load_price_list(path)

def test_load_price_list_fixed_missing_price_raises(tmp_path):
    path = _write_price_list(tmp_path, {"id": "x", "unit": "pc", "pricing_type": "fixed"})
    with pytest.raises(PriceDataError, match="missing required field: price"):
        load_price_list(path)

def test_load_price_list_options_type_missing_options_raises(tmp_path):
    path = _write_price_list(tmp_path, {"id": "x", "unit": "pc", "pricing_type": "fixed_options", "options": []})
    with pytest.raises(PriceDataError, match="options"):
        load_price_list(path)

def test_load_price_list_letter_type_missing_height_prices_raises(tmp_path):
    path = _write_price_list(tmp_path, {"id": "x", "unit": "letter", "pricing_type": "per_letter_by_height"})
    with pytest.raises(PriceDataError, match="height_prices"):
        load_price_list(path)

def test_load_price_list_distance_bracket_missing_brackets_raises(tmp_path):
    path = _write_price_list(tmp_path, {"id": "x", "unit": "flat", "pricing_type": "distance_bracket", "brackets": []})
    with pytest.raises(PriceDataError, match="brackets"):
        load_price_list(path)
