from alcana_bot.price_data import load_price_list
from alcana_bot.pricing import LineItem
from alcana_bot.presentation import build_category_choices, build_group_choices, format_quote, format_cart_review

PRICE_LIST = load_price_list("data/price_list.json")

def test_build_group_choices_returns_every_group_with_a_display_name():
    groups = build_group_choices(PRICE_LIST, "ru")
    ids = [g[0] for g in groups]
    assert "volumetric_letters" in ids
    assert all(name for _, name in groups)

def test_build_category_choices_scoped_to_a_group_only_returns_that_groups_items():
    choices = build_category_choices(PRICE_LIST, "ru", group_id="volumetric_letters")
    ids = [c[0] for c in choices]
    assert "letters_acrylic_led" in ids
    assert "banner_300gr" not in ids

def test_build_category_choices_unknown_group_returns_empty():
    assert build_category_choices(PRICE_LIST, "ru", group_id="does_not_exist") == []

def test_build_category_choices_excludes_fee_addons():
    choices = build_category_choices(PRICE_LIST, "ru")
    ids = [c[0] for c in choices]
    assert "measurement_fee" not in ids
    assert "install_travel_fee" not in ids
    assert "banner_300gr" in ids

def test_build_category_choices_uses_real_price_list_names():
    names = dict(build_category_choices(PRICE_LIST, "ru"))
    assert names["letters_acrylic_photon_led"] == "Объёмные буквы Акрил Фотон ДИОД"
    assert names["banner_300gr"] == "Баннер 300 гр"
    # No machine ids leak through as button labels.
    assert "Letters Acrylic Photon Led" not in names.values()

def test_build_category_choices_prefers_uzbek_name_when_available():
    ru_names = dict(build_category_choices(PRICE_LIST, "ru"))
    uz_names = dict(build_category_choices(PRICE_LIST, "uz"))
    # Every category resolves to a non-empty, non-id label in both languages.
    for category_id, name in uz_names.items():
        assert name and name != category_id
    # A category carrying only a generic `name` renders identically in both.
    assert uz_names["banner_300gr"] == ru_names["banner_300gr"] == "Баннер 300 гр"

def test_format_quote_includes_all_lines_and_total():
    items = [
        LineItem(label="banner_300gr", detail="200x150 см", unit_price=30000, quantity=3.0, total=90000),
        LineItem(label="design_service", detail="1 hour", unit_price=150000, quantity=1, total=150000),
    ]
    message = format_quote(items, "ru", PRICE_LIST)
    assert "90000" in message.replace(" ", "")
    assert "150000" in message.replace(" ", "")
    assert "240000" in message.replace(" ", "")  # total

def test_format_quote_shows_real_product_names_not_ids():
    items = [
        LineItem(label="letters_acrylic_photon_led", detail="6 буквы x 80см", unit_price=15500, quantity=6, total=93000),
        LineItem(label="install_travel_fee", detail="10-20 км", unit_price=150000, quantity=1, total=150000),
    ]
    message = format_quote(items, "ru", PRICE_LIST)
    assert "Объёмные буквы Акрил Фотон ДИОД" in message
    assert "Выезд на установку (по расстоянию)" in message
    assert "letters_acrylic_photon_led" not in message

def test_format_quote_falls_back_to_raw_label_for_unknown_category():
    items = [LineItem(label="not_a_category", detail="", unit_price=1, quantity=1, total=1)]
    assert "not_a_category" in format_quote(items, "ru", PRICE_LIST)

def test_format_cart_review_lists_every_item_and_shows_the_latest_addition():
    items = [
        LineItem(label="banner_300gr", detail="200x150 см", unit_price=30000, quantity=3.0, total=90000),
        LineItem(label="design_service", detail="2 hour", unit_price=150000, quantity=2, total=300000),
    ]
    text = format_cart_review(items, "ru", PRICE_LIST)
    assert "Баннер 300 гр" in text
    assert "Дизайн хизмати" in text
    assert "90 000" in text
    assert "300 000" in text
    assert "Добавлено" in text  # the "just added" header uses the LAST item
