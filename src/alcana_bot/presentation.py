from alcana_bot.price_data import PriceList
from alcana_bot.pricing import LineItem
from alcana_bot.bundle import bundle_total
from alcana_bot.i18n import t

_ADDON_CATEGORY_IDS = {"measurement_fee", "install_travel_fee"}

_ITEM_BULLETS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


def build_group_choices(price_list: PriceList, lang: str) -> list[tuple[str, str]]:
    return [(group.id, group.display_name(lang)) for group in price_list.category_groups]


def build_category_choices(price_list: PriceList, lang: str, group_id: str | None = None) -> list[tuple[str, str]]:
    if group_id is not None:
        group = next((g for g in price_list.category_groups if g.id == group_id), None)
        if group is None:
            return []
        return [
            (category_id, price_list.categories[category_id].display_name(lang))
            for category_id in group.category_ids
            if category_id in price_list.categories
        ]
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
    lines = [t("quote_header", lang), ""]
    for index, item in enumerate(items):
        bullet = _ITEM_BULLETS[index] if index < len(_ITEM_BULLETS) else "🔸"
        lines.append(
            t(
                "quote_line_item",
                lang,
                bullet=bullet,
                label=_resolve_label(price_list, item.label, lang),
                detail=item.detail,
                total=f"{item.total:,}".replace(",", " "),
            )
        )
    total = bundle_total(items)
    lines.append("")
    lines.append(t("quote_total", lang, total=f"{total:,}".replace(",", " ")))
    return "\n".join(lines)

def format_cart_review(items: list[LineItem], lang: str, price_list: PriceList) -> str:
    latest = items[-1]
    lines = [
        t(
            "cart_item_added",
            lang,
            label=_resolve_label(price_list, latest.label, lang),
            total=f"{latest.total:,}".replace(",", " "),
        ),
        "",
    ]
    for index, item in enumerate(items):
        bullet = _ITEM_BULLETS[index] if index < len(_ITEM_BULLETS) else "🔸"
        lines.append(
            t(
                "quote_line_item",
                lang,
                bullet=bullet,
                label=_resolve_label(price_list, item.label, lang),
                detail=item.detail,
                total=f"{item.total:,}".replace(",", " "),
            )
        )
    return "\n".join(lines)
