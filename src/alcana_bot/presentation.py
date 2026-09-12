from alcana_bot.price_data import PriceList
from alcana_bot.pricing import LineItem
from alcana_bot.bundle import bundle_total
from alcana_bot.i18n import t

_ADDON_CATEGORY_IDS = {"measurement_fee", "install_travel_fee"}

def build_category_choices(price_list: PriceList) -> list[tuple[str, str]]:
    return [
        (category_id, category_id.replace("_", " ").title())
        for category_id in price_list.categories
        if category_id not in _ADDON_CATEGORY_IDS
    ]

def format_quote(items: list[LineItem], lang: str) -> str:
    lines = [
        t("quote_line_item", lang, label=item.label, detail=item.detail, total=f"{item.total:,}".replace(",", " "))
        for item in items
    ]
    total = bundle_total(items)
    lines.append(t("quote_total", lang, total=f"{total:,}".replace(",", " ")))
    return "\n".join(lines)
