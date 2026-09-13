# Multi-Product Cart + PDF Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff price several different products into one order (a "cart") before finalizing, and let them export any finished quote as a branded PDF.

**Architecture:** The cart is a `list[LineItem]` held in `context.user_data["cart"]` for the lifetime of one order — no database. Finishing a product appends to it and shows a review screen (add another / remove / done) instead of going straight to the design/travel bundle screen; design and travel are still asked exactly once, for the whole cart. The final quote's items feed a new pure-function PDF renderer (`pdf_export.py`, reportlab) that the bot calls on demand from a button under the quote.

**Tech Stack:** Python, `python-telegram-bot` 21.6, `reportlab` (PDF rendering, pure Python — no native OS dependency), `pypdf` (test-only, to read generated PDF text back for assertions).

**Spec:** `docs/superpowers/specs/2026-09-13-multi-product-cart-and-pdf-export-design.md`

## Global Constraints

- No persistent storage of any kind (no database, no file log of past orders) — both features work entirely from the in-memory `context.user_data` of the conversation in progress, per the spec's explicit non-goal.
- Design-hours and travel-fee lines are computed once per whole cart, never per product.
- The PDF renderer must not depend on anything beyond a pure-Python library (`reportlab`) — deliberately avoiding a repeat of the LibreOffice-on-old-Windows-Server deployment pain from the original build.
- PDF text must render Cyrillic correctly (Russian-language quotes) as well as Uzbek Latin — this repo's dev machine and the deployment server are both Windows, so the font comes from the OS's own `C:\Windows\Fonts\tahoma.ttf` / `tahomabd.ttf` (confirmed present on this dev machine; Tahoma ships with every Windows version back to the mid-90s, including Windows Server 2012 R2, specifically because of its broad script coverage) rather than a font file checked into the repo. Both paths are overridable via `FONT_REGULAR_PATH` / `FONT_BOLD_PATH` environment variables, following the same pattern as the existing `SOFFICE_PATH` variable in `main.py`. This is a deliberate refinement over the spec's "bundle a TTF in `assets/fonts/`" wording — it avoids sourcing and licensing a font binary during implementation while meeting the same goal (Cyrillic-safe, no new OS install step).
- Every existing test in the suite must keep passing after every task (run `python -m pytest -q` from the project root, i.e. `D:\alcana price calculator bot`).
- Follow existing code conventions exactly: handler functions take `(update, context, ...)`, state-transition functions return the next `int` state constant, `_show()` (in `bot.py`) is the only way step content reaches the chat, i18n text always goes through `t(key, lang, **kwargs)` in `i18n.py` with both `uz` and `ru` entries.

---

### Task 1: `assemble_bundle` accepts a list of main items

**Files:**
- Modify: `src/alcana_bot/bundle.py`
- Test: `tests/test_bundle.py`

**Interfaces:**
- Produces: `assemble_bundle(main_items: list[LineItem], design_item: LineItem | None = None, travel_item: LineItem | None = None) -> list[LineItem]` — returns `[*main_items, design_item?, travel_item?]`. This is what Task 4 (`_send_final_quote`) will call with the full cart.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/test_bundle.py` with:

```python
from alcana_bot.pricing import LineItem
from alcana_bot.bundle import assemble_bundle, bundle_total

def make_item(total):
    return LineItem(label="x", detail="", unit_price=total, quantity=1, total=total)

def test_assemble_bundle_includes_all_main_items_and_addons():
    main1 = make_item(100000)
    main2 = make_item(50000)
    design = make_item(150000)
    travel = make_item(200000)
    items = assemble_bundle([main1, main2], design, travel)
    assert items == [main1, main2, design, travel]

def test_assemble_bundle_single_main_item_still_works():
    main = make_item(100000)
    items = assemble_bundle([main], design_item=None, travel_item=None)
    assert items == [main]

def test_assemble_bundle_omits_none_addons():
    main1 = make_item(100000)
    main2 = make_item(50000)
    items = assemble_bundle([main1, main2], design_item=None, travel_item=None)
    assert items == [main1, main2]

