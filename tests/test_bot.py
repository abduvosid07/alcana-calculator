"""Handler-level tests for the conversation flow.

These use hand-rolled fakes for the Telegram objects rather than real
`telegram.Update` instances -- the handlers only touch a small, stable slice
of that API (effective_user/effective_chat/message/callback_query).
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcana_bot import bot as bot_module
from alcana_bot.bot import (
    AWAITING_BRACKET_CHOICE, AWAITING_BUNDLE_CHOICE, AWAITING_CATEGORY,
    AWAITING_CATEGORY_GROUP, AWAITING_FILE, AWAITING_TEXT_INPUT,
    build_application, handle_bracket_selected, handle_bracket_text_fallback,
    handle_bundle_choice, handle_category_group_selected, handle_category_selected,
    handle_text_input,
)
from alcana_bot.config import Config
from alcana_bot.price_data import Category, load_price_list

PRICE_LIST = load_price_list("data/price_list.json")


class FakeLangStore:
    def __init__(self, lang="ru"):
        self._lang = lang
    def get_language(self, user_id, default="uz"):
        return self._lang
    def set_language(self, user_id, lang):
        self._lang = lang


def make_context(user_data=None):
    return SimpleNamespace(user_data=user_data if user_data is not None else {})


def make_fake_message(message_id=1):
    """A message-like object supporting the same in-place edit chain bot.py uses."""
    msg = SimpleNamespace(message_id=message_id, reply_text=AsyncMock(), edit_text=AsyncMock())
    msg.edit_text.return_value = msg
    return msg


def make_callback_update(data):
    message = make_fake_message()
    query = SimpleNamespace(
        data=data,
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    return SimpleNamespace(
        callback_query=query,
        message=None,
        effective_user=SimpleNamespace(id=42),
        effective_chat=SimpleNamespace(id=1, send_message=AsyncMock(return_value=make_fake_message())),
    )


def make_text_update(text):
    return SimpleNamespace(
        callback_query=None,
        message=SimpleNamespace(text=text, reply_text=AsyncMock()),
        effective_user=SimpleNamespace(id=42),
        effective_chat=SimpleNamespace(id=1, send_message=AsyncMock(return_value=make_fake_message())),
    )


FAKE_CONFIG = Config(telegram_bot_token="1:AA", google_gemini_api_key="k", google_maps_api_key="y")


def _all_text(update):
    """Every string the handler sent, via any of the reply/edit channels."""
    calls = list(update.effective_chat.send_message.call_args_list)
    if update.message is not None:
        calls += list(update.message.reply_text.call_args_list)
    if update.callback_query is not None:
        calls += list(update.callback_query.message.reply_text.call_args_list)
        calls += list(update.callback_query.message.edit_text.call_args_list)
    return " ".join(str(c.args[0]) for c in calls if c.args)


def _select_group_and_category(context, group_id, category_id):
    context.user_data["category_group_id"] = group_id
    context.user_data["category_id"] = category_id


# --- Category grouping -------------------------------------------------------

def test_category_group_selection_shows_only_that_groups_categories():
    update = make_callback_update("grp:volumetric_letters")
    context = make_context()

    state = asyncio.run(handle_category_group_selected(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_CATEGORY
    assert context.user_data["category_group_id"] == "volumetric_letters"
    markup = update.callback_query.message.edit_text.call_args.kwargs["reply_markup"]
    callback_datas = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "cat:letters_acrylic_led" in callback_datas
    assert "cat:banner_300gr" not in callback_datas  # belongs to a different group
    assert "back" in callback_datas  # back button present


# --- Fix 1: piece count for fixed / fixed_options ---------------------------

def test_fixed_category_asks_for_piece_count_instead_of_pricing_immediately():
    update = make_callback_update("cat:rollup_200x80")
    context = make_context()
    _select_group_and_category(context, "lightbox_signage", None)
    state = asyncio.run(handle_category_selected(update, context, PRICE_LIST, FakeLangStore(), None))

    assert state == AWAITING_TEXT_INPUT
    assert context.user_data["pending_text_purpose"] == "piece_count"
    assert "main_item" not in context.user_data


def test_piece_count_input_scales_the_fixed_line_total():
    update = make_text_update("10")
    context = make_context()
    context.user_data.update({"category_id": "rollup_200x80", "pending_text_purpose": "piece_count"})

    state = asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))

    assert state == AWAITING_BUNDLE_CHOICE
    item = context.user_data["main_item"]
    assert item.quantity == 10
    assert item.total == 6500000


def test_piece_count_input_defaults_to_one_on_dash():
    update = make_text_update("-")
    context = make_context()
    context.user_data.update({"category_id": "rollup_200x80", "pending_text_purpose": "piece_count"})

    asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))
    assert context.user_data["main_item"].total == 650000


def test_piece_count_input_rejects_garbage_and_reprompts():
    update = make_text_update("abc")
    context = make_context()
    context.user_data.update({"category_id": "rollup_200x80", "pending_text_purpose": "piece_count"})

    state = asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))
    assert state == AWAITING_TEXT_INPUT
    assert "main_item" not in context.user_data
    assert "Сколько штук" in _all_text(update)


def test_piece_count_for_fixed_options_uses_the_chosen_option():
    update = make_text_update("3")
    context = make_context()
    context.user_data.update({"category_id": "standee", "option_index": 2, "pending_text_purpose": "piece_count"})

    asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))
    item = context.user_data["main_item"]
    assert item.unit_price == 1100000
    assert item.total == 3300000


# --- Fix 5: independent per-line bundle toggles -----------------------------

def _bundle_context(price_list=PRICE_LIST):
    context = make_context()
    context.user_data["main_item"] = MagicMock(total=100000)
    always = price_list.bundle_defaults.get("always_include", [])
    context.user_data["include_design"] = "design_service" in always
    context.user_data["include_travel"] = "install_travel_fee" in always
    return context


def test_bundle_toggles_default_from_bundle_defaults_always_include():
    context = _bundle_context()
    assert context.user_data["include_design"] is True
    assert context.user_data["include_travel"] is True


def test_toggling_design_off_keeps_travel_on():
    update = make_callback_update("bundle:toggle_design")
    context = _bundle_context()

    state = asyncio.run(handle_bundle_choice(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_BUNDLE_CHOICE
    assert context.user_data["include_design"] is False
    assert context.user_data["include_travel"] is True
    update.callback_query.message.edit_text.assert_awaited()


def test_confirm_with_design_off_and_travel_on_asks_for_address_without_design_line():
    context = _bundle_context()
    context.user_data["include_design"] = False

    state = asyncio.run(handle_bundle_choice(make_callback_update("bundle:confirm"), context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_TEXT_INPUT
    assert context.user_data["pending_text_purpose"] == "address"
    assert context.user_data["design_item"] is None


def test_confirm_with_design_on_asks_how_many_hours_before_pricing_it():
    """Fix 5: the design line must never be silently priced at a flat 1 hour."""
    context = _bundle_context()
    update = make_callback_update("bundle:confirm")

    state = asyncio.run(handle_bundle_choice(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_TEXT_INPUT
    assert context.user_data["pending_text_purpose"] == "design_hours"
    assert "design_item" not in context.user_data


def test_design_hours_input_scales_the_design_line_and_then_asks_for_address():
    context = _bundle_context()
    context.user_data["pending_text_purpose"] = "design_hours"
    update = make_text_update("2")

    state = asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))

    assert state == AWAITING_TEXT_INPUT
    assert context.user_data["pending_text_purpose"] == "address"
    design_item = context.user_data["design_item"]
    assert design_item.quantity == 2
    assert design_item.total == 300000  # 150 000 so'm/hour x 2


def test_design_hours_input_accepts_a_decimal_value():
    context = _bundle_context()
    context.user_data["pending_text_purpose"] = "design_hours"
    update = make_text_update("1.5")

    asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))
    assert context.user_data["design_item"].total == 225000


def test_design_hours_input_rejects_garbage_and_reprompts():
    context = _bundle_context()
    context.user_data["pending_text_purpose"] = "design_hours"
    update = make_text_update("abc")

    state = asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))
    assert state == AWAITING_TEXT_INPUT
    assert "design_item" not in context.user_data


def test_confirm_with_travel_off_keeps_design_and_skips_distance_step():
    context = _bundle_context()
    context.user_data["include_travel"] = False
    update = make_callback_update("bundle:confirm")

    state = asyncio.run(handle_bundle_choice(update, context, PRICE_LIST, FakeLangStore()))
    assert state == AWAITING_TEXT_INPUT
    assert context.user_data["pending_text_purpose"] == "design_hours"

    # Answer the hours prompt -- since travel is off, this should go straight
    # to the final quote instead of asking for an address.
    hours_update = make_text_update("1")
    state = asyncio.run(handle_text_input(hours_update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))

    assert state == AWAITING_FILE  # quote sent, no address asked
    assert context.user_data["design_item"] is not None
    # The quote lands on the still-tracked bundle-confirm message (edited in
    # place), not a new bubble from the text reply -- that's the point of `_show`.
    quote = _all_text(update)
    assert "Дизайн хизмати" in quote  # design line kept
    assert "Выезд на установку" not in quote  # travel line dropped


def test_confirm_with_both_off_sends_main_item_only():
    context = _bundle_context()
    context.user_data["include_design"] = False
    context.user_data["include_travel"] = False
    update = make_callback_update("bundle:confirm")

    state = asyncio.run(handle_bundle_choice(update, context, PRICE_LIST, FakeLangStore()))
    assert state == AWAITING_FILE
    assert context.user_data["design_item"] is None


# --- Fix 6: bracket picker on failed geocode --------------------------------

def test_failed_geocode_offers_a_bracket_keyboard_not_free_text(mocker):
    mocker.patch("alcana_bot.bot.geocode_address", side_effect=bot_module.DistanceError("bad address"))
    update = make_text_update("не существующий адрес")
    context = make_context()
    context.user_data.update({"category_id": "banner_300gr", "pending_text_purpose": "address", "main_item": MagicMock(total=1)})

    state = asyncio.run(handle_text_input(update, context, PRICE_LIST, FakeLangStore(), FAKE_CONFIG))

    assert state == AWAITING_BRACKET_CHOICE
    markup = update.effective_chat.send_message.call_args.kwargs["reply_markup"]
    buttons = [row[0] for row in markup.inline_keyboard]
    assert len(buttons) == len(PRICE_LIST.categories["install_travel_fee"].brackets) + 1  # + back button row
    assert buttons[1].text == "📍 10-20 км — 150 000 сум"
    assert buttons[1].callback_data == "bracket:1"


def test_selected_bracket_becomes_the_travel_line_of_the_quote():
    update = make_callback_update("bracket:1")
    context = make_context()
    context.user_data["main_item"] = MagicMock(total=100000)
    context.user_data["design_item"] = None

    state = asyncio.run(handle_bracket_selected(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_FILE
    quote = _all_text(update)
    assert "Выезд на установку (по расстоянию)" in quote
    assert "150 000" in quote


def test_typing_while_bracket_picker_is_shown_reshows_it_instead_of_dead_ending():
    update = make_text_update("не знаю")
    context = make_context()
    context.user_data["main_item"] = MagicMock(total=1)

    state = asyncio.run(handle_bracket_text_fallback(update, context, PRICE_LIST, FakeLangStore()))

    assert state == AWAITING_BRACKET_CHOICE
    assert update.effective_chat.send_message.call_args.kwargs["reply_markup"] is not None


# --- Fix 8c: unsupported pricing_type never falls through to `fixed` --------

def test_unsupported_pricing_type_reports_misconfiguration(caplog):
    broken = Category(id="broken", pricing_type="per_sqm ", unit="pc", price=999)
    price_list = SimpleNamespace(
        categories={**PRICE_LIST.categories, "broken": broken},
        bundle_defaults=PRICE_LIST.bundle_defaults,
        workshop_origin=PRICE_LIST.workshop_origin,
        category_groups=[],
    )
    update = make_callback_update("cat:broken")
    context = make_context()

    state = asyncio.run(handle_category_selected(update, context, price_list, FakeLangStore(), None))

    assert state == AWAITING_FILE
    assert "main_item" not in context.user_data  # crucially: NOT priced as fixed
    assert "некорректно" in _all_text(update)


# --- Fix 2: error handler registration --------------------------------------

# The conversation deliberately mixes message and callback-query handlers, so
# PTB's informational per_message warning is expected here.
@pytest.mark.filterwarnings("ignore::telegram.warnings.PTBUserWarning")
def test_build_application_registers_an_error_handler():
    application = build_application(FAKE_CONFIG, PRICE_LIST, FakeLangStore(), None, "soffice")
    assert application.error_handlers, "no application-level error handler registered"
