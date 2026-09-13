from alcana_bot.pricing import LineItem
from alcana_bot.bundle import assemble_bundle, bundle_total

def make_item(total):
    return LineItem(label="x", detail="", unit_price=total, quantity=1, total=total)

def test_assemble_bundle_includes_all_main_items_and_addons():
    main1 = make_item(100000)
    main2 = make_item(50000)
    design = make_item(150000)
    travel = make_item(200000)
    items = assemble_bundle([main1, main2], design, travel)
    assert items == [main1, main2, design, travel]

def test_assemble_bundle_single_main_item_still_works():
    main = make_item(100000)
    items = assemble_bundle([main], design_item=None, travel_item=None)
    assert items == [main]

def test_assemble_bundle_omits_none_addons():
    main1 = make_item(100000)
    main2 = make_item(50000)
    items = assemble_bundle([main1, main2], design_item=None, travel_item=None)
    assert items == [main1, main2]

def test_bundle_total_sums_all_lines():
    items = [make_item(100000), make_item(150000), make_item(200000)]
    assert bundle_total(items) == 450000