def test_bundle_total_sums_all_lines():
    items = [make_item(100000), make_item(150000), make_item(200000)]
    assert bundle_total(items) == 450000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bundle.py -v`
Expected: `test_assemble_bundle_includes_all_main_items_and_addons` and `test_assemble_bundle_single_main_item_still_works` FAIL (current `assemble_bundle` takes a single `main_item`, not a list — passing a list makes it the first element of the returned list unchanged, so `items == [main1, main2, design, travel]` fails since the real output is `[[main1, main2], design, travel]`).

- [ ] **Step 3: Update `assemble_bundle`**

Replace the contents of `src/alcana_bot/bundle.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bundle.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/alcana_bot/bundle.py tests/test_bundle.py
git commit -m "Change assemble_bundle to accept a list of main items (multi-product cart)"
```

---

### Task 2: Cart data model — appending a finished product shows a cart-review screen

**Files:**
- Modify: `src/alcana_bot/i18n.py`
- Modify: `src/alcana_bot/presentation.py`
- Modify: `src/alcana_bot/bot.py`
- Test: `tests/test_presentation.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `assemble_bundle` from Task 1 (not called yet in this task — that's Task 4).
- Produces: `AWAITING_CART_DECISION` state constant (`bot.py`); `context.user_data["cart"]: list[LineItem]`; `format_cart_review(items: list[LineItem], lang: str, price_list) -> str` (`presentation.py`), used by the next task's keyboard-building helper too.

- [ ] **Step 1: Add the new i18n keys**

In `src/alcana_bot/i18n.py`, add these entries to the `TRANSLATIONS` dict (anywhere among the existing entries, e.g. right after `"quote_total"`):

```python
    "cart_item_added": {
        "uz": "✅ Qo'shildi: {label} — {total} so'm",
        "ru": "✅ Добавлено: {label} — {total} сум",
    },
    "cart_add_button": {
        "uz": "➕ Yana mahsulot qo'shish",
        "ru": "➕ Добавить ещё товар",
    },
    "cart_done_button": {
        "uz": "✅ Tugatish",
        "ru": "✅ Завершить",
    },
    "cart_remove_button": {
        "uz": "🗑 {label} ni olib tashlash",
        "ru": "🗑 Убрать: {label}",
    },
```

- [ ] **Step 2: Write the failing test for `format_cart_review`**

Add to `tests/test_presentation.py`:

```python
from alcana_bot.presentation import format_cart_review

def test_format_cart_review_lists_every_item_and_shows_the_latest_addition():
    items = [
        LineItem(label="banner_300gr", detail="200x150 см", unit_price=30000, quantity=3.0, total=90000),
        LineItem(label="design_service", detail="2 hour", unit_price=150000, quantity=2, total=300000),
    ]
    text = format_cart_review(items, "ru", PRICE_LIST)
    assert "Баннер 300 гр" in text
    assert "Дизайн хизмати" in text
    assert "90 000" in text
    assert "300 000" in text
    assert "Добавлено" in text  # the "just added" header uses the LAST item
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_presentation.py::test_format_cart_review_lists_every_item_and_shows_the_latest_addition -v`
Expected: FAIL with `ImportError` or `AttributeError` — `format_cart_review` doesn't exist yet.

- [ ] **Step 4: Implement `format_cart_review`**

In `src/alcana_bot/presentation.py`, add this function after `format_quote`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_presentation.py -v`
Expected: all tests PASS, including the new one.

- [ ] **Step 6: Write the failing bot-level tests**

Add to `tests/test_bot.py` (near the other `_finish_main_item`-adjacent tests — anywhere after the imports/fakes section is fine):

```python
from alcana_bot.bot import AWAITING_CART_DECISION

def test_finishing_a_product_appends_to_cart_and_shows_review_screen():
    update = make_text_update("10")
    context = make_context()
    context.user_data.update({"category_id": "rollup_200x80", "pending_text_purpose": "piece_count"})

    state = asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))

    assert state == AWAITING_CART_DECISION
    assert len(context.user_data["cart"]) == 1
    assert context.user_data["cart"][0].total == 6500000
    assert "main_item" not in context.user_data  # replaced by the cart list


def test_finishing_a_second_product_appends_without_losing_the_first():
    context = make_context()
    context.user_data["cart"] = [MagicMock(total=100000)]
    context.user_data.update({"category_id": "rollup_200x80", "pending_text_purpose": "piece_count"})
    update = make_text_update("2")

    asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))

    assert len(context.user_data["cart"]) == 2
    assert context.user_data["cart"][1].total == 1300000


