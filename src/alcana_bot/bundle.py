from alcana_bot.pricing import LineItem

def assemble_bundle(main_item: LineItem, design_item: LineItem | None = None, travel_item: LineItem | None = None) -> list[LineItem]:
    items = [main_item]
    if design_item is not None:
        items.append(design_item)
    if travel_item is not None:
        items.append(travel_item)
    return items

def bundle_total(items: list[LineItem]) -> int:
    return sum(item.total for item in items)
