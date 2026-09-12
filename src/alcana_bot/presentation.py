from alcana_bot.price_data import PriceList
from alcana_bot.pricing import LineItem
from alcana_bot.bundle import bundle_total
from alcana_bot.i18n import t

_ADDON_CATEGORY_IDS = {"measurement_fee", "install_travel_fee"}

def build_category_choices(price_list: PriceList, lang: str) -> list[tuple[str, str]]:
    return [
        (category.id, category.display_name(lang))
        for category_id, category in price_list.categories.items()
        if category_id not in _ADDON_CATEGORY_IDS
    ]

def _resolve_label(price_list: PriceList, label: str, lang: str) -> str:
    """Turn a LineItem's category id into the real price-list product name.

    Labels are stored as category ids (language-neutral) so the same quote can
    be rendered in either language; the display name is resolved here, at the
    point where the language is actually known.
    """
    category = price_list.categories.get(label)
    return category.display_name(lang) if category is not None else label

def format_quote(items: list[LineItem], lang: str, price_list: PriceList) -> str:
    lines = [
        t(
            "quote_line_item",
            lang,
            label=_resolve_label(price_list, item.label, lang),
            detail=item.detail,
            total=f"{item.total:,}".replace(",", " "),
        )
        for item in items
    ]
    total = bundle_total(items)
    lines.append(t("quote_total", lang, total=f"{total:,}".replace(",", " ")))
    return "\n".join(lines)
