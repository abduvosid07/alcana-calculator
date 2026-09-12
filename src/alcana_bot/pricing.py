import math
from dataclasses import dataclass
from alcana_bot.price_data import Category

class PricingError(Exception):
    pass

@dataclass(frozen=True)
class LineItem:
    label: str
    detail: str
    unit_price: int
    quantity: float
    total: int

def price_fixed(category: Category) -> LineItem:
    return LineItem(label=category.id, detail="", unit_price=category.price, quantity=1, total=category.price)

def price_fixed_options(category: Category, option_index: int) -> LineItem:
    option = category.options[option_index]
    price = option["price"]
    return LineItem(label=category.id, detail=option.get("label", ""), unit_price=price, quantity=1, total=price)

def _area_sqm(width_cm: float, height_cm: float) -> float:
    return (width_cm / 100.0) * (height_cm / 100.0)

def price_per_sqm(category: Category, width_cm: float, height_cm: float) -> LineItem:
    area = _area_sqm(width_cm, height_cm)
    total = round(area * category.price)
    return LineItem(label=category.id, detail=f"{width_cm}x{height_cm} см", unit_price=category.price, quantity=area, total=total)

def price_per_sqm_options(category: Category, option_index: int, width_cm: float, height_cm: float) -> LineItem:
    option = category.options[option_index]
    area = _area_sqm(width_cm, height_cm)
    unit_price = option["price_per_sqm"]
    total = round(area * unit_price)
    return LineItem(label=category.id, detail=f"{option.get('label', '')} {width_cm}x{height_cm} см", unit_price=unit_price, quantity=area, total=total)

def price_per_letter_by_height(category: Category, letter_count: int, height_cm: float) -> LineItem:
    brackets = sorted(category.height_prices, key=lambda hp: hp["height_cm"])
    match = next((hp for hp in brackets if hp["height_cm"] >= height_cm), None)
    if match is None:
        raise PricingError(f"{category.id}: no price bracket covers height {height_cm}cm (max is {brackets[-1]['height_cm']}cm)")
    total = match["price"] * letter_count
    return LineItem(label=category.id, detail=f"{letter_count} буквы x {match['height_cm']}см", unit_price=match["price"], quantity=letter_count, total=total)

def price_per_unit(category: Category, quantity: float) -> LineItem:
    total = round(category.price * quantity)
    return LineItem(label=category.id, detail=f"{quantity} {category.unit}", unit_price=category.price, quantity=quantity, total=total)

def resolve_distance_bracket(category: Category, distance_km: float) -> LineItem:
    match = next((b for b in category.brackets if b["min_km"] <= distance_km <= b["max_km"]), None)
    if match is None:
        raise PricingError(f"{category.id}: no distance bracket covers {distance_km}km")
    return LineItem(label=category.id, detail=f"{distance_km:.0f} км", unit_price=match["price"], quantity=1, total=match["price"])
