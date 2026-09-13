class I18nError(Exception):
    pass

# Shown before a language is known yet, so it isn't language-specific.
LANGUAGE_PROMPT = "🌐 Tilni tanlang / Выберите язык:"
LANGUAGE_BUTTONS = [("uz", "🇺🇿 O'zbekcha"), ("ru", "🇷🇺 Русский")]

TRANSLATIONS = {
    "welcome": {
        "uz": "👋 Salom! Buyurtma narxini hisoblash uchun rasm yoki .cdr fayl yuboring.",
        "ru": "👋 Здравствуйте! Отправьте фото или .cdr файл, чтобы рассчитать цену заказа.",
    },
    "language_set": {
        "uz": "✅ Til o'zbek tiliga o'rnatildi.",
        "ru": "✅ Язык установлен на русский.",
    },
    "back_button": {
        "uz": "⬅️ Orqaga",
        "ru": "⬅️ Назад",
    },
    "choose_category_group": {
        "uz": "📂 Bo'limni tanlang:",
        "ru": "📂 Выберите раздел:",
    },
    "choose_category": {
        "uz": "🧩 Mahsulotni tanlang:",
        "ru": "🧩 Выберите товар:",
    },
    "choose_option": {
        "uz": "🔘 Variantni tanlang:",
        "ru": "🔘 Выберите вариант:",
    },
    "enter_dimensions": {
        "uz": "📏 O'lchamlarni avtomatik aniqlab bo'lmadi. Kenglik va balandlikni sm da kiriting (masalan: 200x150):",
        "ru": "📏 Не удалось определить размеры автоматически. Введите ширину и высоту в см (например: 200x150):",
    },
    "enter_quantity": {
        "uz": "🔢 Miqdorni kiriting (masalan: soat, metr yoki daqiqa soni):",
        "ru": "🔢 Введите количество (например: часы, метры или минуты):",
    },
    "enter_letter_spec": {
        "uz": "🔤 Harflar sonini va balandligini (sm) avtomatik aniqlab bo'lmadi. Iltimos, sonini va balandligini kiriting (masalan: 6, 80):",
        "ru": "🔤 Не удалось определить количество и высоту букв автоматически. Введите количество и высоту в см (например: 6, 80):",
    },
    "enter_design_hours": {
        "uz": "🎨 Dizaynga necha soat sarfladingiz? Sonini kiriting (masalan: 2 yoki 1.5):",
        "ru": "🎨 Сколько часов вы потратили на дизайн? Введите число (например: 2 или 1.5):",
    },
    "ask_address_or_location": {
        "uz": "📍 Mijoz manzilini yozing yoki Telegram orqali joylashuvni yuboring:",
        "ru": "📍 Напишите адрес клиента или отправьте геолокацию через Telegram:",
    },
    "enter_piece_count": {
        "uz": "📦 Nechta dona kerak? Sonini kiriting (bitta dona uchun 1 deb yozing):",
        "ru": "📦 Сколько штук? Введите количество (для одной штуки напишите 1):",
    },
    "ask_bundle_confirmation": {
        "uz": "🧺 Taklifga nimalar kirsin? Kerakmaganini bosib o'chiring, so'ng tasdiqlang:",
        "ru": "🧺 Что включить в предложение? Нажмите, чтобы убрать ненужное, затем подтвердите:",
    },
    "bundle_design_included": {
        "uz": "🎨 Dizayn: ✅ qo'shilgan",
        "ru": "🎨 Дизайн: ✅ включено",
    },
    "bundle_design_excluded": {
        "uz": "🎨 Dizayn: ❌ olib tashlandi",
        "ru": "🎨 Дизайн: ❌ убрано",
    },
    "bundle_travel_included": {
        "uz": "🚚 Montaj/yo'l: ✅ qo'shilgan",
        "ru": "🚚 Монтаж/выезд: ✅ включено",
    },
    "bundle_travel_excluded": {
        "uz": "🚚 Montaj/yo'l: ❌ olib tashlandi",
        "ru": "🚚 Монтаж/выезд: ❌ убрано",
    },
    "bundle_confirm": {
        "uz": "✅ Tasdiqlash",
        "ru": "✅ Подтвердить",
    },
    "choose_travel_bracket": {
        "uz": "🗺 Manzilni aniqlab bo'lmadi. Eng yaqin masofa oralig'ini tanlang:",
        "ru": "🗺 Не удалось определить адрес. Выберите ближайший интервал расстояния:",
    },
    "travel_bracket_button": {
        "uz": "📍 {min_km}-{max_km} km — {price} so'm",
        "ru": "📍 {min_km}-{max_km} км — {price} сум",
    },
    "enter_travel_fee_manually": {
        "uz": "✍️ Chiqish (montaj) narxini qo'lda kiriting, so'mda (faqat raqam):",
        "ru": "✍️ Введите стоимость выезда вручную, в сумах (только число):",
    },
    "category_misconfigured": {
        "uz": "⚠️ Bu mahsulot narxlar ro'yxatida to'g'ri sozlanmagan. Iltimos, botni boshqaruvchi mutaxassisga murojaat qiling.",
        "ru": "⚠️ Этот товар настроен в прайс-листе некорректно. Пожалуйста, сообщите специалисту, который обслуживает бота.",
    },
    "unexpected_error": {
        "uz": "⚠️ Kutilmagan xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring yoki /start bosing.",
        "ru": "⚠️ Произошла непредвиденная ошибка. Пожалуйста, попробуйте ещё раз или нажмите /start.",
    },
    "quote_header": {
        "uz": "🧾 <b>Hisob-kitob</b>",
        "ru": "🧾 <b>Смета</b>",
    },
    "quote_line_item": {
        "uz": "{bullet} <b>{label}</b>\n    {detail} — {total} so'm",
        "ru": "{bullet} <b>{label}</b>\n    {detail} — {total} сум",
    },
    "quote_total": {
        "uz": "💰 <b>Jami: {total} so'm</b>",
        "ru": "💰 <b>Итого: {total} сум</b>",
    },
    "extraction_failed_fallback": {
        "uz": "⚠️ Avtomatik aniqlash muvaffaqiyatsiz tugadi, iltimos qo'lda kiriting.",
        "ru": "⚠️ Автоматическое распознавание не удалось, пожалуйста, введите вручную.",
    },
}

def t(key: str, lang: str, **kwargs) -> str:
    if key not in TRANSLATIONS:
        raise I18nError(f"unknown translation key: '{key}'")
    entry = TRANSLATIONS[key]
    if lang not in entry:
        raise I18nError(f"unknown language '{lang}' for key '{key}'")
    return entry[lang].format(**kwargs) if kwargs else entry[lang]
