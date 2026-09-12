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
