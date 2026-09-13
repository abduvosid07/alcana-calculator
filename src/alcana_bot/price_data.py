import json
from dataclasses import dataclass, field

class PriceDataError(Exception):
    pass

KNOWN_PRICING_TYPES = {
    "fixed",
    "fixed_options",
    "per_sqm",
    "per_sqm_options",
    "per_letter_by_height",
    "per_hour",
    "per_minute",
    "per_meter",
    "distance_bracket",
}

_ADDON_CATEGORY_IDS = {"measurement_fee", "install_travel_fee"}


def _pick_name(name_uz: str | None, name_ru: str | None, name: str | None, id_: str, lang: str) -> str:
    """Shared display-name fallback: language-specific -> generic -> other language -> id."""
    preferred = name_uz if lang == "uz" else name_ru
    other = name_ru if lang == "uz" else name_uz
    for candidate in (preferred, name, other):
        if candidate:
            return candidate
    return id_.replace("_", " ").title()


@dataclass(frozen=True)
class Category:
    id: str
    pricing_type: str
    unit: str
    requires_dimensions: bool = False
    price: int | None = None
    options: list | None = None
    height_prices: list | None = None
    brackets: list | None = None
    extraction_mode: str | None = None
    name: str | None = None
    name_ru: str | None = None
    name_uz: str | None = None

    def display_name(self, lang: str = "ru") -> str:
        """Human-readable product name for the given language.

        Falls back through: language-specific name -> generic ``name`` ->
        the other language-specific name -> a title-cased version of the id.
        ``data/price_list.json`` is inconsistent (most entries carry only
        ``name``, a couple carry ``name_ru``/``name_uz``), so every step has
        to be optional.
        """
        return _pick_name(self.name_uz, self.name_ru, self.name, self.id, lang)


@dataclass(frozen=True)
class CategoryGroup:
    id: str
    name_ru: str
    name_uz: str
    category_ids: list

    def display_name(self, lang: str = "ru") -> str:
        return _pick_name(self.name_uz, self.name_ru, None, self.id, lang)


@dataclass(frozen=True)
class PriceList:
    categories: dict
    bundle_defaults: dict
    workshop_origin: dict
    category_groups: list = field(default_factory=list)

def _validate_entry(category_id: str, pricing_type: str, entry: dict) -> None:
    """Fail loudly at load time on a pricing_type the bot cannot price.

    Without this an unknown/typo'd pricing_type silently fell through to the
    `fixed` branch in bot.py and mispriced the order.
    """
    if pricing_type not in KNOWN_PRICING_TYPES:
        raise PriceDataError(
            f"Category '{category_id}' has unknown pricing_type '{pricing_type}' "
            f"(known types: {', '.join(sorted(KNOWN_PRICING_TYPES))})"
        )

    if pricing_type in ("fixed", "per_sqm", "per_hour", "per_minute", "per_meter"):
        if entry.get("price") is None:
            raise PriceDataError(f"Category '{category_id}' (pricing_type '{pricing_type}') is missing required field: price")
    elif pricing_type in ("fixed_options", "per_sqm_options"):
        if not entry.get("options"):
            raise PriceDataError(f"Category '{category_id}' (pricing_type '{pricing_type}') is missing required non-empty field: options")
    elif pricing_type == "per_letter_by_height":
        if not entry.get("height_prices"):
            raise PriceDataError(f"Category '{category_id}' (pricing_type '{pricing_type}') is missing required non-empty field: height_prices")
    elif pricing_type == "distance_bracket":
        if not entry.get("brackets"):
            raise PriceDataError(f"Category '{category_id}' (pricing_type '{pricing_type}') is missing required non-empty field: brackets")


def _validate_groups(groups: list, categories: dict) -> None:
    """Fail loudly if the menu grouping is out of sync with the category list.

    Without this a category left out of every group would be silently
    unreachable through the two-level menu, and a typo'd id inside a group
    would silently drop that product from the menu instead of erroring.
    """
    seen = set()
    for group in groups:
        for category_id in group.category_ids:
            if category_id not in categories:
                raise PriceDataError(f"category_groups: group '{group.id}' references unknown category '{category_id}'")
            if category_id in seen:
                raise PriceDataError(f"category_groups: category '{category_id}' appears in more than one group")
            seen.add(category_id)

    missing = set(categories) - _ADDON_CATEGORY_IDS - seen
    if missing:
        raise PriceDataError(f"category_groups: categories not assigned to any group: {', '.join(sorted(missing))}")


def load_price_list(path: str) -> PriceList:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    categories = {}
    for entry in raw["categories"]:
        if "pricing_type" not in entry:
            raise PriceDataError(f"Category '{entry.get('id', '?')}' is missing required field: pricing_type")
        _validate_entry(entry.get("id", "?"), entry["pricing_type"], entry)
        categories[entry["id"]] = Category(
            id=entry["id"],
            pricing_type=entry["pricing_type"],
            unit=entry.get("unit", "pc"),
            requires_dimensions=entry.get("requires_dimensions", False),
            price=entry.get("price"),
            options=entry.get("options"),
            height_prices=entry.get("height_prices"),
            brackets=entry.get("brackets"),
            extraction_mode=entry.get("extraction_mode"),
            name=entry.get("name"),
            name_ru=entry.get("name_ru"),
            name_uz=entry.get("name_uz"),
        )

    category_groups = [
        CategoryGroup(
            id=group["id"],
            name_ru=group["name_ru"],
            name_uz=group["name_uz"],
            category_ids=list(group["categories"]),
        )
        for group in raw.get("category_groups", [])
    ]
    if category_groups:
        _validate_groups(category_groups, categories)

    return PriceList(
        categories=categories,
        bundle_defaults=raw["bundle_defaults"],
        workshop_origin=raw["workshop_origin"],
        category_groups=category_groups,
    )