def test_finishing_a_product_clears_its_per_product_fields():
    """Regression guard: without this, adding a second per_sqm product via
    'add another' (no new photo) would silently reuse the FIRST product's
    extracted dimensions instead of asking fresh."""
    update = make_text_update("10")
    context = make_context()
    context.user_data.update({
        "category_id": "rollup_200x80",
        "pending_text_purpose": "piece_count",
        "extracted_dimensions": {"width_cm": 200, "height_cm": 150},
        "cdr_dimensions": (200, 150),
        "image_bytes": b"fake",
        "media_type": "image/jpeg",
        "option_index": 0,
    })

    asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))

    for key in ("extracted_dimensions", "cdr_dimensions", "image_bytes", "media_type", "category_id", "option_index"):
        assert key not in context.user_data
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot.py -k cart -v`
Expected: FAIL — `AWAITING_CART_DECISION` doesn't exist yet, and `_finish_main_item` still sets `main_item` / goes to the bundle screen.

- [ ] **Step 8: Implement the cart model in `bot.py`**

In `src/alcana_bot/bot.py`:

1. Add the new state to the state tuple (insert `AWAITING_CART_DECISION` after `AWAITING_TEXT_INPUT`, update `range(8)` to `range(9)`):

```python
(
    AWAITING_LANGUAGE,
    AWAITING_FILE,
    AWAITING_CATEGORY_GROUP,
    AWAITING_CATEGORY,
    AWAITING_OPTION,
    AWAITING_TEXT_INPUT,
    AWAITING_CART_DECISION,
    AWAITING_BUNDLE_CHOICE,
    AWAITING_BRACKET_CHOICE,
) = range(9)
```

2. Update the import line for `presentation` to also bring in `format_cart_review`:

```python
from alcana_bot.presentation import build_group_choices, build_category_choices, format_quote, format_cart_review
```

3. Add a cart keyboard builder and a screen-show helper, right after `_show_bundle_menu`:

```python
def _cart_keyboard(context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang: str) -> InlineKeyboardMarkup:
    cart = context.user_data.get("cart", [])
    rows = []
    if len(cart) >= 2:
        for index, item in enumerate(cart):
            category = price_list.categories.get(item.label)
            label = category.display_name(lang) if category is not None else item.label
            rows.append([InlineKeyboardButton(t("cart_remove_button", lang, label=label), callback_data=f"cart:remove:{index}")])
    rows.append([InlineKeyboardButton(t("cart_add_button", lang), callback_data="cart:add")])
    rows.append([InlineKeyboardButton(t("cart_done_button", lang), callback_data="cart:done")])
    rows.append([InlineKeyboardButton(t("back_button", lang), callback_data="back")])
    return InlineKeyboardMarkup(rows)


async def _show_cart_review(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang: str) -> int:
    cart = context.user_data["cart"]
    text = format_cart_review(cart, lang, price_list)
    await _show(update, context, text, reply_markup=_cart_keyboard(context, price_list, lang))
    return AWAITING_CART_DECISION
```

4. Replace the body of `_finish_main_item` so it appends to the cart and clears the fields specific to the product just finished, instead of setting `main_item` and jumping to the bundle screen:

```python
async def _finish_main_item(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, item) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    context.user_data.setdefault("cart", []).append(item)
    for key in ("extracted_dimensions", "cdr_dimensions", "image_bytes", "media_type", "category_id", "option_index"):
        context.user_data.pop(key, None)
    return await _show_cart_review(update, context, price_list, lang)
```

(This task does not yet wire up `cart:add` / `cart:remove` / `cart:done` / the `back` button on this screen, or the bundle-defaults toggling that used to live in `_finish_main_item` — that's Task 3. The app is not fully usable end-to-end again until Task 3 lands; this task's own tests only check the cart-append and screen-render behavior in isolation.)

- [ ] **Step 9: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -k cart -v`
Expected: all 3 new tests PASS.

- [ ] **Step 10: Run the full suite to check nothing else broke**

Run: `python -m pytest -q`
Expected: some pre-existing tests that asserted the old `main_item`/bundle-screen behavior of `_finish_main_item` will now FAIL (e.g. `test_fixed_category_asks_for_piece_count_instead_of_pricing_immediately` still passes since it stops before `_finish_main_item`, but anything asserting `state == AWAITING_BUNDLE_CHOICE` or reading `context.user_data["main_item"]` right after a `_finish_main_item` call will fail). Update those specific assertions now to match the new cart behavior — for each failing test, change `AWAITING_BUNDLE_CHOICE` to `AWAITING_CART_DECISION` and `context.user_data["main_item"]` to `context.user_data["cart"][0]`, then re-run. Do not touch tests unrelated to this failure mode.

- [ ] **Step 11: Commit**

```bash
git add src/alcana_bot/i18n.py src/alcana_bot/presentation.py src/alcana_bot/bot.py tests/test_presentation.py tests/test_bot.py
git commit -m "Add cart data model: finishing a product appends to context.user_data['cart'] and shows a review screen"
```

---

### Task 3: Wire up the cart-review screen's buttons and photo/document entry

**Files:**
- Modify: `src/alcana_bot/bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `AWAITING_CART_DECISION`, `_show_cart_review`, `_cart_keyboard` from Task 2.
- Produces: `handle_cart_add`, `handle_cart_remove`, `handle_cart_done`, `handle_category_group_back` (signature changes to take `price_list`) — all registered against the `ConversationHandler`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_bot.py`, extend the existing `from alcana_bot.bot import (...)` block at the top of the file (the one that already imports `AWAITING_BRACKET_CHOICE, AWAITING_BUNDLE_CHOICE, ...`) to add these four names to it: `handle_cart_add, handle_cart_remove, handle_cart_done, handle_category_group_back`.

Then add to `tests/test_bot.py`:

