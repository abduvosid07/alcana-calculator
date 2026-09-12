import json
from dataclasses import dataclass

class PriceDataError(Exception):
    pass

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

@dataclass(frozen=True)
class PriceList:
    categories: dict
    bundle_defaults: dict
    workshop_origin: dict

def load_price_list(path: str) -> PriceList:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    categories = {}
    for entry in raw["categories"]:
        if "pricing_type" not in entry:
            raise PriceDataError(f"Category '{entry.get('id', '?')}' is missing required field: pricing_type")
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
        )

    return PriceList(
        categories=categories,
        bundle_defaults=raw["bundle_defaults"],
        workshop_origin=raw["workshop_origin"],
    )
