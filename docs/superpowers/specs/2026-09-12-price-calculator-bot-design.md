# Alcana Price Calculator Bot — Design

Status: approved by user 2026-09-12, pending write-up into implementation plan.

## Purpose

Alcana's designers/sales staff currently calculate advertising order prices
(lightboxes, banners, oracal prints, volumetric letters, neon, installation,
etc.) by hand against a price list PDF. This bot lets staff send the design
file they'd normally forward to the workshop (a photo with dimensions
annotated on it, or a CorelDraw `.cdr` file) into a Telegram bot, answer a
short set of follow-up questions, and get back an itemized price
in Uzbek or Russian — with no manual price-list lookup.

**Users:** internal staff only (designers, sales). Not customer-facing.

## Non-goals / explicitly deferred

- **1C integration** — add only after the bot is running successfully in
  practice. Out of scope for v1.
- **Consumables/inventory tracking** — good idea, deferred. Needs a
  "this was just a quote" vs. "this became a confirmed order" distinction
  first, since many calculated quotes never turn into a real order and must
  not decrement stock. Nothing to build for this now; v1's flow should not
  be redesigned later to add it, but no work happens on it yet.
- **Client-facing / portfolio features** — dropped for now, being handled
  through a different channel.

## Architecture

- **Language:** Python (`python-telegram-bot`).
- **Transport:** Telegram long-polling. No public URL, no open inbound port,
  no webhook — the bot continuously asks Telegram for new messages. This
  matters because it needs to run on the Schneider server
  (185.181.165.188) purely over outbound internet access, the same reason
  the user's existing n8n automations are polling-only.
- **Hosting:** runs as a Windows service on the Schneider server (via NSSM
  or Task Scheduler "run at startup"), so it survives reboots and doesn't
  need an open RDP session to stay alive.
- **Vision/extraction model:** Claude Haiku 4.5 (`claude-haiku-4-5`) via the
  Anthropic API. Chosen over a general OCR library because the source
  photos have rotated/stylized dimension labels and mixed Uzbek/Russian
  units; chosen over a larger Claude model because this is a narrow,
  well-defined extraction task and Haiku keeps per-order cost near zero
  (well under $0.01/order). Escalate to a larger model later only if
  extraction accuracy proves insufficient in practice.
- **Distance/geocoding:** Yandex Maps API (better address coverage for
  Uzbekistan than Google Maps).

## Price data

Price list is encoded once as `data/price_list.json` (already written,
transcribed from `Прайс 10.09.2026 NEW.pdf`, dated 2026-09-10). Updating
prices later means editing that file — no code changes.

Each category has a `pricing_type` that drives how the bot computes the
line total:

| pricing_type | Computation |
|---|---|
| `fixed` | flat price, quantity 1 unless asked |
| `fixed_options` | staff/bot picks one of several flat-price variants |
| `per_sqm` | price × area (m²) from extracted or manually entered dimensions |
| `per_sqm_options` | staff picks a variant, then price_per_sqm × area |
| `per_letter_by_height` | price-at-height × letter count (see below) |
| `per_hour` / `per_minute` / `per_meter` | price × duration/length, asked directly |
| `distance_bracket` | resolved automatically from computed driving distance |

### Confirmed pricing assumptions (from user)

- Volumetric letters (items 24–27 in the PDF) are priced **per individual
  letter** at a given height bracket (60/80/100/120 cm) — not per cm of
  height, not a flat sign price. The bot **must count the letters in the
  design automatically** rather than asking staff to type a count.
- `rollup_200x80` (PDF row 13, "1-10 шт") is treated as a flat per-piece
  price regardless of quantity ordered within that range. Flagged in the
  JSON as an assumption — revisit if bulk orders should get a discount.

## Order flow

1. Staff sends a photo or `.cdr` file to the bot.
2. **Dimension/spec extraction:**
   - Photo → sent to Claude Haiku 4.5 to read printed dimension labels
     (e.g. "680 см", "80 см") off the image, since designers already
     annotate size this way before sending files to the workshop.
   - `.cdr` file → read the document/page canvas size directly from the
     file (no external app needed; CorelDraw is not installed on the
     server).
   - If the selected category is one of the volumetric-letter products,
     the same vision step also counts the letters in the design and reads
     the intended letter height.
   - **Fallback:** if extraction fails, is low-confidence, or the category
     doesn't need image-derived dimensions, the bot asks staff to type the
     size/count directly instead of guessing.
3. **Product selection:** bot shows a button menu of categories from
   `price_list.json`. Staff taps the right one (no attempt to guess
   product type from the image — confirmed in brainstorming, since e.g. a
   banner and an oracal print look identical as a flat image).
4. **Category-specific follow-ups:** any additional choice the category
   needs (e.g. which oracal grade, 1x vs 2x acrylic lightbox, standee
   variant) via buttons.
5. **Distance step** (for categories that need installation): staff either
   types the client's address/area (geocoded via Yandex Maps) **or**
   shares a Telegram location pin — whichever is easier for them. Bot
   computes driving distance from the fixed workshop origin
   (41.291234, 69.196435 — see `price_list.json` → `workshop_origin`) and
   automatically resolves the matching `install_travel_fee` bracket. No
   manual km-bracket selection.
6. **Bundle suggestion:** by default, the bot proposes the main product
   line **plus** a design-service hour and the installation/travel fee as
   one combined quote (per `bundle_defaults` in the price data). Staff can
   remove any line — e.g. drop the design hour if the client already has a
   ready design, or drop travel for a pickup/no-install order.
7. Bot replies with an itemized breakdown (line items + total), in the
   staff member's saved language.

## Language

One-time `/til` (Uzbek) / `/язык` (Russian) command sets the staff member's
language preference, stored per Telegram user ID. All subsequent bot
messages for that user render in the chosen language. No per-order
language prompt.

## Configuration / secrets

Provided by the user directly into server-side config (never typed into
chat), as environment variables:

- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `ANTHROPIC_API_KEY` — from console.anthropic.com (separate from any
  Claude.ai/Claude Code subscription — pay-per-token billing)
- `YANDEX_MAPS_API_KEY` — geocoding + distance
- Workshop origin coordinates are already committed in `price_list.json`
  (not a secret)

## Error handling

- Extraction failures (unreadable photo, unsupported/corrupt `.cdr`,
  low-confidence OCR) fall back to asking staff to type the value — the
  bot never silently guesses a dimension or letter count.
- Unrecognized/failed address geocoding falls back to asking staff to pick
  the nearest km bracket manually (same brackets as today's price list),
  rather than blocking the whole quote on a mapping failure.
- All Telegram, Anthropic API, and Yandex Maps errors are logged; the bot
  tells staff to retry rather than crashing silently, since this is a
  long-running polling service with no one watching a terminal.

## Testing approach

- Unit tests for the pricing computation per `pricing_type` (fixed,
  per_sqm, per_letter_by_height, distance_bracket, etc.) against known
  values from `price_list.json`, independent of Telegram/vision/maps.
- Manual end-to-end test against the real Telegram bot for each of: a
  photo-based per-sqm order, a `.cdr`-based order, a volumetric-letters
  order (letter counting), and a distance-based install fee — before
  calling v1 done.

## Open items to confirm during implementation

- Exact wording/labels in Uzbek for all price list items (PDF mixes
  Uzbek and Russian; bot needs consistent UZ strings for `/til` mode).
- NSSM vs. Task Scheduler for the Windows service — decide when actually
  deploying to the Schneider server.