```python
def _cart_context(cart):
    context = make_context()
    context.user_data["cart"] = cart
    return context


def test_cart_add_button_goes_to_category_group_menu():
    context = _cart_context([MagicMock(total=100000)])
    update = make_callback_update("cart:add")

    state = asyncio.run(handle_cart_add(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_CATEGORY_GROUP


def test_cart_remove_drops_that_index_and_restays_on_review():
    item1, item2 = MagicMock(total=100000), MagicMock(total=200000)
    context = _cart_context([item1, item2])
    update = make_callback_update("cart:remove:0")

    state = asyncio.run(handle_cart_remove(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_CART_DECISION
    assert context.user_data["cart"] == [item2]


def test_cart_remove_last_item_falls_back_to_category_group_menu():
    context = _cart_context([MagicMock(total=100000)])
    update = make_callback_update("cart:remove:0")

    state = asyncio.run(handle_cart_remove(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_CATEGORY_GROUP
    assert context.user_data["cart"] == []


def test_cart_done_sets_bundle_defaults_and_shows_bundle_menu():
    context = _cart_context([MagicMock(total=100000)])
    update = make_callback_update("cart:done")

    state = asyncio.run(handle_cart_done(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_BUNDLE_CHOICE
    always = PRICE_LIST.bundle_defaults.get("always_include", [])
    assert context.user_data["include_design"] == ("design_service" in always)
    assert context.user_data["include_travel"] == ("install_travel_fee" in always)


def test_category_group_back_with_empty_cart_resets_to_welcome():
    context = make_context()  # no cart at all -- first product in progress
    update = make_callback_update("back")

    state = asyncio.run(handle_category_group_back(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_FILE
    assert context.user_data == {}


def test_category_group_back_with_existing_cart_returns_to_cart_review():
    context = _cart_context([MagicMock(total=100000)])
    update = make_callback_update("back")

    state = asyncio.run(handle_category_group_back(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_CART_DECISION
    assert len(context.user_data["cart"]) == 1  # not lost
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot.py -k "cart_add or cart_remove or cart_done or category_group_back" -v`
Expected: FAIL — `handle_cart_add`/`handle_cart_remove`/`handle_cart_done` don't exist yet, and `handle_category_group_back` doesn't take a `price_list` argument yet.

- [ ] **Step 3: Implement the handlers**

In `src/alcana_bot/bot.py`, replace `handle_category_group_back` with a cart-aware version, and add the three new cart handlers right after it:

```python
async def handle_category_group_back(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    if context.user_data.get("cart"):
        return await _show_cart_review(update, context, price_list, lang)
    context.user_data.clear()
    await _show(update, context, t("welcome", lang))
    return AWAITING_FILE


async def handle_cart_add(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    return await _show_category_group_menu(update, context, price_list, lang)


async def handle_cart_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    index = int(query.data.split(":", 2)[2])
    cart = context.user_data.get("cart", [])
    if 0 <= index < len(cart):
        cart.pop(index)
    if not cart:
        return await _show_category_group_menu(update, context, price_list, lang)
    return await _show_cart_review(update, context, price_list, lang)


async def handle_cart_done(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    always_include = price_list.bundle_defaults.get("always_include", [])
    context.user_data["include_design"] = DESIGN_CATEGORY_ID in always_include
    context.user_data["include_travel"] = TRAVEL_CATEGORY_ID in always_include
    return await _show_bundle_menu(update, context, lang)
```

- [ ] **Step 4: Wire the new state and handler into `build_application`**

In `src/alcana_bot/bot.py`, inside `build_application`'s `conversation = ConversationHandler(...)`:

1. Change the `AWAITING_CATEGORY_GROUP` back-handler line's callback (the `handle_category_group_back` lambda) to pass `price_list` too:

```python
            AWAITING_CATEGORY_GROUP: [
                CallbackQueryHandler(lambda u, c: handle_category_group_selected(u, c, price_list, lang_store), pattern=r"^grp:"),
                CallbackQueryHandler(lambda u, c: handle_category_group_back(u, c, price_list, lang_store), pattern=r"^back$"),
            ],
```

