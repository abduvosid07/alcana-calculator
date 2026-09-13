# src/alcana_bot/bot.py
import asyncio
import logging
import os
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
)

from alcana_bot.config import Config
from alcana_bot.price_data import PriceList, Category
from alcana_bot.lang_store import LangStore
from alcana_bot.presentation import build_group_choices, build_category_choices, format_quote, format_cart_review
from alcana_bot.pricing import (
    price_fixed, price_fixed_options, price_per_sqm, price_per_sqm_options,
    price_per_letter_by_height, price_per_unit, resolve_distance_bracket, PricingError, LineItem,
)
from alcana_bot.bundle import assemble_bundle
from alcana_bot.vision import extract_dimensions_from_image, extract_letter_spec_from_image, ExtractionError
from alcana_bot.cdr import extract_cdr_dimensions, CdrExtractionError
from alcana_bot.distance import geocode_address, estimate_driving_km, DistanceError
from alcana_bot.i18n import t, LANGUAGE_PROMPT, LANGUAGE_BUTTONS

logger = logging.getLogger(__name__)

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

DEFAULT_LANG = "uz"

DESIGN_CATEGORY_ID = "design_service"
TRAVEL_CATEGORY_ID = "install_travel_fee"


def _lang(context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore, user_id: int) -> str:
    return lang_store.get_language(user_id)


def _back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(t("back_button", lang), callback_data="back")]])


