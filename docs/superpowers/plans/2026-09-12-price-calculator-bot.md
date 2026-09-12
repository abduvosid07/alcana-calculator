# Alcana Price Calculator Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that lets Alcana staff send a design photo/`.cdr` file, answer a few questions, and get an itemized advertising-order price in Uzbek or Russian.

**Architecture:** A Python long-polling Telegram bot (`python-telegram-bot`) with pure, independently-testable modules for pricing math, distance calculation, CDR/photo dimension extraction, and i18n; a thin handler layer wires them into a conversation flow. Price data lives in a JSON file edited directly for price updates.

**Tech Stack:** Python 3.11+, `python-telegram-bot`, `anthropic` (Claude Haiku 4.5 for vision extraction), `requests` (Yandex Maps HTTP), `pytest`.

**Spec:** [docs/superpowers/specs/2026-09-12-price-calculator-bot-design.md](../specs/2026-09-12-price-calculator-bot-design.md)

## Global Constraints

- Currency is UZS everywhere; all prices are plain integers (no decimals).
- Long-polling only — no webhook, no open inbound port (must run on a server with outbound-only internet access).
- All secrets (`TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `YANDEX_MAPS_API_KEY`) come from environment variables only — never hardcoded, never logged.
- Price data lives in `data/price_list.json`; a pure price change must never require a code change.
- Workshop origin is fixed: latitude `41.291234`, longitude `69.196435` (already in `data/price_list.json` → `workshop_origin`).
- The bot must never silently guess a dimension, letter count, or distance bracket — every extraction/calculation failure falls back to asking staff to type the value.
- Vision extraction model is `claude-haiku-4-5` (not a larger model — this is a narrow extraction task; see spec rationale).
- Users are internal staff only — no customer-facing wording or flows.

---

## Task 1: Project scaffolding and config loader

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/alcana_bot/__init__.py`
- Create: `src/alcana_bot/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` dataclass with fields `telegram_bot_token: str`, `anthropic_api_key: str`, `yandex_maps_api_key: str`; function `load_config(env: dict) -> Config`.

- [ ] **Step 1: Create requirements, gitignore, env example**

`requirements.txt`:
```
python-telegram-bot==21.6
anthropic==0.40.0
requests==2.32.3
python-dotenv==1.0.1
defusedxml==0.7.1
pytest==8.3.3
pytest-mock==3.14.0
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
.env
data/user_lang.json
*.egg-info/
.superpowers/
```

`.env.example`:
```
TELEGRAM_BOT_TOKEN=
ANTHROPIC_API_KEY=
YANDEX_MAPS_API_KEY=
```

`src/alcana_bot/__init__.py`: empty file.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_config.py
import pytest
from alcana_bot.config import load_config, ConfigError

def test_load_config_success():
    env = {
        "TELEGRAM_BOT_TOKEN": "tg-token",
        "ANTHROPIC_API_KEY": "ant-key",
        "YANDEX_MAPS_API_KEY": "ya-key",
    }
    config = load_config(env)
    assert config.telegram_bot_token == "tg-token"
    assert config.anthropic_api_key == "ant-key"
    assert config.yandex_maps_api_key == "ya-key"

def test_load_config_missing_vars_lists_all_missing():
    env = {"TELEGRAM_BOT_TOKEN": "tg-token"}
    with pytest.raises(ConfigError) as exc_info:
        load_config(env)
    message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "YANDEX_MAPS_API_KEY" in message
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alcana_bot'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/alcana_bot/config.py
from dataclasses import dataclass

REQUIRED_VARS = ["TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "YANDEX_MAPS_API_KEY"]

class ConfigError(Exception):
    pass

@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    anthropic_api_key: str
    yandex_maps_api_key: str

def load_config(env: dict) -> Config:
    missing = [name for name in REQUIRED_VARS if not env.get(name)]
    if missing:
        raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")
    return Config(
        telegram_bot_token=env["TELEGRAM_BOT_TOKEN"],
        anthropic_api_key=env["ANTHROPIC_API_KEY"],
        yandex_maps_api_key=env["YANDEX_MAPS_API_KEY"],
    )
```

Create a `pyproject.toml` so `alcana_bot` is importable during tests:
```toml
[project]
name = "alcana-bot"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example .gitignore pyproject.toml src/alcana_bot/__init__.py src/alcana_bot/config.py tests/test_config.py
git commit -m "feat: add project scaffolding and env config loader"
```

---

## Task 2: Price data loader

**Files:**
- Create: `src/alcana_bot/price_data.py`
- Test: `tests/test_price_data.py`

**Interfaces:**
- Consumes: `data/price_list.json` (already exists at repo root).
- Produces: `Category` dataclass (fields: `id`, `pricing_type`, `unit`, `requires_dimensions`, plus optional `price`, `options`, `height_prices`, `brackets`, `extraction_mode`), `PriceList` dataclass (`categories: dict[str, Category]`, `bundle_defaults: dict`, `workshop_origin: dict`), function `load_price_list(path: str) -> PriceList`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_price_data.py
import json
import pytest
from alcana_bot.price_data import load_price_list, PriceDataError

REAL_PRICE_LIST_PATH = "data/price_list.json"

def test_load_real_price_list():
    price_list = load_price_list(REAL_PRICE_LIST_PATH)
    assert "banner_300gr" in price_list.categories
    banner = price_list.categories["banner_300gr"]
    assert banner.pricing_type == "per_sqm"
    assert banner.price == 30000

    letters = price_list.categories["letters_acrylic_led"]
    assert letters.pricing_type == "per_letter_by_height"
    assert letters.height_prices == [
        {"height_cm": 60, "price": 8500},
        {"height_cm": 80, "price": 9500},
        {"height_cm": 100, "price": 13000},
        {"height_cm": 120, "price": 16000},
    ]

    assert price_list.workshop_origin["latitude"] == 41.291234
    assert "design_service" in price_list.bundle_defaults["always_include"]

def test_load_price_list_missing_pricing_type_field(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({
        "categories": [{"id": "x", "unit": "pc"}],
        "bundle_defaults": {"always_include": []},
        "workshop_origin": {"latitude": 0, "longitude": 0},
    }))
    with pytest.raises(PriceDataError, match="pricing_type"):
        load_price_list(str(bad_file))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_price_data.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/price_data.py
import json
from dataclasses import dataclass, field

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_price_data.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/price_data.py tests/test_price_data.py
git commit -m "feat: add price_list.json loader with validation"
```

---

## Task 3: Pricing computation engine

**Files:**
- Create: `src/alcana_bot/pricing.py`
- Test: `tests/test_pricing.py`

**Interfaces:**
- Consumes: `Category` from `price_data.py`.
- Produces: `LineItem` dataclass (`label: str`, `detail: str`, `unit_price: int`, `quantity: float`, `total: int`); functions `price_fixed`, `price_fixed_options`, `price_per_sqm`, `price_per_sqm_options`, `price_per_letter_by_height`, `price_per_unit`, `resolve_distance_bracket` — every function returns a `LineItem` or raises `PricingError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pricing.py
import pytest
from alcana_bot.price_data import load_price_list
from alcana_bot.pricing import (
    price_fixed, price_fixed_options, price_per_sqm, price_per_sqm_options,
    price_per_letter_by_height, price_per_unit, resolve_distance_bracket,
    PricingError,
)

PRICE_LIST = load_price_list("data/price_list.json")

def test_price_fixed():
    category = PRICE_LIST.categories["lightbox_rr_60b"]
    item = price_fixed(category)
    assert item.total == 1150000
    assert item.quantity == 1

def test_price_fixed_options():
    category = PRICE_LIST.categories["standee"]
    item = price_fixed_options(category, option_index=2)
    assert item.total == 1100000
    assert "Алюкабонд" in item.detail

def test_price_per_sqm():
    category = PRICE_LIST.categories["banner_300gr"]
    item = price_per_sqm(category, width_cm=200, height_cm=150)
    assert item.total == 90000  # 3.0 sqm * 30000

def test_price_per_sqm_options():
    category = PRICE_LIST.categories["acrylic_lightbox"]
    item = price_per_sqm_options(category, option_index=1, width_cm=100, height_cm=100)
    assert item.total == 2800000  # 1.0 sqm * 2,800,000 (double-sided)

def test_price_per_letter_by_height_exact_match():
    category = PRICE_LIST.categories["letters_acrylic_led"]
    item = price_per_letter_by_height(category, letter_count=5, height_cm=80)
    assert item.total == 47500  # 5 * 9,500

def test_price_per_letter_by_height_rounds_up_to_next_bracket():
    category = PRICE_LIST.categories["letters_acrylic_led"]
    item = price_per_letter_by_height(category, letter_count=2, height_cm=90)
    assert item.unit_price == 13000  # rounds up 90 -> 100cm bracket
    assert item.total == 26000

def test_price_per_letter_by_height_above_max_raises():
    category = PRICE_LIST.categories["letters_acrylic_led"]
    with pytest.raises(PricingError, match="no price bracket"):
        price_per_letter_by_height(category, letter_count=1, height_cm=150)

def test_price_per_unit_hour():
    category = PRICE_LIST.categories["design_service"]
    item = price_per_unit(category, quantity=2)
    assert item.total == 300000  # 2 hours * 150,000

def test_resolve_distance_bracket():
    category = PRICE_LIST.categories["install_travel_fee"]
    item = resolve_distance_bracket(category, distance_km=25)
    assert item.total == 200000

def test_resolve_distance_bracket_beyond_max_raises():
    category = PRICE_LIST.categories["install_travel_fee"]
    with pytest.raises(PricingError, match="no distance bracket"):
        resolve_distance_bracket(category, distance_km=150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pricing.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/pricing.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pricing.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/pricing.py tests/test_pricing.py
git commit -m "feat: add pricing computation engine for all pricing_types"
```

---

## Task 4: Distance calculation (geocoding + haversine estimate)

**Files:**
- Create: `src/alcana_bot/distance.py`
- Test: `tests/test_distance.py`

**Interfaces:**
- Consumes: `requests` for HTTP calls to Yandex Geocoder; `workshop_origin` dict from `PriceList`.
- Produces: `geocode_address(address: str, api_key: str) -> tuple[float, float]`, `haversine_km(origin: tuple, destination: tuple) -> float`, `estimate_driving_km(origin: tuple, destination: tuple, road_factor: float = 1.3) -> float`, `DistanceError`.

**Design note:** v1 uses geocoding (free-tier Yandex Geocoder) plus a straight-line distance x 1.3 road-factor approximation instead of Yandex's paid/quota-limited routing API. This keeps the feature free to run; swap `estimate_driving_km` for a real routing call later if precision becomes an issue — nothing else in the codebase needs to change since callers only see `estimate_driving_km`'s return value.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_distance.py
import pytest
from alcana_bot.distance import geocode_address, haversine_km, estimate_driving_km, DistanceError

SAMPLE_GEOCODE_RESPONSE = {
    "response": {
        "GeoObjectCollection": {
            "featureMember": [
                {"GeoObject": {"Point": {"pos": "69.240562 41.311081"}}}
            ]
        }
    }
}

def test_geocode_address_parses_lat_lon(mocker):
    mock_get = mocker.patch("alcana_bot.distance.requests.get")
    mock_get.return_value.json.return_value = SAMPLE_GEOCODE_RESPONSE
    mock_get.return_value.raise_for_status = lambda: None

    lat, lon = geocode_address("Chilonzor, Tashkent", api_key="fake-key")

    assert lat == pytest.approx(41.311081)
    assert lon == pytest.approx(69.240562)

def test_geocode_address_no_results_raises(mocker):
    mock_get = mocker.patch("alcana_bot.distance.requests.get")
    mock_get.return_value.json.return_value = {"response": {"GeoObjectCollection": {"featureMember": []}}}
    mock_get.return_value.raise_for_status = lambda: None

    with pytest.raises(DistanceError, match="no results"):
        geocode_address("nonexistent place asdkjashd", api_key="fake-key")

def test_haversine_km_known_distance():
    # Workshop origin to a point ~2km away (rough check, not exact)
    workshop = (41.291234, 69.196435)
    nearby = (41.30, 69.20)
    km = haversine_km(workshop, nearby)
    assert 0.5 < km < 3.0

def test_estimate_driving_km_applies_road_factor():
    origin = (41.291234, 69.196435)
    destination = (41.30, 69.20)
    straight = haversine_km(origin, destination)
    driving = estimate_driving_km(origin, destination)
    assert driving == pytest.approx(straight * 1.3, rel=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_distance.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/distance.py
import math
import requests

class DistanceError(Exception):
    pass

GEOCODE_URL = "https://geocode-maps.yandex.ru/1.x/"

def geocode_address(address: str, api_key: str) -> tuple[float, float]:
    response = requests.get(GEOCODE_URL, params={
        "apikey": api_key,
        "geocode": address,
        "format": "json",
        "results": 1,
    }, timeout=10)
    response.raise_for_status()
    data = response.json()
    members = data["response"]["GeoObjectCollection"]["featureMember"]
    if not members:
        raise DistanceError(f"Geocoding '{address}' returned no results")
    pos = members[0]["GeoObject"]["Point"]["pos"]  # "lon lat"
    lon_str, lat_str = pos.split(" ")
    return float(lat_str), float(lon_str)

def haversine_km(origin: tuple, destination: tuple) -> float:
    lat1, lon1 = origin
    lat2, lon2 = destination
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def estimate_driving_km(origin: tuple, destination: tuple, road_factor: float = 1.3) -> float:
    return haversine_km(origin, destination) * road_factor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_distance.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/distance.py tests/test_distance.py
git commit -m "feat: add address geocoding and driving-distance estimate"
```

---

## Task 5: CDR page-size extraction via LibreOffice

**Files:**
- Create: `src/alcana_bot/cdr.py`
- Test: `tests/test_cdr.py`

**Interfaces:**
- Produces: `parse_svg_page_size(svg_content: str) -> tuple[float, float]` (pure, unit-tested), `convert_cdr_to_svg(cdr_path: str, soffice_path: str, output_dir: str) -> str` (shells out, not automated-tested — see note), `extract_cdr_dimensions(cdr_path: str, soffice_path: str) -> tuple[float, float]` (combines both), `CdrExtractionError`.

**Design note:** `convert_cdr_to_svg` requires LibreOffice installed on the deployment machine (`soffice` binary) — this is a new prerequisite beyond what's in the spec, needed because CorelDraw itself isn't available there. There's no `.cdr` test fixture available, so `convert_cdr_to_svg` is verified manually during deployment (per the spec's testing approach); the pure SVG-parsing logic that actually computes the dimensions is fully unit tested here in isolation.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cdr.py
import pytest
from alcana_bot.cdr import parse_svg_page_size, CdrExtractionError

def test_parse_svg_page_size_mm():
    svg = '<svg width="680mm" height="80mm" xmlns="http://www.w3.org/2000/svg"></svg>'
    width_cm, height_cm = parse_svg_page_size(svg)
    assert width_cm == pytest.approx(68.0)
    assert height_cm == pytest.approx(8.0)

def test_parse_svg_page_size_px_assumes_96dpi():
    # 96px = 1 inch = 2.54cm
    svg = '<svg width="96px" height="192px" xmlns="http://www.w3.org/2000/svg"></svg>'
    width_cm, height_cm = parse_svg_page_size(svg)
    assert width_cm == pytest.approx(2.54)
    assert height_cm == pytest.approx(5.08)

def test_parse_svg_page_size_pt():
    # 72pt = 1 inch = 2.54cm
    svg = '<svg width="72pt" height="144pt" xmlns="http://www.w3.org/2000/svg"></svg>'
    width_cm, height_cm = parse_svg_page_size(svg)
    assert width_cm == pytest.approx(2.54)
    assert height_cm == pytest.approx(5.08)

def test_parse_svg_page_size_missing_dimensions_raises():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    with pytest.raises(CdrExtractionError, match="width/height"):
        parse_svg_page_size(svg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cdr.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/cdr.py
import os
import re
import subprocess
import defusedxml.ElementTree as ET

class CdrExtractionError(Exception):
    pass

_UNIT_TO_CM = {
    "mm": 0.1,
    "cm": 1.0,
    "in": 2.54,
    "pt": 2.54 / 72,
    "px": 2.54 / 96,  # assume 96dpi, matches LibreOffice's SVG export default
}

def _to_cm(value_str: str) -> float:
    match = re.match(r"^([\d.]+)([a-z%]*)$", value_str.strip())
    if not match:
        raise CdrExtractionError(f"Could not parse SVG dimension: '{value_str}'")
    number, unit = match.groups()
    unit = unit or "px"
    if unit not in _UNIT_TO_CM:
        raise CdrExtractionError(f"Unsupported SVG unit: '{unit}'")
    return float(number) * _UNIT_TO_CM[unit]

def parse_svg_page_size(svg_content: str) -> tuple[float, float]:
    root = ET.fromstring(svg_content)
    width = root.get("width")
    height = root.get("height")
    if not width or not height:
        raise CdrExtractionError("SVG root element is missing width/height attributes")
    return _to_cm(width), _to_cm(height)

def convert_cdr_to_svg(cdr_path: str, soffice_path: str, output_dir: str) -> str:
    result = subprocess.run(
        [soffice_path, "--headless", "--convert-to", "svg", "--outdir", output_dir, cdr_path],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise CdrExtractionError(f"soffice conversion failed: {result.stderr}")
    base_name = os.path.splitext(os.path.basename(cdr_path))[0]
    svg_path = os.path.join(output_dir, f"{base_name}.svg")
    if not os.path.exists(svg_path):
        raise CdrExtractionError(f"Expected output SVG not found: {svg_path}")
    return svg_path

def extract_cdr_dimensions(cdr_path: str, soffice_path: str) -> tuple[float, float]:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        svg_path = convert_cdr_to_svg(cdr_path, soffice_path, tmp_dir)
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_content = f.read()
        return parse_svg_page_size(svg_content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cdr.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/cdr.py tests/test_cdr.py
git commit -m "feat: add CDR page-size extraction via LibreOffice SVG conversion"
```

---

## Task 6: Vision-based dimension and letter-count extraction

**Files:**
- Create: `src/alcana_bot/vision.py`
- Test: `tests/test_vision.py`

**Interfaces:**
- Consumes: an injected Anthropic-client-like object exposing `.messages.create(...)` (the real client comes from `anthropic.Anthropic(api_key=...)` at call sites — never constructed inside these functions, so tests inject a fake).
- Produces: `extract_dimensions_from_image(client, image_bytes: bytes, media_type: str) -> dict` (`{"width_cm": float, "height_cm": float, "confidence": float}`), `extract_letter_spec_from_image(client, image_bytes: bytes, media_type: str) -> dict` (`{"letter_count": int, "height_cm": float, "confidence": float}`), `ExtractionError`. Confidence below `0.6` raises `ExtractionError` so callers fall back to asking staff.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vision.py
import json
import pytest
from alcana_bot.vision import extract_dimensions_from_image, extract_letter_spec_from_image, ExtractionError

class FakeTextBlock:
    def __init__(self, text):
        self.text = text

class FakeResponse:
    def __init__(self, text):
        self.content = [FakeTextBlock(text)]

class FakeMessages:
    def __init__(self, response_text):
        self._response_text = response_text
    def create(self, **kwargs):
        return FakeResponse(self._response_text)

class FakeClient:
    def __init__(self, response_text):
        self.messages = FakeMessages(response_text)

def test_extract_dimensions_from_image_parses_valid_json():
    client = FakeClient(json.dumps({"width_cm": 680, "height_cm": 80, "confidence": 0.95}))
    result = extract_dimensions_from_image(client, image_bytes=b"fake", media_type="image/png")
    assert result == {"width_cm": 680, "height_cm": 80, "confidence": 0.95}

def test_extract_dimensions_from_image_low_confidence_raises():
    client = FakeClient(json.dumps({"width_cm": 680, "height_cm": 80, "confidence": 0.3}))
    with pytest.raises(ExtractionError, match="confidence"):
        extract_dimensions_from_image(client, image_bytes=b"fake", media_type="image/png")

def test_extract_dimensions_from_image_malformed_response_raises():
    client = FakeClient("not json at all")
    with pytest.raises(ExtractionError, match="parse"):
        extract_dimensions_from_image(client, image_bytes=b"fake", media_type="image/png")

def test_extract_letter_spec_from_image_parses_valid_json():
    client = FakeClient(json.dumps({"letter_count": 6, "height_cm": 80, "confidence": 0.9}))
    result = extract_letter_spec_from_image(client, image_bytes=b"fake", media_type="image/png")
    assert result == {"letter_count": 6, "height_cm": 80, "confidence": 0.9}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vision.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/vision.py
import base64
import json

class ExtractionError(Exception):
    pass

MODEL = "claude-haiku-4-5"
CONFIDENCE_THRESHOLD = 0.6

_DIMENSIONS_PROMPT = (
    "This image shows an advertising design with printed dimension labels "
    "(e.g. numbers with 'см' or 'cm'). Read the overall width and height in "
    "centimeters. Reply with ONLY a JSON object, no other text, in this exact "
    'shape: {"width_cm": <number>, "height_cm": <number>, "confidence": <0-1>}. '
    "Set confidence low (below 0.5) if the labels are unclear or ambiguous."
)

_LETTERS_PROMPT = (
    "This image shows a design for volumetric/3D letters (dimensional signage "
    "letters). Count exactly how many individual letters/characters need to be "
    "fabricated, and read or infer the intended letter height in centimeters "
    "(one of 60, 80, 100, or 120cm, or another explicit value). Reply with ONLY "
    'a JSON object, no other text: {"letter_count": <integer>, "height_cm": '
    '<number>, "confidence": <0-1>}. Set confidence low if unclear.'
)

def _call_vision(client, image_bytes: bytes, media_type: str, prompt: str, required_keys: list[str]) -> dict:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": encoded}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    text = response.content[0].text
    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Could not parse model response as JSON: {text!r}") from e

    for key in required_keys:
        if key not in result:
            raise ExtractionError(f"Model response missing required key '{key}': {result}")

    if result["confidence"] < CONFIDENCE_THRESHOLD:
        raise ExtractionError(f"Extraction confidence too low ({result['confidence']}); fall back to manual entry")

    return result

def extract_dimensions_from_image(client, image_bytes: bytes, media_type: str) -> dict:
    return _call_vision(client, image_bytes, media_type, _DIMENSIONS_PROMPT, ["width_cm", "height_cm", "confidence"])

def extract_letter_spec_from_image(client, image_bytes: bytes, media_type: str) -> dict:
    return _call_vision(client, image_bytes, media_type, _LETTERS_PROMPT, ["letter_count", "height_cm", "confidence"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_vision.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/vision.py tests/test_vision.py
git commit -m "feat: add Claude Haiku vision extraction for dimensions and letter counts"
```

---

## Task 7: i18n string tables

**Files:**
- Create: `src/alcana_bot/i18n.py`
- Test: `tests/test_i18n.py`

**Interfaces:**
- Produces: `t(key: str, lang: str, **kwargs) -> str`, `I18nError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_i18n.py
import pytest
from alcana_bot.i18n import t, I18nError

def test_t_returns_uz_and_ru():
    assert t("welcome", "uz") != t("welcome", "ru")
    assert isinstance(t("welcome", "uz"), str)

def test_t_formats_placeholders():
    message = t("quote_total", "ru", total="150 000")
    assert "150 000" in message

def test_t_unknown_key_raises():
    with pytest.raises(I18nError, match="unknown"):
        t("this_key_does_not_exist", "uz")

def test_t_unknown_lang_raises():
    with pytest.raises(I18nError, match="language"):
        t("welcome", "fr")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_i18n.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/i18n.py
class I18nError(Exception):
    pass

TRANSLATIONS = {
    "welcome": {
        "uz": "Salom! Buyurtma narxini hisoblash uchun rasm yoki .cdr fayl yuboring.",
        "ru": "Здравствуйте! Отправьте фото или .cdr файл, чтобы рассчитать цену заказа.",
    },
    "choose_language": {
        "uz": "Tilni tanlang: /til uz yoki /til ru",
        "ru": "Выберите язык: /язык ru или /язык uz",
    },
    "language_set": {
        "uz": "Til o'zbek tiliga o'rnatildi.",
        "ru": "Язык установлен на русский.",
    },
    "choose_category": {
        "uz": "Mahsulot turini tanlang:",
        "ru": "Выберите тип товара:",
    },
    "choose_option": {
        "uz": "Variantni tanlang:",
        "ru": "Выберите вариант:",
    },
    "enter_dimensions": {
        "uz": "O'lchamlarni avtomatik aniqlab bo'lmadi. Kenglik va balandlikni sm da kiriting (masalan: 200x150):",
        "ru": "Не удалось определить размеры автоматически. Введите ширину и высоту в см (например: 200x150):",
    },
    "enter_quantity": {
        "uz": "Miqdorni kiriting (masalan: soat, metr yoki daqiqa soni):",
        "ru": "Введите количество (например: часы, метры или минуты):",
    },
    "enter_letter_spec": {
        "uz": "Harflar sonini va balandligini (sm) avtomatik aniqlab bo'lmadi. Iltimos, sonini va balandligini kiriting (masalan: 6, 80):",
        "ru": "Не удалось определить количество и высоту букв автоматически. Введите количество и высоту в см (например: 6, 80):",
    },
    "ask_address_or_location": {
        "uz": "Mijoz manzilini yozing yoki Telegram orqali joylashuvni yuboring:",
        "ru": "Напишите адрес клиента или отправьте геолокацию через Telegram:",
    },
    "ask_bundle_confirmation": {
        "uz": "Taklif: mahsulot + dizayn xizmati + montaj/yo'l harajati. Barchasini qoldiraymi?",
        "ru": "Предложение: товар + услуга дизайна + монтаж/выезд. Оставить всё как есть?",
    },
    "quote_line_item": {
        "uz": "{label}: {detail} — {total} so'm",
        "ru": "{label}: {detail} — {total} сум",
    },
    "quote_total": {
        "uz": "Jami: {total} so'm",
        "ru": "Итого: {total} сум",
    },
    "extraction_failed_fallback": {
        "uz": "Avtomatik aniqlash muvaffaqiyatsiz tugadi, iltimos qo'lda kiriting.",
        "ru": "Автоматическое распознавание не удалось, пожалуйста, введите вручную.",
    },
}

def t(key: str, lang: str, **kwargs) -> str:
    if key not in TRANSLATIONS:
        raise I18nError(f"unknown translation key: '{key}'")
    entry = TRANSLATIONS[key]
    if lang not in entry:
        raise I18nError(f"unknown language '{lang}' for key '{key}'")
    return entry[lang].format(**kwargs) if kwargs else entry[lang]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_i18n.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/i18n.py tests/test_i18n.py
git commit -m "feat: add UZ/RU translation tables"
```

---

## Task 8: Persistent per-user language preference store

**Files:**
- Create: `src/alcana_bot/lang_store.py`
- Test: `tests/test_lang_store.py`

**Interfaces:**
- Produces: `LangStore` class with `__init__(self, file_path: str)`, `get_language(self, user_id: int, default: str = "uz") -> str`, `set_language(self, user_id: int, lang: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lang_store.py
from alcana_bot.lang_store import LangStore

def test_get_language_defaults_when_unset(tmp_path):
    store = LangStore(str(tmp_path / "user_lang.json"))
    assert store.get_language(12345) == "uz"

def test_set_then_get_language_roundtrip(tmp_path):
    store = LangStore(str(tmp_path / "user_lang.json"))
    store.set_language(12345, "ru")
    assert store.get_language(12345) == "ru"

def test_language_persists_across_new_instance(tmp_path):
    file_path = str(tmp_path / "user_lang.json")
    store1 = LangStore(file_path)
    store1.set_language(999, "ru")

    store2 = LangStore(file_path)
    assert store2.get_language(999) == "ru"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_lang_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/lang_store.py
import json
import os

class LangStore:
    def __init__(self, file_path: str):
        self._file_path = file_path
        if not os.path.exists(self._file_path):
            self._write({})

    def _read(self) -> dict:
        with open(self._file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        tmp_path = self._file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp_path, self._file_path)

    def get_language(self, user_id: int, default: str = "uz") -> str:
        data = self._read()
        return data.get(str(user_id), default)

    def set_language(self, user_id: int, lang: str) -> None:
        data = self._read()
        data[str(user_id)] = lang
        self._write(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_lang_store.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/lang_store.py tests/test_lang_store.py
git commit -m "feat: add persistent per-user language preference store"
```

---

## Task 9: Bundle assembly logic

**Files:**
- Create: `src/alcana_bot/bundle.py`
- Test: `tests/test_bundle.py`

**Interfaces:**
- Consumes: `LineItem` from `pricing.py`.
- Produces: `assemble_bundle(main_item: LineItem, design_item: LineItem | None, travel_item: LineItem | None) -> list[LineItem]`, `bundle_total(items: list[LineItem]) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bundle.py
from alcana_bot.pricing import LineItem
from alcana_bot.bundle import assemble_bundle, bundle_total

def make_item(total):
    return LineItem(label="x", detail="", unit_price=total, quantity=1, total=total)

def test_assemble_bundle_includes_all_when_provided():
    main = make_item(100000)
    design = make_item(150000)
    travel = make_item(200000)
    items = assemble_bundle(main, design, travel)
    assert items == [main, design, travel]

def test_assemble_bundle_omits_none_lines():
    main = make_item(100000)
    items = assemble_bundle(main, design_item=None, travel_item=None)
    assert items == [main]

def test_bundle_total_sums_all_lines():
    items = [make_item(100000), make_item(150000), make_item(200000)]
    assert bundle_total(items) == 450000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bundle.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/bundle.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bundle.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/bundle.py tests/test_bundle.py
git commit -m "feat: add bundle assembly and totals"
```

---

## Task 10: Bot presentation helpers (keyboard building, message formatting)

**Files:**
- Create: `src/alcana_bot/presentation.py`
- Test: `tests/test_presentation.py`

**Interfaces:**
- Consumes: `PriceList` from `price_data.py`, `LineItem` from `pricing.py`, `t()` from `i18n.py`.
- Produces: `build_category_choices(price_list: PriceList) -> list[tuple[str, str]]` (returns `(category_id, display_name)` pairs, excluding `measurement_fee` and `install_travel_fee` which are add-ons, not directly selectable products), `format_quote(items: list[LineItem], lang: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_presentation.py
from alcana_bot.price_data import load_price_list
from alcana_bot.pricing import LineItem
from alcana_bot.presentation import build_category_choices, format_quote

PRICE_LIST = load_price_list("data/price_list.json")

def test_build_category_choices_excludes_fee_addons():
    choices = build_category_choices(PRICE_LIST)
    ids = [c[0] for c in choices]
    assert "measurement_fee" not in ids
    assert "install_travel_fee" not in ids
    assert "banner_300gr" in ids

def test_format_quote_includes_all_lines_and_total():
    items = [
        LineItem(label="banner_300gr", detail="200x150 см", unit_price=30000, quantity=3.0, total=90000),
        LineItem(label="design_service", detail="1 hour", unit_price=150000, quantity=1, total=150000),
    ]
    message = format_quote(items, "ru")
    assert "90000" in message.replace(" ", "")
    assert "150000" in message.replace(" ", "")
    assert "240000" in message.replace(" ", "")  # total
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_presentation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/alcana_bot/presentation.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_presentation.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/presentation.py tests/test_presentation.py
git commit -m "feat: add category menu and quote formatting helpers"
```

---

## Task 11: Bot wiring (handlers and conversation flow)

**Files:**
- Create: `src/alcana_bot/bot.py`

**Interfaces:**
- Consumes: every module above, plus `python-telegram-bot`'s `Application`, `ConversationHandler`, `CallbackQueryHandler`, `MessageHandler`, `filters`.
- Produces: `build_application(config: Config, price_list: PriceList, lang_store: LangStore, anthropic_client, soffice_path: str) -> Application`.

**Note on extraction ordering (resolving a spec ambiguity):** the spec describes dimension extraction as step 2 and category selection as step 3, but letter-counting extraction needs to know the category first. This task resolves it as: run generic dimension extraction immediately on file receipt (works for any `per_sqm*` category); if the staff member then picks a `per_letter_by_height` category, run a second, letter-specific vision pass on the same stored image bytes.

**Note on testability:** this task is PTB glue code depending on live Telegram/Anthropic/Yandex calls, so it's verified via the manual end-to-end tests in Task 14, not automated tests — but every decision it calls into (`pricing`, `distance`, `cdr`, `vision`, `bundle`, `presentation`) is already unit tested in its own module, so this file's job is purely to route data between them correctly.

**Conversation state and data flow used below:**

```
States: AWAITING_FILE -> AWAITING_CATEGORY -> [AWAITING_OPTION] -> [AWAITING_TEXT_INPUT] -> AWAITING_BUNDLE_CHOICE -> AWAITING_FILE (next order)

context.user_data keys:
  image_bytes, media_type   raw file bytes for re-use across vision calls (photo orders only)
  cdr_dimensions            (width_cm, height_cm) tuple if a .cdr was parsed successfully
  extracted_dimensions      {"width_cm", "height_cm"} from the photo vision pass, if confident
  category_id               selected category id (str)
  option_index              selected sub-option index, if the category has options
  pending_text_purpose      one of "dimensions" | "letters" | "quantity" | "address" -- tells
                             the single text handler what to do with the next text message
  main_item                 the computed LineItem for the primary product
  design_item, travel_item  LineItem or None, filled in during the bundle step
```

- [ ] **Step 1: Write the full bot module**

```python
# src/alcana_bot/bot.py
import logging
import os
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
)

from alcana_bot.config import Config
from alcana_bot.price_data import PriceList
from alcana_bot.lang_store import LangStore
from alcana_bot.presentation import build_category_choices, format_quote
from alcana_bot.pricing import (
    price_fixed, price_fixed_options, price_per_sqm, price_per_sqm_options,
    price_per_letter_by_height, price_per_unit, resolve_distance_bracket, PricingError,
)
from alcana_bot.bundle import assemble_bundle
from alcana_bot.vision import extract_dimensions_from_image, extract_letter_spec_from_image, ExtractionError
from alcana_bot.cdr import extract_cdr_dimensions, CdrExtractionError
from alcana_bot.distance import geocode_address, estimate_driving_km, DistanceError
from alcana_bot.i18n import t

logger = logging.getLogger(__name__)

AWAITING_FILE, AWAITING_CATEGORY, AWAITING_OPTION, AWAITING_TEXT_INPUT, AWAITING_BUNDLE_CHOICE = range(5)


def _lang(context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore, user_id: int) -> str:
    return lang_store.get_language(user_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    await update.message.reply_text(t("welcome", lang))
    return AWAITING_FILE


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore, lang: str) -> None:
    lang_store.set_language(update.effective_user.id, lang)
    await update.message.reply_text(t("language_set", lang))


async def _show_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang: str) -> int:
    choices = build_category_choices(price_list)
    keyboard = [[InlineKeyboardButton(name, callback_data=f"cat:{category_id}")] for category_id, name in choices]
    await update.effective_chat.send_message(t("choose_category", lang), reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_CATEGORY


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, anthropic_client) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = bytes(await photo_file.download_as_bytearray())
    context.user_data["image_bytes"] = image_bytes
    context.user_data["media_type"] = "image/jpeg"

    try:
        result = extract_dimensions_from_image(anthropic_client, image_bytes, "image/jpeg")
        context.user_data["extracted_dimensions"] = {"width_cm": result["width_cm"], "height_cm": result["height_cm"]}
    except ExtractionError as e:
        logger.info("Photo dimension extraction failed, will fall back to manual entry: %s", e)
        context.user_data["extracted_dimensions"] = None

    return await _show_category_menu(update, context, price_list, lang)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, soffice_path: str) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    document = update.message.document
    context.user_data["extracted_dimensions"] = None
    context.user_data["cdr_dimensions"] = None

    if document.file_name.lower().endswith(".cdr"):
        doc_file = await document.get_file()
        with tempfile.TemporaryDirectory() as tmp_dir:
            cdr_path = os.path.join(tmp_dir, document.file_name)
            await doc_file.download_to_drive(cdr_path)
            try:
                width_cm, height_cm = extract_cdr_dimensions(cdr_path, soffice_path)
                context.user_data["cdr_dimensions"] = (width_cm, height_cm)
            except CdrExtractionError as e:
                logger.info("CDR dimension extraction failed, will fall back to manual entry: %s", e)

    return await _show_category_menu(update, context, price_list, lang)


async def handle_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, anthropic_client) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    category_id = query.data.split(":", 1)[1]
    context.user_data["category_id"] = category_id
    category = price_list.categories[category_id]

    if category.pricing_type in ("fixed_options", "per_sqm_options"):
        keyboard = [[InlineKeyboardButton(opt.get("label", str(i)), callback_data=f"opt:{i}")] for i, opt in enumerate(category.options)]
        await query.edit_message_text(t("choose_option", lang))
        await query.message.reply_text(t("choose_option", lang), reply_markup=InlineKeyboardMarkup(keyboard))
        return AWAITING_OPTION

    if category.pricing_type == "per_letter_by_height":
        image_bytes = context.user_data.get("image_bytes")
        if image_bytes:
            try:
                spec = extract_letter_spec_from_image(anthropic_client, image_bytes, context.user_data["media_type"])
                item = price_per_letter_by_height(category, letter_count=spec["letter_count"], height_cm=spec["height_cm"])
                return await _finish_main_item(update, context, price_list, lang_store, item)
            except (ExtractionError, PricingError) as e:
                logger.info("Letter extraction/pricing failed, falling back to manual entry: %s", e)
        context.user_data["pending_text_purpose"] = "letters"
        await query.message.reply_text(t("enter_letter_spec", lang))
        return AWAITING_TEXT_INPUT

    if category.pricing_type == "per_sqm":
        dims = context.user_data.get("extracted_dimensions") or context.user_data.get("cdr_dimensions")
        if dims:
            width_cm, height_cm = (dims["width_cm"], dims["height_cm"]) if isinstance(dims, dict) else dims
            item = price_per_sqm(category, width_cm, height_cm)
            return await _finish_main_item(update, context, price_list, lang_store, item)
        context.user_data["pending_text_purpose"] = "dimensions"
        await query.message.reply_text(t("enter_dimensions", lang))
        return AWAITING_TEXT_INPUT

    if category.pricing_type in ("per_hour", "per_minute", "per_meter"):
        context.user_data["pending_text_purpose"] = "quantity"
        await query.message.reply_text(t("enter_quantity", lang))
        return AWAITING_TEXT_INPUT

    # fixed
    item = price_fixed(category)
    return await _finish_main_item(update, context, price_list, lang_store, item)


async def handle_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    option_index = int(query.data.split(":", 1)[1])
    context.user_data["option_index"] = option_index
    category = price_list.categories[context.user_data["category_id"]]

    if category.pricing_type == "fixed_options":
        item = price_fixed_options(category, option_index)
        return await _finish_main_item(update, context, price_list, lang_store, item)

    # per_sqm_options: still needs dimensions
    dims = context.user_data.get("extracted_dimensions") or context.user_data.get("cdr_dimensions")
    if dims:
        width_cm, height_cm = (dims["width_cm"], dims["height_cm"]) if isinstance(dims, dict) else dims
        item = price_per_sqm_options(category, option_index, width_cm, height_cm)
        return await _finish_main_item(update, context, price_list, lang_store, item)

    context.user_data["pending_text_purpose"] = "dimensions"
    await query.message.reply_text(t("enter_dimensions", lang))
    return AWAITING_TEXT_INPUT


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, config: Config) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    purpose = context.user_data.get("pending_text_purpose")
    category = price_list.categories[context.user_data["category_id"]]
    text = update.message.text.strip()

    try:
        if purpose == "dimensions":
            width_str, height_str = text.lower().replace(" ", "").split("x")
            option_index = context.user_data.get("option_index")
            if option_index is not None:
                item = price_per_sqm_options(category, option_index, float(width_str), float(height_str))
            else:
                item = price_per_sqm(category, float(width_str), float(height_str))
            return await _finish_main_item(update, context, price_list, lang_store, item)

        if purpose == "letters":
            count_str, height_str = [p.strip() for p in text.split(",")]
            item = price_per_letter_by_height(category, letter_count=int(count_str), height_cm=float(height_str))
            return await _finish_main_item(update, context, price_list, lang_store, item)

        if purpose == "quantity":
            item = price_per_unit(category, quantity=float(text))
            return await _finish_main_item(update, context, price_list, lang_store, item)

        if purpose == "address":
            lat, lon = geocode_address(text, config.yandex_maps_api_key)
            return await _finish_distance_step(update, context, price_list, lang_store, (lat, lon))
    except (ValueError, PricingError, DistanceError) as e:
        logger.info("Could not parse/compute from text input (purpose=%s): %s", purpose, e)
        await update.message.reply_text(t("extraction_failed_fallback", lang))
        return AWAITING_TEXT_INPUT


async def handle_location_shared(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    location = update.message.location
    return await _finish_distance_step(update, context, price_list, lang_store, (location.latitude, location.longitude))


async def _finish_main_item(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, item) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    context.user_data["main_item"] = item
    keyboard = [[InlineKeyboardButton("Ha / Да", callback_data="bundle:yes"), InlineKeyboardButton("Yo'q / Нет", callback_data="bundle:no")]]
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(t("ask_bundle_confirmation", lang), reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_BUNDLE_CHOICE


async def handle_bundle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    include_bundle = query.data.split(":", 1)[1] == "yes"

    if not include_bundle:
        item = context.user_data["main_item"]
        await query.message.reply_text(format_quote([item], lang))
        return AWAITING_FILE

    design_category = price_list.categories["design_service"]
    context.user_data["design_item"] = price_per_unit(design_category, quantity=1)
    context.user_data["pending_text_purpose"] = "address"
    await query.message.reply_text(t("ask_address_or_location", lang))
    return AWAITING_TEXT_INPUT


async def _finish_distance_step(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, destination: tuple) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    origin = (price_list.workshop_origin["latitude"], price_list.workshop_origin["longitude"])
    distance_km = estimate_driving_km(origin, destination)
    travel_category = price_list.categories["install_travel_fee"]

    try:
        travel_item = resolve_distance_bracket(travel_category, distance_km)
    except PricingError as e:
        logger.info("Distance bracket resolution failed: %s", e)
        travel_item = None

    items = assemble_bundle(context.user_data["main_item"], context.user_data.get("design_item"), travel_item)
    await update.effective_chat.send_message(format_quote(items, lang))
    return AWAITING_FILE


def build_application(config: Config, price_list: PriceList, lang_store: LangStore, anthropic_client, soffice_path: str) -> Application:
    application = Application.builder().token(config.telegram_bot_token).build()

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", lambda u, c: start(u, c, lang_store))],
        states={
            AWAITING_FILE: [
                MessageHandler(filters.PHOTO, lambda u, c: handle_photo(u, c, price_list, lang_store, anthropic_client)),
                MessageHandler(filters.Document.ALL, lambda u, c: handle_document(u, c, price_list, lang_store, soffice_path)),
            ],
            AWAITING_CATEGORY: [
                CallbackQueryHandler(lambda u, c: handle_category_selected(u, c, price_list, lang_store, anthropic_client), pattern=r"^cat:"),
            ],
            AWAITING_OPTION: [
                CallbackQueryHandler(lambda u, c: handle_option_selected(u, c, price_list, lang_store), pattern=r"^opt:"),
            ],
            AWAITING_TEXT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: handle_text_input(u, c, price_list, lang_store, config)),
                MessageHandler(filters.LOCATION, lambda u, c: handle_location_shared(u, c, price_list, lang_store)),
            ],
            AWAITING_BUNDLE_CHOICE: [
                CallbackQueryHandler(lambda u, c: handle_bundle_choice(u, c, price_list, lang_store), pattern=r"^bundle:"),
            ],
        },
        fallbacks=[CommandHandler("start", lambda u, c: start(u, c, lang_store))],
    )

    application.add_handler(conversation)
    application.add_handler(CommandHandler("til", lambda u, c: set_language(u, c, lang_store, "uz")))
    application.add_handler(CommandHandler("язык", lambda u, c: set_language(u, c, lang_store, "ru")))

    return application
```

- [ ] **Step 2: Manual smoke test**

Run: `python -c "from alcana_bot.bot import build_application; print('imports OK')"`
Expected: prints `imports OK` with no exceptions.

- [ ] **Step 3: Commit**

```bash
git add src/alcana_bot/bot.py
git commit -m "feat: add full bot conversation flow wiring all pricing modules"
```

---

## Task 12: Application entrypoint

**Files:**
- Create: `src/alcana_bot/main.py`

**Interfaces:**
- Consumes: `load_config`, `load_price_list`, `LangStore`, `build_application`, `anthropic.Anthropic`.
- Produces: a runnable script (`python -m alcana_bot.main`).

- [ ] **Step 1: Write the entrypoint**

```python
# src/alcana_bot/main.py
import logging
import os
from dotenv import load_dotenv
from anthropic import Anthropic

from alcana_bot.config import load_config
from alcana_bot.price_data import load_price_list
from alcana_bot.lang_store import LangStore
from alcana_bot.bot import build_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

def main():
    load_dotenv()
    config = load_config(os.environ)
    price_list = load_price_list("data/price_list.json")
    lang_store = LangStore("data/user_lang.json")
    anthropic_client = Anthropic(api_key=config.anthropic_api_key)
    soffice_path = os.environ.get("SOFFICE_PATH", "soffice")

    application = build_application(config, price_list, lang_store, anthropic_client, soffice_path)
    application.run_polling()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it starts (requires real `.env` with valid tokens)**

Run: `python -m alcana_bot.main`
Expected: logs show the bot has started polling; no exceptions on startup. Stop with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add src/alcana_bot/main.py
git commit -m "feat: add application entrypoint"
```

---

## Task 13: README with setup, prerequisites, and deployment steps

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

```markdown
# Alcana Price Calculator Bot

Telegram bot for Alcana staff to get instant advertising-order price quotes
from a design photo or `.cdr` file. See `docs/superpowers/specs/2026-09-12-price-calculator-bot-design.md`
for the full design rationale.

## Prerequisites

- Python 3.11+
- [LibreOffice](https://www.libreoffice.org/) installed (provides the `soffice`
  binary, used to read page dimensions from `.cdr` files — CorelDraw is not
  required and is not installed on the deployment server)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
  (separate from any Claude.ai/Claude Code subscription — billed per token)
- A Yandex Maps API key (free tier) from [developer.tech.yandex.ru](https://developer.tech.yandex.ru/)

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in the three API keys.
3. If `soffice` isn't on your PATH, set `SOFFICE_PATH` in `.env` to its full path
   (e.g. `C:\Program Files\LibreOffice\program\soffice.exe` on Windows).
4. `pytest` — all tests should pass before running the bot.
5. `python -m alcana_bot.main`

## Updating prices

Edit `data/price_list.json` directly. No code changes needed for a pure price
change. Restart the bot process to pick up the new file.

## Deploying as a 24/7 Windows service

Run continuously on the Schneider server using NSSM (Non-Sucking Service Manager):

1. Download NSSM, run `nssm install AlcanaBot`.
2. Set the application path to your Python interpreter and arguments to
   `-m alcana_bot.main`, with "Startup directory" set to this project folder.
3. Under the "Environment" tab, add `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`,
   `YANDEX_MAPS_API_KEY`, and `SOFFICE_PATH` (or keep using `.env` in the
   startup directory — `python-dotenv` loads it automatically).
4. Start the service: `nssm start AlcanaBot`. It will now run in the
   background and restart automatically on reboot or crash.

## Known v1 limitations (see spec for rationale)

- Distance is estimated (geocoded straight-line x 1.3 road factor), not a
  real routing API — swap `estimate_driving_km` in `distance.py` if precision
  becomes an issue.
- `.cdr` conversion depends on LibreOffice being present and its CDR import
  filter working for the file version in use; if conversion fails, the bot
  asks staff to type dimensions manually instead of guessing.
- 1C integration and consumables/inventory tracking are deferred (see spec).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, prerequisites, and deployment steps"
```

---

## Task 14: Full test suite and manual end-to-end verification

**Files:** none created — verification only.

- [ ] **Step 1: Run the full automated test suite**

Run: `pytest -v`
Expected: all tests across Tasks 1-10 pass (approximately 35 tests).

- [ ] **Step 2: Manual end-to-end test — per-sqm photo order**

Send the bot a photo with visible printed dimension labels (e.g. the
CardioCenter example), select a `per_sqm` category (e.g. `banner_300gr`),
confirm the extracted size looks right, and confirm the final quote total
matches a hand-calculated expectation from `data/price_list.json`.

- [ ] **Step 3: Manual end-to-end test — `.cdr` file order**

Send a real `.cdr` file, confirm `soffice` conversion succeeds and the
extracted page size is reasonable, or that the manual-entry fallback
triggers cleanly if it doesn't.

- [ ] **Step 4: Manual end-to-end test — volumetric letters order**

Send a design with visible individual letters, select a
`per_letter_by_height` category, confirm letter count and height are
extracted (or the manual fallback triggers), and confirm the total equals
`letter_count x price_at_matched_height`.

- [ ] **Step 5: Manual end-to-end test — distance-based install fee**

Provide a typed address and, separately, a shared Telegram location pin;
confirm both resolve to a sensible distance bracket from the workshop
origin.

- [ ] **Step 6: Commit any fixes found during manual testing**

```bash
git add -A
git commit -m "fix: address issues found during manual end-to-end verification"
```