2. Add the new `AWAITING_CART_DECISION` entry to the `states` dict (place it after `AWAITING_TEXT_INPUT`'s block):

```python
            AWAITING_CART_DECISION: [
                CallbackQueryHandler(lambda u, c: handle_cart_add(u, c, price_list, lang_store), pattern=r"^cart:add$"),
                CallbackQueryHandler(lambda u, c: handle_cart_remove(u, c, price_list, lang_store), pattern=r"^cart:remove:\d+$"),
                CallbackQueryHandler(lambda u, c: handle_cart_done(u, c, price_list, lang_store), pattern=r"^cart:done$"),
                CallbackQueryHandler(lambda u, c: handle_category_group_back(u, c, price_list, lang_store), pattern=r"^back$"),
                MessageHandler(filters.PHOTO, lambda u, c: handle_photo(u, c, price_list, lang_store, vision_client)),
                MessageHandler(filters.Document.ALL, lambda u, c: handle_document(u, c, price_list, lang_store, soffice_path)),
            ],
```

(Reusing `handle_category_group_back` as the cart-review screen's `back` handler too is intentional: at this point the just-finished product is already priced and stored, so "back" and "add another" both mean "go pick what's next" — there's nothing to "undo" here, that's what the per-item 🗑 remove buttons are for.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -v`
Expected: all tests PASS (including the ones from Task 2 and the pre-existing suite).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/alcana_bot/bot.py tests/test_bot.py
git commit -m "Wire up cart review screen: add another product, remove a line, finish to bundle screen"
```

---

### Task 4: Build the final quote from the whole cart, attach a PDF button, and preserve cart/last-quote data across a new upload

**Files:**
- Modify: `src/alcana_bot/i18n.py`
- Modify: `src/alcana_bot/bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `assemble_bundle(main_items, design_item, travel_item)` from Task 1.
- Produces: `context.user_data["last_quote_items"]` (consumed by Task 6's PDF-button handler).

- [ ] **Step 1: Add the PDF button's i18n key**

In `src/alcana_bot/i18n.py`, add to `TRANSLATIONS`:

```python
    "pdf_button": {
        "uz": "📄 PDF",
        "ru": "📄 PDF",
    },
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_bot.py`:

```python
def test_final_quote_includes_every_cart_item():
    context = make_context()
    context.user_data["cart"] = [
        MagicMock(label="banner_300gr", total=90000),
        MagicMock(label="design_service", total=300000),
    ]
    context.user_data["design_item"] = None
    update = make_callback_update("bracket:1")

    state = asyncio.run(handle_bracket_selected(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_FILE
    quote = _all_text(update)
    assert "90 000" in quote
    assert "300 000" in quote
    assert "150 000" in quote  # the travel bracket line itself


def test_final_quote_attaches_a_pdf_button():
    context = make_context()
    context.user_data["cart"] = [MagicMock(label="banner_300gr", total=90000)]
    context.user_data["design_item"] = None
    update = make_callback_update("bracket:1")

    asyncio.run(handle_bracket_selected(update, context, PRICE_LIST, FakeLangStore()))

    markup = update.callback_query.message.edit_text.call_args.kwargs["reply_markup"]
    callback_datas = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "pdf" in callback_datas


def test_final_quote_resets_cart_but_keeps_last_quote_items_for_the_pdf_button():
    context = make_context()
    context.user_data["cart"] = [MagicMock(label="banner_300gr", total=90000)]
    context.user_data["design_item"] = None
    update = make_callback_update("bracket:1")

    asyncio.run(handle_bracket_selected(update, context, PRICE_LIST, FakeLangStore()))

    assert "cart" not in context.user_data  # wiped so the next photo starts empty
    assert len(context.user_data["last_quote_items"]) == 2  # main item + travel


def test_new_photo_after_a_finished_order_starts_a_fresh_empty_cart(mocker):
    mocker.patch("alcana_bot.bot.extract_dimensions_from_image", side_effect=bot_module.ExtractionError("no client"))
    context = make_context()
    context.user_data["last_quote_items"] = [MagicMock(total=1)]
    update = SimpleNamespace(
        message=SimpleNamespace(
            photo=[SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace(
                download_as_bytearray=AsyncMock(return_value=bytearray(b"fake")),
            )))],
        ),
        callback_query=None,
        effective_user=SimpleNamespace(id=42),
        effective_chat=SimpleNamespace(id=1, send_message=AsyncMock(return_value=make_fake_message())),
    )

    from alcana_bot.bot import handle_photo
    asyncio.run(handle_photo(update, context, PRICE_LIST, FakeLangStore(), None))

    assert context.user_data["cart"] == []
    assert context.user_data["last_quote_items"] == [MagicMock(total=1)]
```

This test needs `mocker` (pytest-mock, already a project dependency) since `handle_photo` calls the real vision extraction otherwise — patching `alcana_bot.bot.extract_dimensions_from_image` to raise `ExtractionError` exercises the same fallback path `handle_photo` already has for a failed extraction, without needing a real or fake vision client.

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot.py -k "final_quote or fresh_empty_cart" -v`
Expected: FAIL — `_send_final_quote` still reads `context.user_data["main_item"]` (a `KeyError` now, since Task 2/3 replaced it with `cart`), has no PDF button, and doesn't set `last_quote_items`; `handle_photo` doesn't yet preserve `cart`/`last_quote_items` across its clear.

- [ ] **Step 4: Update `_send_final_quote`**

In `src/alcana_bot/bot.py`, replace `_send_final_quote`:

```python
async def _send_final_quote(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, travel_item) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    items = assemble_bundle(context.user_data["cart"], context.user_data.get("design_item"), travel_item)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(t("pdf_button", lang), callback_data="pdf")]])
    await _show(update, context, format_quote(items, lang, price_list), reply_markup=keyboard)
    context.user_data.clear()
    context.user_data["last_quote_items"] = items
    return AWAITING_FILE
