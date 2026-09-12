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
