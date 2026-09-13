from alcana_bot.pricing import LineItem

def assemble_bundle(main_items: list[LineItem], design_item: LineItem | None = None, travel_item: LineItem | None = None) -> list[LineItem]:
    items = list(main_items)
    if design_item is not None:
        items.append(design_item)
    if travel_item is not None:
        items.append(travel_item)
    return items

def bundle_total(items: list[LineItem]) -> int:
    return sum(item.total for item in items)