```

- [ ] **Step 5: Update `handle_photo` and `handle_document` to preserve the cart and last quote across their clear**

In `src/alcana_bot/bot.py`, replace the first line of both `handle_photo` and `handle_document` (`context.user_data.clear()`) with:

```python
    cart = context.user_data.get("cart", [])
    last_quote_items = context.user_data.get("last_quote_items")
    context.user_data.clear()
    context.user_data["cart"] = cart
    if last_quote_items is not None:
        context.user_data["last_quote_items"] = last_quote_items
```

(Apply this identically in both functions, right where `context.user_data.clear()` currently is.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -v`
Expected: all tests PASS.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/alcana_bot/i18n.py src/alcana_bot/bot.py tests/test_bot.py
git commit -m "Build the final quote from the whole cart, attach a PDF button, preserve cart/last-quote data across uploads"
```

---

### Task 5: PDF rendering module

**Files:**
- Create: `src/alcana_bot/pdf_export.py`
- Modify: `requirements.txt`
- Test: `tests/test_pdf_export.py`

**Interfaces:**
- Consumes: `LineItem` (`pricing.py`), `bundle_total` (`bundle.py`), `PriceList.categories[id].display_name(lang)` (`price_data.py`).
- Produces: `render_quote_pdf(items: list[LineItem], lang: str, price_list: PriceList) -> bytes` and `PdfExportError` — both consumed by Task 6's bot.py handler.

- [ ] **Step 1: Add dependencies**

In `requirements.txt`, add these two lines (anywhere, e.g. right after `defusedxml==0.7.1`):

```
reportlab==4.2.5
pypdf==5.1.0
```

Run: `pip install -r requirements.txt`
Expected: both packages install without error. If either exact version 404s from PyPI, install the latest available patch of that same minor line instead (e.g. `reportlab==4.2.x`) and update `requirements.txt` to match what actually installed — this is a version-pin detail, not a design change.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_pdf_export.py`:

```python
from io import BytesIO

import pytest
from pypdf import PdfReader

from alcana_bot.pdf_export import render_quote_pdf, PdfExportError
from alcana_bot.pricing import LineItem
from alcana_bot.price_data import load_price_list

PRICE_LIST = load_price_list("data/price_list.json")


def make_item(label, detail, total):
    return LineItem(label=label, detail=detail, unit_price=total, quantity=1, total=total)


def test_render_quote_pdf_returns_pdf_bytes():
    items = [make_item("banner_300gr", "200x150 см", 90000)]
    pdf_bytes = render_quote_pdf(items, "ru", PRICE_LIST)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_render_quote_pdf_contains_product_name_and_amount():
    items = [make_item("banner_300gr", "200x150 см", 90000)]
    pdf_bytes = render_quote_pdf(items, "ru", PRICE_LIST)
    text = PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()
    assert "Баннер 300 гр" in text
    assert "90" in text and "000" in text


def test_render_quote_pdf_multiple_items_shows_grand_total():
    items = [
        make_item("banner_300gr", "200x150 см", 90000),
        make_item("design_service", "2 hour", 300000),
    ]
    pdf_bytes = render_quote_pdf(items, "uz", PRICE_LIST)
    text = PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()
    assert "390" in text  # 90 000 + 300 000 grand total


def test_render_quote_pdf_empty_items_raises():
    with pytest.raises(PdfExportError):
        render_quote_pdf([], "ru", PRICE_LIST)


def test_render_quote_pdf_unknown_font_path_raises_pdf_export_error(monkeypatch):
    monkeypatch.setattr("alcana_bot.pdf_export._FONT_REGULAR_PATH", r"C:\does\not\exist.ttf")
    monkeypatch.setattr("alcana_bot.pdf_export._registered", False)
    with pytest.raises(PdfExportError):
        render_quote_pdf([make_item("banner_300gr", "x", 1)], "ru", PRICE_LIST)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_pdf_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alcana_bot.pdf_export'`.

- [ ] **Step 4: Implement `pdf_export.py`**

Create `src/alcana_bot/pdf_export.py`:

