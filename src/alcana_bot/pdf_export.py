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
