# Multi-Product Cart + PDF Export — Design

Status: approved by user 2026-09-13, pending write-up into implementation plan.

## Purpose

Two gaps reported by the user after the first round of live staff use:

1. **One order = one product.** Real jobs often combine several different
   products (e.g. a lightbox *and* banners) into a single client quote, but
   today's bot can only price one product per run through the conversation.
2. **Quotes only exist as chat text.** Staff currently have to manually
   retype the bot's quote into another document to hand it to a client.
   A clean, branded PDF they can forward directly would remove that step.

## Non-goals / explicitly deferred

- **Quote-vs-confirmed-order tracking, prepayment recording, `/buyurtmalar`,
  `/hisobot`.** Originally brainstormed alongside these two features, but
  dropped by the user: once a client actually prepays, the order goes into
  1C anyway, so a parallel tracker in the bot would just duplicate that.
  Revisit only if a concrete need shows up in practice.
- **Any persistent storage (database, file log) of past orders.** Without
  the tracking feature above, neither remaining feature needs one — the
  cart lives in memory for the duration of one staff member's conversation,
  and the PDF is rendered on the spot from that same in-memory data.
- **Company logo in the PDF.** The user will send a logo file later; until
  then the PDF header renders a plain text wordmark. Swapping in the real
  logo is a small follow-up once the file exists, not part of this build.
- **Company phone/address in the PDF footer.** Left blank/omitted until the
  user provides the text; not a blocker for the rest of this feature.

## Data model changes

`bundle.py`'s `assemble_bundle` currently takes a single `main_item`. It
changes to take a list:

```python
def assemble_bundle(main_items: list[LineItem], design_item=None, travel_item=None) -> list[LineItem]:
    return [*main_items, *(x for x in (design_item, travel_item) if x is not None)]
```

`presentation.format_quote` already accepts a flat `list[LineItem]` and
numbers/bullets each one — it needs no change to support multiple product
lines.

`context.user_data["cart"]: list[LineItem]` replaces `context.user_data["main_item"]`
as the running list of priced product lines for the order in progress.

## Conversation flow changes

### Building the cart

- `handle_photo` / `handle_document` currently do `context.user_data.clear()`
  unconditionally at the top (so a new photo always starts a brand new
  order). This changes to preserve two keys across the clear:
  `cart` (the running list of already-priced products) and
  `last_quote_items` (see PDF section below) — everything else
  (extracted dimensions, category selection, pending text purpose, etc.)
  is still wiped, since those are specific to whichever single product is
  currently being configured.
  ```python
  cart = context.user_data.get("cart", [])
  last_quote_items = context.user_data.get("last_quote_items")
  context.user_data.clear()
  context.user_data["cart"] = cart
  if last_quote_items is not None:
      context.user_data["last_quote_items"] = last_quote_items
  ```
  This means sending a fresh photo mid-cart "just works" as adding a second
  product, with its own extraction, while a photo sent after a completed
  order (empty cart) behaves exactly as it does today.