```python
import os
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from alcana_bot.bundle import bundle_total
from alcana_bot.price_data import PriceList
from alcana_bot.pricing import LineItem


class PdfExportError(Exception):
    pass


# Windows ships Tahoma with every version back to the mid-90s specifically
# for its broad script coverage (Cyrillic + extended Latin), so it renders
# both Uzbek and Russian quotes correctly with no font file to source or
# check into the repo. Both this dev machine and the deployment server are
# Windows, so this is a safe default; override via env var if that ever
# changes, same pattern as SOFFICE_PATH in main.py.
_FONT_REGULAR_PATH = os.environ.get("FONT_REGULAR_PATH", r"C:\Windows\Fonts\tahoma.ttf")
_FONT_BOLD_PATH = os.environ.get("FONT_BOLD_PATH", r"C:\Windows\Fonts\tahomabd.ttf")
_FONT_REGULAR = "AlcanaSans"
_FONT_BOLD = "AlcanaSans-Bold"
_registered = False

_TITLES = {"uz": "Hisob-kitob", "ru": "Смета"}
_TOTAL_LABELS = {"uz": "Jami", "ru": "Итого"}
_CURRENCY = {"uz": "so'm", "ru": "сум"}


def _ensure_fonts_registered() -> None:
    global _registered
    if _registered:
        return
    try:
        pdfmetrics.registerFont(TTFont(_FONT_REGULAR, _FONT_REGULAR_PATH))
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, _FONT_BOLD_PATH))
    except Exception as e:
        raise PdfExportError(f"Could not register PDF font from '{_FONT_REGULAR_PATH}': {type(e).__name__}: {e}") from e
    _registered = True


def _display_label(price_list: PriceList, category_id: str, lang: str) -> str:
    category = price_list.categories.get(category_id)
    return category.display_name(lang) if category is not None else category_id


def render_quote_pdf(items: list[LineItem], lang: str, price_list: PriceList) -> bytes:
    if not items:
        raise PdfExportError("Cannot render a PDF for an empty quote")
    _ensure_fonts_registered()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 2 * cm
    y = height - margin

    pdf.setFont(_FONT_BOLD, 18)
    pdf.drawString(margin, y, "ALCANA PRINT")
    y -= 1 * cm

    pdf.setFont(_FONT_BOLD, 14)
    pdf.drawString(margin, y, _TITLES.get(lang, _TITLES["ru"]))
    y -= 1 * cm

    currency = _CURRENCY.get(lang, _CURRENCY["ru"])
    for index, item in enumerate(items, start=1):
        label = _display_label(price_list, item.label, lang)
        total_str = f"{item.total:,}".replace(",", " ")
        pdf.setFont(_FONT_BOLD, 11)
        pdf.drawString(margin, y, f"{index}. {label}")
        y -= 0.6 * cm
        pdf.setFont(_FONT_REGULAR, 11)
        pdf.drawString(margin + 0.5 * cm, y, f"{item.detail} \u2014 {total_str} {currency}")
        y -= 0.9 * cm

    y -= 0.3 * cm
    pdf.line(margin, y, width - margin, y)
    y -= 0.8 * cm

    total_str = f"{bundle_total(items):,}".replace(",", " ")
    pdf.setFont(_FONT_BOLD, 13)
    pdf.drawString(margin, y, f"{_TOTAL_LABELS.get(lang, _TOTAL_LABELS['ru'])}: {total_str} {currency}")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_pdf_export.py -v`
Expected: all 5 tests PASS. If `test_render_quote_pdf_contains_product_name_and_amount` fails only on the "90" + "000" assertion because `pypdf`'s text extraction inserts unexpected spacing, loosen that specific assertion to `assert "90" in text.replace(" ", "").replace("\xa0", "") or "90 000" in text` — do not change the PDF-generation code to chase an extraction-library quirk. The bold-vs-regular font names (`AlcanaSans` / `AlcanaSans-Bold`) are for reportlab's own kerning tables, not what pypdf surfaces to you.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/alcana_bot/pdf_export.py requirements.txt tests/test_pdf_export.py
git commit -m "Add PDF quote renderer using reportlab and the OS Tahoma font (Cyrillic + Latin)"
```

---

### Task 6: Wire the "📄 PDF" button to actually generate and send the file

**Files:**
- Modify: `src/alcana_bot/i18n.py`
- Modify: `src/alcana_bot/bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `render_quote_pdf`, `PdfExportError` from Task 5; `context.user_data["last_quote_items"]` from Task 4.

- [ ] **Step 1: Add the fallback-message i18n keys**

In `src/alcana_bot/i18n.py`, add to `TRANSLATIONS`:

```python
    "pdf_expired": {
        "uz": "Bu taklif eskirgan, iltimos qaytadan hisoblang.",
        "ru": "Это предложение устарело, пожалуйста, посчитайте заново.",
    },
    "pdf_generation_failed": {
        "uz": "PDF yaratib bo'lmadi, iltimos qaytadan urinib ko'ring.",
        "ru": "Не удалось создать PDF, пожалуйста, попробуйте ещё раз.",
    },
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_bot.py`:

