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

def price_fixed(category: Category, quantity: int = 1) -> LineItem:
    if category.price is None:
        raise PricingError(f"{category.id}: has no price configured")
    if quantity < 1:
        raise PricingError(f"{category.id}: quantity must be at least 1 (got {quantity})")
    return LineItem(
        label=category.id,
        detail=f"{quantity} шт",
        unit_price=category.price,
        quantity=quantity,
        total=category.price * quantity,
    )

def price_fixed_options(category: Category, option_index: int, quantity: int = 1) -> LineItem:
    try:
        option = category.options[option_index]
    except IndexError:
        raise PricingError(f"{category.id}: option_index {option_index} out of range (options available: {len(category.options)})")
    if quantity < 1:
        raise PricingError(f"{category.id}: quantity must be at least 1 (got {quantity})")
    price = option["price"]
    detail = f"{option.get('label', '')} — {quantity} шт".strip(" —")
    return LineItem(label=category.id, detail=detail, unit_price=price, quantity=quantity, total=price * quantity)

def _area_sqm(width_cm: float, height_cm: float) -> float:
    return (width_cm / 100.0) * (height_cm / 100.0)

def price_per_sqm(category: Category, width_cm: float, height_cm: float) -> LineItem:
    area = _area_sqm(width_cm, height_cm)
    total = round(area * category.price)
    return LineItem(label=category.id, detail=f"{width_cm}x{height_cm} см", unit_price=category.price, quantity=area, total=total)

def price_per_sqm_options(category: Category, option_index: int, width_cm: float, height_cm: float) -> LineItem:
    try:
        option = category.options[option_index]
    except IndexError:
        raise PricingError(f"{category.id}: option_index {option_index} out of range (options available: {len(category.options)})")
    area = _area_sqm(width_cm, height_cm)
    unit_price = option["price_per_sqm"]
    total = round(area * unit_price)
    return LineItem(label=category.id, detail=f"{option.get('label', '')} {width_cm}x{height_cm} см", unit_price=unit_price, quantity=area, total=total)

def price_per_letter_by_height(category: Category, letter_count: int, height_cm: float) -> LineItem:
    """Price is per centimeter of actual letter height, per letter.

    height_prices entries give the rate (so'm/cm) for the bracket the letter's
    height falls into -- e.g. up to 60cm costs 8,500 so'm per cm. The rate
    rounds up to the next bracket once height exceeds it, but the ACTUAL
    height is what gets billed (you pay for the real cm of material produced,
    at the rate for your size tier), not the bracket's nominal height.
    """
    if category.height_prices is None:
        raise PricingError(f"{category.id}: has no height_prices configured")
    brackets = sorted(category.height_prices, key=lambda hp: hp["height_cm"])
    if not brackets:
        raise PricingError(f"{category.id}: has no height_prices configured")
    match = next((hp for hp in brackets if hp["height_cm"] >= height_cm), None)
    if match is None:
        raise PricingError(f"{category.id}: no price bracket covers height {height_cm}cm (max is {brackets[-1]['height_cm']}cm)")
    rate_per_cm = match["price"]
    total = round(rate_per_cm * height_cm * letter_count)
    return LineItem(label=category.id, detail=f"{letter_count} буквы x {height_cm}см", unit_price=rate_per_cm, quantity=letter_count, total=total)

def price_per_unit(category: Category, quantity: float) -> LineItem:
    total = round(category.price * quantity)
    return LineItem(label=category.id, detail=f"{quantity} {category.unit}", unit_price=category.price, quantity=quantity, total=total)

def resolve_distance_bracket(category: Category, distance_km: float) -> LineItem:
    if category.brackets is None:
        raise PricingError(f"{category.id}: has no distance brackets configured")
    match = next((b for b in category.brackets if b["min_km"] <= distance_km <= b["max_km"]), None)
    if match is None:
        raise PricingError(f"{category.id}: no distance bracket covers {distance_km}km")
    return LineItem(label=category.id, detail=f"{distance_km:.0f} км", unit_price=match["price"], quantity=1, total=match["price"])
