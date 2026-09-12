from alcana_bot.price_data import load_price_list
from alcana_bot.pricing import LineItem
from alcana_bot.presentation import build_category_choices, format_quote

PRICE_LIST = load_price_list("data/price_list.json")

def test_build_category_choices_excludes_fee_addons():
    choices = build_category_choices(PRICE_LIST)
    ids = [c[0] for c in choices]
    assert "measurement_fee" not in ids
    assert "install_travel_fee" not in ids
    assert "banner_300gr" in ids

def test_format_quote_includes_all_lines_and_total():
    items = [
        LineItem(label="banner_300gr", detail="200x150 см", unit_price=30000, quantity=3.0, total=90000),
        LineItem(label="design_service", detail="1 hour", unit_price=150000, quantity=1, total=150000),
    ]
    message = format_quote(items, "ru")
    assert "90000" in message.replace(" ", "")
    assert "150000" in message.replace(" ", "")
    assert "240000" in message.replace(" ", "")  # total
