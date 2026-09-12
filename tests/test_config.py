import pytest
from alcana_bot.config import load_config, ConfigError

def test_load_config_success():
    env = {
        "TELEGRAM_BOT_TOKEN": "tg-token",
        "GOOGLE_GEMINI_API_KEY": "gem-key",
        "GOOGLE_MAPS_API_KEY": "maps-key",
    }
    config = load_config(env)
    assert config.telegram_bot_token == "tg-token"
    assert config.google_gemini_api_key == "gem-key"
    assert config.google_maps_api_key == "maps-key"

def test_load_config_missing_vars_lists_all_missing():
    env = {"TELEGRAM_BOT_TOKEN": "tg-token"}
    with pytest.raises(ConfigError) as exc_info:
        load_config(env)
    message = str(exc_info.value)
    assert "GOOGLE_GEMINI_API_KEY" in message
    assert "GOOGLE_MAPS_API_KEY" in message
