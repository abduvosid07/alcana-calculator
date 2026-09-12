import pytest
from alcana_bot.price_data import load_price_list
from alcana_bot.pricing import (
    price_fixed, price_fixed_options, price_per_sqm, price_per_sqm_options,
    price_per_letter_by_height, price_per_unit, resolve_distance_bracket,
    PricingError,
)

PRICE_LIST = load_price_list("data/price_list.json")

def test_price_fixed():
    category = PRICE_LIST.categories["lightbox_rr_60b"]
    item = price_fixed(category)
    assert item.total == 1150000
    assert isinstance(item.total, int)
    assert item.quantity == 1

def test_price_fixed_options():
    category = PRICE_LIST.categories["standee"]
    item = price_fixed_options(category, option_index=2)
    assert item.total == 1100000
    assert isinstance(item.total, int)
    assert "Алюкабонд" in item.detail

def test_price_per_sqm():
    category = PRICE_LIST.categories["banner_300gr"]
    item = price_per_sqm(category, width_cm=200, height_cm=150)
    assert item.total == 90000  # 3.0 sqm * 30000
    assert isinstance(item.total, int)

def test_price_per_sqm_options():
    category = PRICE_LIST.categories["acrylic_lightbox"]
    item = price_per_sqm_options(category, option_index=1, width_cm=100, height_cm=100)
    assert item.total == 2800000  # 1.0 sqm * 2,800,000 (double-sided)
    assert isinstance(item.total, int)

def test_price_per_letter_by_height_exact_match():
    category = PRICE_LIST.categories["letters_acrylic_led"]
    item = price_per_letter_by_height(category, letter_count=5, height_cm=80)
    assert item.total == 47500  # 5 * 9,500
    assert isinstance(item.total, int)

def test_price_per_letter_by_height_rounds_up_to_next_bracket():
    category = PRICE_LIST.categories["letters_acrylic_led"]
    item = price_per_letter_by_height(category, letter_count=2, height_cm=90)
    assert item.unit_price == 13000  # rounds up 90 -> 100cm bracket
    assert item.total == 26000
    assert isinstance(item.total, int)

def test_price_per_letter_by_height_above_max_raises():
    category = PRICE_LIST.categories["letters_acrylic_led"]
    with pytest.raises(PricingError, match="no price bracket"):
        price_per_letter_by_height(category, letter_count=1, height_cm=150)

def test_price_per_unit_hour():
    category = PRICE_LIST.categories["design_service"]
    item = price_per_unit(category, quantity=2)
    assert item.total == 300000  # 2 hours * 150,000
    assert isinstance(item.total, int)

def test_resolve_distance_bracket():
    category = PRICE_LIST.categories["install_travel_fee"]
    item = resolve_distance_bracket(category, distance_km=25)
    assert item.total == 200000
    assert isinstance(item.total, int)

def test_resolve_distance_bracket_beyond_max_raises():
    category = PRICE_LIST.categories["install_travel_fee"]
    with pytest.raises(PricingError, match="no distance bracket"):
        resolve_distance_bracket(category, distance_km=150)

def test_price_fixed_options_out_of_range_raises():
    """Test that out-of-range option_index raises PricingError, not IndexError."""
    category = PRICE_LIST.categories["standee"]
    with pytest.raises(PricingError, match="option_index .* out of range"):
        price_fixed_options(category, option_index=999)

def test_price_per_sqm_options_out_of_range_raises():
    """Test that out-of-range option_index raises PricingError, not IndexError."""
    category = PRICE_LIST.categories["acrylic_lightbox"]
    with pytest.raises(PricingError, match="option_index .* out of range"):
        price_per_sqm_options(category, option_index=999, width_cm=100, height_cm=100)

def test_price_per_letter_by_height_empty_brackets_raises():
    """Test that Category with empty height_prices raises PricingError."""
    from alcana_bot.price_data import Category
    # Create a synthetic Category with empty height_prices list
    category = Category(
        id="test_empty_brackets",
        pricing_type="letter_by_height",
        price=None,
        unit=None,
        options=None,
        height_prices=[],  # Empty list
        brackets=None,
    )
    with pytest.raises(PricingError, match="has no height_prices configured"):
        price_per_letter_by_height(category, letter_count=1, height_cm=80)

def test_price_per_letter_by_height_none_brackets_raises():
    """Test that Category with None height_prices raises PricingError."""
    from alcana_bot.price_data import Category
    # Create a synthetic Category with None height_prices
    category = Category(
        id="test_none_brackets",
        pricing_type="letter_by_height",
        price=None,
        unit=None,
        options=None,
        height_prices=None,  # None value
        brackets=None,
    )
    with pytest.raises(PricingError, match="has no height_prices configured"):
        price_per_letter_by_height(category, letter_count=1, height_cm=80)