- `_finish_main_item` (called once a product's price is fully computed) no
  longer goes straight to the bundle screen. Instead it appends the item to
  `context.user_data["cart"]`, **clears the just-consumed per-product fields**
  (`extracted_dimensions`, `cdr_dimensions`, `image_bytes`, `media_type`,
  `category_id`, `option_index`), and shows a new **cart review** screen.
  This clearing is what makes "➕ Yana qo'shish" safe even when staff don't
  send a new photo: without it, picking a second category that also needs
  `per_sqm` dimensions would silently reuse the *first* product's extracted
  dimensions instead of asking fresh — a silent mispricing bug, not just a
  cosmetic one.

  The cart review screen lists the *whole* running cart, not just the item
  just added, so staff can see the total building up:

  > ✅ Qo'shildi: {latest product} — {latest total} so'm
  >
  > 1️⃣ {product 1} — {total 1} so'm
  > 2️⃣ {product 2} — {total 2} so'm
  >
  > [🗑 1-mahsulotni olib tashlash]   *(one remove button per cart item, only shown once there are 2+)*
  > [🗑 2-mahsulotni olib tashlash]
  > [➕ Yana mahsulot qo'shish]
  > [✅ Tugatish]
  > [⬅️ Orqaga]

- New state `AWAITING_CART_DECISION`, with handlers:
  - `CallbackQueryHandler` pattern `^cart:add$` → jumps to the category-group
    menu (same screen as after uploading a file), so staff can price another
    product from the same design without re-uploading a photo.
  - `CallbackQueryHandler` pattern `^cart:remove:\d+$` → removes that index
    from `context.user_data["cart"]` and re-renders the cart review screen
    (removing the last item when the cart becomes empty falls back to the
    category-group menu, since an empty cart can't be "finished").
  - `CallbackQueryHandler` pattern `^cart:done$` → moves to the existing
    bundle screen (design hours / travel), computed once for the whole cart.
  - `CallbackQueryHandler` pattern `^back$` → returns to wherever configuring
    the just-added product came from (same back-target logic as today's
    per-product back handlers).
  - `MessageHandler(filters.PHOTO)` / `MessageHandler(filters.Document.ALL)`
    → treated exactly like the entry-point handlers (extraction runs, cart
    is preserved per the clear logic above, lands back on the category-group
    menu for the new product).

- `_finish_main_item`'s bundle-defaults toggle logic (`include_design`,
  `include_travel`) now runs once, at `cart:done`, instead of per product.

- `_send_final_quote` builds `items = assemble_bundle(cart, design_item,
  travel_item)`, sends the quote text with a `📄 PDF` button attached, then
  does:
  ```python
  context.user_data.clear()
  context.user_data["last_quote_items"] = items
  ```
  so the next photo starts a genuinely empty cart, while the PDF button
  under the just-sent quote keeps working.

## PDF export

- **Library:** `reportlab` (pure Python — no native OS dependency, unlike
  LibreOffice, which already caused real deployment pain on the old Windows
  Server 2012 R2 box).
- **Font:** a Unicode TTF (DejaVu Sans, regular + bold) checked into
  `assets/fonts/`, registered with `reportlab.pdfbase.pdfmetrics` at
  startup — reportlab's built-in fonts don't cover Cyrillic, which would
  otherwise render as garbage for the Russian-language quotes.
- **Trigger:** `CallbackQueryHandler` pattern `^pdf$`, registered in the
  `AWAITING_FILE` state (where the conversation sits right after a quote is
  sent). Reads `context.user_data["last_quote_items"]`, renders a PDF, and
  sends it via `send_document`. If that key is somehow missing (e.g. a very
  old button tapped after the bot restarted, since `context.user_data` is
  in-memory and doesn't survive a restart), replies with a short "bu taklif
  eskirgan, iltimos qaytadan hisoblang" fallback instead of erroring.
- **Layout:** wordmark header ("ALCANA PRINT", styled) → numbered line-item
  table (name, detail, price — same content and order as the chat quote) →
  bold total row → (blank footer for now, see Non-goals).
- **Filename:** `Alcana_{YYYY-MM-DD}.pdf` (date only — no order id, since
  there's no persisted identifier to include).

## Error handling

- PDF rendering failures (bad font registration, reportlab exception) are
  caught and reported to staff as "PDF yaratib bo'lmadi, iltimos qaytadan
  urinib ko'ring" rather than crashing the conversation — consistent with
  the bot's existing rule that an external/rendering failure never leaves
  staff without a reply.
- Removing the last remaining cart item and landing back on the
  category-group menu must not leave `include_design`/`include_travel` set
  from a since-removed product; those are only computed at `cart:done`, so
  this is naturally correct as long as they're not touched earlier.

## Testing approach

- Unit tests for `assemble_bundle` with multiple main items.
- Handler-level tests (same style as existing `test_bot.py`) for: adding a
  second product via button, adding a second product via a fresh photo,
  removing a cart item, removing the last cart item, and the full
  multi-product quote total.
- Unit tests for the PDF renderer: given a list of `LineItem`s, produces
  non-empty PDF bytes without raising, and (where practical) asserts the
  generated PDF's extracted text contains the expected product names/total
  (`reportlab`-generated PDFs can be read back with `pypdf` for this
  assertion) rather than only checking "it didn't crash".
- Manual end-to-end test against the real bot: a two-product cart (one via
  button, one via a second photo), removing a line, finishing, and tapping
  the PDF button.
