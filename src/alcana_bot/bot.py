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
    price_per_letter_by_height, price_per_unit, resolve_distance_bracket, PricingError, LineItem,
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

        if purpose == "manual_travel_fee":
            manual_price = int(text.replace(" ", ""))
            travel_category = price_list.categories["install_travel_fee"]
            travel_item = LineItem(label=travel_category.id, detail="вручную / qo'lda", unit_price=manual_price, quantity=1, total=manual_price)
            return await _send_final_quote(update, context, lang_store, travel_item)
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


async def _send_final_quote(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_store: LangStore, travel_item) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    items = assemble_bundle(context.user_data["main_item"], context.user_data.get("design_item"), travel_item)
    await update.effective_chat.send_message(format_quote(items, lang))
    return AWAITING_FILE


async def _finish_distance_step(update: Update, context: ContextTypes.DEFAULT_TYPE, price_list: PriceList, lang_store: LangStore, destination: tuple) -> int:
    lang = _lang(context, lang_store, update.effective_user.id)
    origin = (price_list.workshop_origin["latitude"], price_list.workshop_origin["longitude"])
    distance_km = estimate_driving_km(origin, destination)
    travel_category = price_list.categories["install_travel_fee"]

    try:
        travel_item = resolve_distance_bracket(travel_category, distance_km)
    except PricingError as e:
        # Never silently drop the travel fee (Global Constraint) -- ask staff
        # to type it manually instead of guessing or omitting it.
        logger.info("Distance bracket resolution failed, falling back to manual entry: %s", e)
        context.user_data["pending_text_purpose"] = "manual_travel_fee"
        await update.effective_chat.send_message(t("extraction_failed_fallback", lang))
        return AWAITING_TEXT_INPUT

    return await _send_final_quote(update, context, lang_store, travel_item)


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