```python
def test_pdf_button_sends_a_document_when_last_quote_items_present(mocker):
    mocker.patch("alcana_bot.bot.render_quote_pdf", return_value=b"%PDF-fake-bytes")
    context = make_context()
    context.user_data["last_quote_items"] = [MagicMock(total=1)]
    update = make_callback_update("pdf")

    from alcana_bot.bot import handle_pdf_export
    state = asyncio.run(handle_pdf_export(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_FILE
    update.effective_chat.send_document.assert_awaited()
    _, kwargs = update.effective_chat.send_document.call_args
    assert kwargs["filename"].endswith(".pdf")


def test_pdf_button_with_no_last_quote_shows_expired_message():
    context = make_context()  # no last_quote_items at all
    update = make_callback_update("pdf")

    from alcana_bot.bot import handle_pdf_export
    state = asyncio.run(handle_pdf_export(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_FILE
    update.callback_query.message.reply_text.assert_awaited()
    text = update.callback_query.message.reply_text.call_args.args[0]
    assert "eskirgan" in text or "устарело" in text


def test_pdf_button_render_failure_shows_friendly_error(mocker):
    mocker.patch("alcana_bot.bot.render_quote_pdf", side_effect=bot_module.PdfExportError("font missing"))
    context = make_context()
    context.user_data["last_quote_items"] = [MagicMock(total=1)]
    update = make_callback_update("pdf")

    from alcana_bot.bot import handle_pdf_export
    state = asyncio.run(handle_pdf_export(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_FILE
    update.callback_query.message.reply_text.assert_awaited()
```

Update `make_callback_update` and `make_text_update` in `tests/test_bot.py` (both already define `effective_chat=SimpleNamespace(id=1, send_message=AsyncMock(...))`) to also give `effective_chat` a `send_document=AsyncMock()` attribute, e.g.:

```python
        effective_chat=SimpleNamespace(id=1, send_message=AsyncMock(return_value=make_fake_message()), send_document=AsyncMock()),
```

(apply this same addition to both factory functions).

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot.py -k pdf_button -v`
Expected: FAIL — `handle_pdf_export` doesn't exist, `alcana_bot.bot` has no `render_quote_pdf`/`PdfExportError` names to patch yet.

- [ ] **Step 4: Implement `handle_pdf_export` and wire it in**

In `src/alcana_bot/bot.py`:

1. Add these imports near the top, alongside the other `alcana_bot` imports:

```python
from datetime import datetime
from io import BytesIO
from alcana_bot.pdf_export import render_quote_pdf, PdfExportError
```

2. Add the handler, after `handle_bracket_text_fallback`:

```python
async def handle_pdf_export(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    items = context.user_data.get("last_quote_items")
    if not items:
        await query.message.reply_text(t("pdf_expired", lang))
        return AWAITING_FILE

    try:
        # reportlab's rendering is synchronous CPU work -- off the event loop
        # so it doesn't stall the bot for every other staff member.
        pdf_bytes = await asyncio.to_thread(render_quote_pdf, items, lang, price_list)
    except PdfExportError as e:
        logger.error("PDF rendering failed: %s", e)
        await query.message.reply_text(t("pdf_generation_failed", lang))
        return AWAITING_FILE

    filename = f"Alcana_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    await update.effective_chat.send_document(document=BytesIO(pdf_bytes), filename=filename)
    return AWAITING_FILE
```

3. Register it in `build_application`'s `AWAITING_FILE` state:

```python
            AWAITING_FILE: [
                MessageHandler(filters.PHOTO, lambda u, c: handle_photo(u, c, price_list, lang_store, vision_client)),
                MessageHandler(filters.Document.ALL, lambda u, c: handle_document(u, c, price_list, lang_store, soffice_path)),
                CallbackQueryHandler(lambda u, c: handle_pdf_export(u, c, price_list, lang_store), pattern=r"^pdf$"),
            ],
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests PASS, no warnings beyond the pre-existing `google-genai` deprecation warning.

- [ ] **Step 7: Manual end-to-end smoke test against the real bot**

With the bot running locally (`python -m alcana_bot.main`, `PYTHONPATH=src`), in Telegram:
1. Send a photo, price one product, tap "➕ Yana mahsulot qo'shish", price a second (different category) product.
2. Confirm the cart review screen lists both.
3. Tap "🗑" on one of them, confirm it's removed and the other remains.
4. Tap "✅ Tugatish", answer design hours and address as usual, confirm the final quote lists the remaining cart item(s) + design + travel with a correct grand total.
5. Tap "📄 PDF" and confirm a PDF file arrives in the chat, opens correctly, and the Uzbek/Russian text (whichever language is active) renders correctly rather than as boxes/garbage.
6. Send a new photo and confirm it starts a completely empty cart (not carrying over the previous order's items).

- [ ] **Step 8: Commit**

```bash
git add src/alcana_bot/i18n.py src/alcana_bot/bot.py tests/test_bot.py
git commit -m "Wire the PDF button to render and send the quote as a file"
```
