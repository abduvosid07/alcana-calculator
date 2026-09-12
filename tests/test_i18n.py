import pytest
from alcana_bot.i18n import t, I18nError, TRANSLATIONS

def test_t_returns_uz_and_ru():
    assert t("welcome", "uz") != t("welcome", "ru")
    assert isinstance(t("welcome", "uz"), str)

def test_t_formats_placeholders():
    message = t("quote_total", "ru", total="150 000")
    assert "150 000" in message

def test_t_unknown_key_raises():
    with pytest.raises(I18nError, match="unknown"):
        t("this_key_does_not_exist", "uz")

def test_t_unknown_lang_raises():
    with pytest.raises(I18nError, match="language"):
        t("welcome", "fr")

def test_every_key_has_both_languages():
    for key, entry in TRANSLATIONS.items():
        assert set(entry) == {"uz", "ru"}, f"key '{key}' is missing a language"
        assert all(value.strip() for value in entry.values()), f"key '{key}' has an empty string"

def test_travel_bracket_button_formats_placeholders():
    message = t("travel_bracket_button", "ru", min_km=10, max_km=20, price="150 000")
    assert "10-20" in message
    assert "150 000" in message