async def _show(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Render a step, editing the tapped message in place for button-driven
    transitions instead of piling a new bubble on top of it.

    A reply that follows something staff just TYPED must always be a new
    message, never an edit of an older bot message -- Telegram does not move
    an edited message's position in the chat, so editing a prompt sent before
    the staff member's own text would make the bot's answer render above what
    they just typed (looks like the bot answered before they asked).
    """
    if update.callback_query is not None:
        try:
            return await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception:
            logger.debug("Could not edit the tapped message, sending a new one instead", exc_info=True)
    return await update.effective_chat.send_message(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def _show_language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton(label, callback_data=f"lang:{code}") for code, label in LANGUAGE_BUTTONS]]
    await _show(update, context, LANGUAGE_PROMPT, reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_LANGUAGE


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore) -> int:
    context.user_data.clear()
    return await _show_language_menu(update, context)


async def handle_language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1]
    lang_store.set_language(update.effective_user.id, lang)
    await _show(update, context, t("welcome", lang))
    return AWAITING_FILE


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore, lang: str) -> None:
    lang_store.set_language(update.effective_user.id, lang)
    await update.message.reply_text(t("language_set", lang))


async def _show_category_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang: str) -> int:
    choices = build_group_choices(price_list, lang)
    keyboard = [[InlineKeyboardButton(name, callback_data=f"grp:{group_id}")] for group_id, name in choices]
    keyboard.append([InlineKeyboardButton(t("back_button", lang), callback_data="back")])
    await _show(update, context, t("choose_category_group", lang), reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_CATEGORY_GROUP


async def _show_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang: str, group_id: str) -> int:
    context.user_data["category_group_id"] = group_id
    choices = build_category_choices(price_list, lang, group_id=group_id)
    keyboard = [[InlineKeyboardButton(name, callback_data=f"cat:{category_id}")] for category_id, name in choices]
    keyboard.append([InlineKeyboardButton(t("back_button", lang), callback_data="back")])
    await _show(update, context, t("choose_category", lang), reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_CATEGORY


async def _show_option_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str, category: Category) -> int:
    keyboard = [[InlineKeyboardButton(opt.get("label", str(i)), callback_data=f"opt:{i}")] for i, opt in enumerate(category.options)]
    keyboard.append([InlineKeyboardButton(t("back_button", lang), callback_data="back")])
    await _show(update, context, t("choose_option", lang), reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_OPTION


async def _show_bundle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    await _show(update, context, t("ask_bundle_confirmation", lang), reply_markup=_bundle_keyboard(context, lang))
    return AWAITING_BUNDLE_CHOICE


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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, vision_client) -> int:
    context.user_data.clear()
    lang = _lang(context, lang_store, update.effective_user.id)
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = bytes(await photo_file.download_as_bytearray())
    context.user_data["image_bytes"] = image_bytes
    context.user_data["media_type"] = "image/jpeg"

    try:
        # Synchronous SDK call -- off the event loop so one slow vision
        # request doesn't freeze the bot for every other staff member.
        result = await asyncio.to_thread(extract_dimensions_from_image, vision_client, image_bytes, "image/jpeg")
        context.user_data["extracted_dimensions"] = {"width_cm": result["width_cm"], "height_cm": result["height_cm"]}
    except ExtractionError as e:
        logger.info("Photo dimension extraction failed, will fall back to manual entry: %s", e)
        context.user_data["extracted_dimensions"] = None

    return await _show_category_group_menu(update, context, price_list, lang)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, soffice_path: str) -> int:
    context.user_data.clear()
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
                # soffice conversion can take up to 60s -- run it in a thread.
                width_cm, height_cm = await asyncio.to_thread(extract_cdr_dimensions, cdr_path, soffice_path)
                context.user_data["cdr_dimensions"] = (width_cm, height_cm)
            except CdrExtractionError as e:
                logger.info("CDR dimension extraction failed, will fall back to manual entry: %s", e)

    return await _show_category_group_menu(update, context, price_list, lang)


async def handle_category_group_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    group_id = query.data.split(":", 1)[1]
    return await _show_category_menu(update, context, price_list, lang, group_id)


async def handle_category_group_back(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    context.user_data.clear()
    await _show(update, context, t("welcome", lang))
    return AWAITING_FILE


async def _ask_piece_count(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    context.user_data["pending_text_purpose"] = "piece_count"
    await _show(update, context, t("enter_piece_count", lang), reply_markup=_back_keyboard(lang))
    return AWAITING_TEXT_INPUT


async def handle_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, vision_client) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    category_id = query.data.split(":", 1)[1]
    context.user_data["category_id"] = category_id
    category = price_list.categories[category_id]

    if category.pricing_type in ("fixed_options", "per_sqm_options"):
        return await _show_option_menu(update, context, lang, category)

    if category.pricing_type == "per_letter_by_height":
        image_bytes = context.user_data.get("image_bytes")
        if image_bytes:
            try:
                spec = await asyncio.to_thread(
                    extract_letter_spec_from_image, vision_client, image_bytes, context.user_data["media_type"]
                )
                item = price_per_letter_by_height(category, letter_count=spec["letter_count"], height_cm=spec["height_cm"])
                return await _finish_main_item(update, context, price_list, lang_store, item)
            except (ExtractionError, PricingError) as e:
                logger.info("Letter extraction/pricing failed, falling back to manual entry: %s", e)
        context.user_data["pending_text_purpose"] = "letters"
        await _show(update, context, t("enter_letter_spec", lang), reply_markup=_back_keyboard(lang))
        return AWAITING_TEXT_INPUT

    if category.pricing_type == "per_sqm":
        dims = context.user_data.get("extracted_dimensions") or context.user_data.get("cdr_dimensions")
        if dims:
            width_cm, height_cm = (dims["width_cm"], dims["height_cm"]) if isinstance(dims, dict) else dims
            item = price_per_sqm(category, width_cm, height_cm)
            return await _finish_main_item(update, context, price_list, lang_store, item)
        context.user_data["pending_text_purpose"] = "dimensions"
        await _show(update, context, t("enter_dimensions", lang), reply_markup=_back_keyboard(lang))
        return AWAITING_TEXT_INPUT

    if category.pricing_type in ("per_hour", "per_minute", "per_meter"):
        context.user_data["pending_text_purpose"] = "quantity"
        await _show(update, context, t("enter_quantity", lang), reply_markup=_back_keyboard(lang))
        return AWAITING_TEXT_INPUT

    if category.pricing_type == "fixed":
        # Flat per-piece price: ask how many pieces before computing, otherwise
        # an order for 10 roll-ups silently quotes as 1.
        return await _ask_piece_count(update, context, lang)

    # Unreachable while load_price_list validates pricing_type at startup;
    # kept as a second line of defense so a bad price list can never be
    # silently mispriced as `fixed`.
    logger.error("Category '%s' has unsupported pricing_type '%s'", category.id, category.pricing_type)
    await _show(update, context, t("category_misconfigured", lang))
    return AWAITING_FILE


async def handle_category_back(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    return await _show_category_group_menu(update, context, price_list, lang)


async def handle_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    option_index = int(query.data.split(":", 1)[1])
    context.user_data["option_index"] = option_index
    category = price_list.categories[context.user_data["category_id"]]

    if category.pricing_type == "fixed_options":
        return await _ask_piece_count(update, context, lang)

    # per_sqm_options: still needs dimensions
    dims = context.user_data.get("extracted_dimensions") or context.user_data.get("cdr_dimensions")
    if dims:
        width_cm, height_cm = (dims["width_cm"], dims["height_cm"]) if isinstance(dims, dict) else dims
        item = price_per_sqm_options(category, option_index, width_cm, height_cm)
        return await _finish_main_item(update, context, price_list, lang_store, item)

    context.user_data["pending_text_purpose"] = "dimensions"
    await _show(update, context, t("enter_dimensions", lang), reply_markup=_back_keyboard(lang))
    return AWAITING_TEXT_INPUT


async def handle_option_back(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    group_id = context.user_data.get("category_group_id")
    return await _show_category_menu(update, context, price_list, lang, group_id)


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, config: Config) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    purpose = context.user_data.get("pending_text_purpose")
    category_id = context.user_data.get("category_id")
    category = price_list.categories[category_id] if category_id else None
    text = update.message.text.strip()

    try:
        if purpose == "dimensions":
            width_str, height_str = text.lower().replace(" ", "").split("x")
            if category.pricing_type == "per_sqm_options":
                item = price_per_sqm_options(category, context.user_data["option_index"], float(width_str), float(height_str))
            else:
                item = price_per_sqm(category, float(width_str), float(height_str))
            return await _finish_main_item(update, context, price_list, lang_store, item)

        if purpose == "piece_count":
            quantity = 1 if text in ("", "-") else int(text)
            if category.pricing_type == "fixed_options":
                item = price_fixed_options(category, context.user_data["option_index"], quantity=quantity)
            else:
                item = price_fixed(category, quantity=quantity)
            return await _finish_main_item(update, context, price_list, lang_store, item)

        if purpose == "letters":
            count_str, height_str = [p.strip() for p in text.split(",")]
            item = price_per_letter_by_height(category, letter_count=int(count_str), height_cm=float(height_str))
            return await _finish_main_item(update, context, price_list, lang_store, item)

        if purpose == "quantity":
            item = price_per_unit(category, quantity=float(text))
            return await _finish_main_item(update, context, price_list, lang_store, item)

        if purpose == "design_hours":
            hours = float(text.replace(",", "."))
            if hours <= 0:
                raise ValueError("hours must be positive")
            design_category = price_list.categories[DESIGN_CATEGORY_ID]
            context.user_data["design_item"] = price_per_unit(design_category, quantity=hours)
            return await _proceed_after_design(update, context, price_list, lang_store, lang)

        if purpose == "address":
            try:
                # Synchronous HTTP call -- keep it off the event loop.
                lat, lon = await asyncio.to_thread(geocode_address, text, config.google_maps_api_key)
            except DistanceError as e:
                # Spec: a failed geocode falls back to picking the nearest km
                # bracket manually, not to free-text guessing.
                logger.info("Geocoding failed, offering manual bracket picker: %s", e)
                return await _offer_bracket_picker(update, context, price_list, lang)
            return await _finish_distance_step(update, context, price_list, lang_store, (lat, lon))

        if purpose == "manual_travel_fee":
            manual_price = int(text.replace(" ", ""))
            travel_category = price_list.categories[TRAVEL_CATEGORY_ID]
            travel_item = LineItem(label=travel_category.id, detail="вручную / qo'lda", unit_price=manual_price, quantity=1, total=manual_price)
            return await _send_final_quote(update, context, price_list, lang_store, travel_item)
    except (ValueError, KeyError, PricingError, DistanceError) as e:
        logger.info("Could not parse/compute from text input (purpose=%s): %s", purpose, e)
        prompt_key = {
            "dimensions": "enter_dimensions",
            "piece_count": "enter_piece_count",
            "letters": "enter_letter_spec",
            "quantity": "enter_quantity",
            "design_hours": "enter_design_hours",
            "address": "ask_address_or_location",
            "manual_travel_fee": "enter_travel_fee_manually",
        }.get(purpose, "extraction_failed_fallback")
        await _show(update, context, t(prompt_key, lang), reply_markup=_back_keyboard(lang))
        return AWAITING_TEXT_INPUT


async def handle_text_input_back(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    purpose = context.user_data.get("pending_text_purpose")

    if purpose in ("design_hours", "address"):
        return await _show_bundle_menu(update, context, lang)
    if purpose == "manual_travel_fee":
        return await _offer_bracket_picker(update, context, price_list, lang)

    category_id = context.user_data.get("category_id")
    category = price_list.categories.get(category_id) if category_id else None
    if category is not None and category.pricing_type in ("fixed_options", "per_sqm_options") and "option_index" in context.user_data:
        return await _show_option_menu(update, context, lang, category)

    group_id = context.user_data.get("category_group_id")
    return await _show_category_menu(update, context, price_list, lang, group_id)


async def handle_location_shared(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    location = update.message.location
    return await _finish_distance_step(update, context, price_list, lang_store, (location.latitude, location.longitude))


def _bundle_keyboard(context: ContextTypes.DEFAULT_TYPE, lang: str) -> InlineKeyboardMarkup:
    design_key = "bundle_design_included" if context.user_data.get("include_design") else "bundle_design_excluded"
    travel_key = "bundle_travel_included" if context.user_data.get("include_travel") else "bundle_travel_excluded"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(design_key, lang), callback_data="bundle:toggle_design")],
        [InlineKeyboardButton(t(travel_key, lang), callback_data="bundle:toggle_travel")],
        [InlineKeyboardButton(t("bundle_confirm", lang), callback_data="bundle:confirm")],
        [InlineKeyboardButton(t("back_button", lang), callback_data="back")],
    ])


async def _finish_main_item(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, item) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    context.user_data.setdefault("cart", []).append(item)
    # Clear fields specific to the product just finished -- without this,
    # adding a second product via "add another" (no new photo) would silently
    # reuse the FIRST product's extracted dimensions instead of asking fresh.
    for key in ("extracted_dimensions", "cdr_dimensions", "image_bytes", "media_type", "category_id", "option_index"):
        context.user_data.pop(key, None)
    return await _show_cart_review(update, context, price_list, lang)


async def handle_bundle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    action = query.data.split(":", 1)[1]

    if action in ("toggle_design", "toggle_travel"):
        key = "include_design" if action == "toggle_design" else "include_travel"
        context.user_data[key] = not context.user_data.get(key, False)
        return await _show_bundle_menu(update, context, lang)

    # action == "confirm"
    if context.user_data.get("include_design"):
        context.user_data["pending_text_purpose"] = "design_hours"
        await _show(update, context, t("enter_design_hours", lang), reply_markup=_back_keyboard(lang))
        return AWAITING_TEXT_INPUT

    context.user_data["design_item"] = None
    return await _proceed_after_design(update, context, price_list, lang_store, lang)


async def _proceed_after_design(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, lang: str) -> int:
    if not context.user_data.get("include_travel"):
        return await _send_final_quote(update, context, price_list, lang_store, travel_item=None)

    context.user_data["pending_text_purpose"] = "address"
    await _show(update, context, t("ask_address_or_location", lang), reply_markup=_back_keyboard(lang))
    return AWAITING_TEXT_INPUT


async def handle_bundle_back(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    category_id = context.user_data.get("category_id")
    category = price_list.categories.get(category_id) if category_id else None
    if category is not None and category.pricing_type in ("fixed_options", "per_sqm_options"):
        return await _show_option_menu(update, context, lang, category)
    group_id = context.user_data.get("category_group_id")
    return await _show_category_menu(update, context, price_list, lang, group_id)


async def _offer_bracket_picker(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang: str) -> int:
    """Let staff pick the km bracket directly when the address can't be geocoded."""
    travel_category = price_list.categories[TRAVEL_CATEGORY_ID]
    brackets = travel_category.brackets or []
    if not brackets:
        # No brackets to choose from -- fall back to typing the amount.
        context.user_data["pending_text_purpose"] = "manual_travel_fee"
        await _show(update, context, t("enter_travel_fee_manually", lang), reply_markup=_back_keyboard(lang))
        return AWAITING_TEXT_INPUT

    keyboard = [
        [InlineKeyboardButton(
            t("travel_bracket_button", lang,
              min_km=bracket["min_km"], max_km=bracket["max_km"],
              price=f"{bracket['price']:,}".replace(",", " ")),
            callback_data=f"bracket:{index}",
        )]
        for index, bracket in enumerate(brackets)
    ]
    keyboard.append([InlineKeyboardButton(t("back_button", lang), callback_data="back")])
    context.user_data["pending_text_purpose"] = None
    await _show(update, context, t("choose_travel_bracket", lang), reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_BRACKET_CHOICE


async def handle_bracket_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    travel_category = price_list.categories[TRAVEL_CATEGORY_ID]
    brackets = travel_category.brackets or []
    index = int(query.data.split(":", 1)[1])

    if index >= len(brackets):
        logger.error("Travel bracket index %s out of range (%s brackets)", index, len(brackets))
        context.user_data["pending_text_purpose"] = "manual_travel_fee"
        await _show(update, context, t("enter_travel_fee_manually", lang), reply_markup=_back_keyboard(lang))
        return AWAITING_TEXT_INPUT

    bracket = brackets[index]
    travel_item = LineItem(
        label=travel_category.id,
        detail=f"{bracket['min_km']}-{bracket['max_km']} км",
        unit_price=bracket["price"],
        quantity=1,
        total=bracket["price"],
    )
    return await _send_final_quote(update, context, price_list, lang_store, travel_item)


async def handle_bracket_back(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    query = update.callback_query
    await query.answer()
    lang = _lang(context, lang_store, update.effective_user.id)
    return await _show_bundle_menu(update, context, lang)


async def handle_bracket_text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore) -> int:
    """Staff typed something while the bracket keyboard was showing -- re-show it.

    Without this the picker would be a dead end for anyone who types instead of
    tapping (the whole point of issue 6 was removing dead ends).
    """
    lang = _lang(context, lang_store, update.effective_user.id)
    return await _offer_bracket_picker(update, context, price_list, lang)


async def _send_final_quote(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, travel_item) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    items = assemble_bundle(context.user_data["main_item"], context.user_data.get("design_item"), travel_item)
    await _show(update, context, format_quote(items, lang, price_list))
    return AWAITING_FILE


async def _finish_distance_step(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, destination: tuple) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    origin = (price_list.workshop_origin["latitude"], price_list.workshop_origin["longitude"])
    distance_km = estimate_driving_km(origin, destination)
    travel_category = price_list.categories[TRAVEL_CATEGORY_ID]

    try:
        travel_item = resolve_distance_bracket(travel_category, distance_km)
    except PricingError as e:
        # Distance computed fine but exceeds every bracket -- a bracket picker
        # wouldn't help, so ask for the amount, with an explicit prompt.
        # Never silently drop the travel fee (Global Constraint).
        logger.info("Distance bracket resolution failed, falling back to manual entry: %s", e)
        context.user_data["pending_text_purpose"] = "manual_travel_fee"
        await _show(update, context, t("enter_travel_fee_manually", lang), reply_markup=_back_keyboard(lang))
        return AWAITING_TEXT_INPUT

    return await _send_final_quote(update, context, price_list, lang_store, travel_item)


def build_application(config: Config, price_list: PriceList, lang_store: LangStore, vision_client, soffice_path: str) -> Application:
    application = Application.builder().token(config.telegram_bot_token).build()

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Catch-all so an unexpected exception never leaves staff without a reply."""
        logger.error("Unhandled exception: %s", context.error, exc_info=context.error)
        chat = getattr(update, "effective_chat", None) if isinstance(update, Update) else None
        if chat is None:
            return
        lang = DEFAULT_LANG
        user = getattr(update, "effective_user", None)
        if user is not None:
            try:
                lang = lang_store.get_language(user.id)
            except Exception:  # pragma: no cover - lang lookup must never mask the real error
                logger.warning("Could not resolve language for user during error handling", exc_info=True)
        try:
            await chat.send_message(t("unexpected_error", lang))
        except Exception:  # pragma: no cover - nothing further we can do
            logger.exception("Failed to send error notice to chat %s", chat.id)

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", lambda u, c: start(u, c, lang_store)),
            MessageHandler(filters.PHOTO, lambda u, c: handle_photo(u, c, price_list, lang_store, vision_client)),
            MessageHandler(filters.Document.ALL, lambda u, c: handle_document(u, c, price_list, lang_store, soffice_path)),
        ],
        states={
            AWAITING_LANGUAGE: [
                CallbackQueryHandler(lambda u, c: handle_language_selected(u, c, lang_store), pattern=r"^lang:"),
            ],
            AWAITING_FILE: [
                MessageHandler(filters.PHOTO, lambda u, c: handle_photo(u, c, price_list, lang_store, vision_client)),
                MessageHandler(filters.Document.ALL, lambda u, c: handle_document(u, c, price_list, lang_store, soffice_path)),
            ],
            AWAITING_CATEGORY_GROUP: [
                CallbackQueryHandler(lambda u, c: handle_category_group_selected(u, c, price_list, lang_store), pattern=r"^grp:"),
                CallbackQueryHandler(lambda u, c: handle_category_group_back(u, c, lang_store), pattern=r"^back$"),
            ],
            AWAITING_CATEGORY: [
                CallbackQueryHandler(lambda u, c: handle_category_selected(u, c, price_list, lang_store, vision_client), pattern=r"^cat:"),
                CallbackQueryHandler(lambda u, c: handle_category_back(u, c, price_list, lang_store), pattern=r"^back$"),
            ],
            AWAITING_OPTION: [
                CallbackQueryHandler(lambda u, c: handle_option_selected(u, c, price_list, lang_store), pattern=r"^opt:"),
                CallbackQueryHandler(lambda u, c: handle_option_back(u, c, price_list, lang_store), pattern=r"^back$"),
            ],
            AWAITING_TEXT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: handle_text_input(u, c, price_list, lang_store, config)),
                MessageHandler(filters.LOCATION, lambda u, c: handle_location_shared(u, c, price_list, lang_store)),
                CallbackQueryHandler(lambda u, c: handle_text_input_back(u, c, price_list, lang_store), pattern=r"^back$"),
            ],
            AWAITING_BUNDLE_CHOICE: [
                CallbackQueryHandler(lambda u, c: handle_bundle_choice(u, c, price_list, lang_store), pattern=r"^bundle:"),
                CallbackQueryHandler(lambda u, c: handle_bundle_back(u, c, price_list, lang_store), pattern=r"^back$"),
            ],
            AWAITING_BRACKET_CHOICE: [
                CallbackQueryHandler(lambda u, c: handle_bracket_selected(u, c, price_list, lang_store), pattern=r"^bracket:"),
                CallbackQueryHandler(lambda u, c: handle_bracket_back(u, c, price_list, lang_store), pattern=r"^back$"),
                # Escape hatches: a shared location still resolves the fee
                # automatically, and typed text re-shows the picker.
                MessageHandler(filters.LOCATION, lambda u, c: handle_location_shared(u, c, price_list, lang_store)),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: handle_bracket_text_fallback(u, c, price_list, lang_store)),
            ],
        },
        fallbacks=[CommandHandler("start", lambda u, c: start(u, c, lang_store))],
    )

    application.add_handler(conversation)
    application.add_handler(CommandHandler("til", lambda u, c: set_language(u, c, lang_store, "uz")))
    application.add_handler(CommandHandler("ru", lambda u, c: set_language(u, c, lang_store, "ru")))
    application.add_error_handler(error_handler)

    return application
