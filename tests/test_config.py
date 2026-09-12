import pytest
from alcana_bot.config import load_config, ConfigError

def test_load_config_success():
    env = {
        "TELEGRAM_BOT_TOKEN": "tg-token",
        "ANTHROPIC_API_KEY": "ant-key",
        "YANDEX_MAPS_API_KEY": "ya-key",
    }
    config = load_config(env)
    assert config.telegram_bot_token == "tg-token"
    assert config.anthropic_api_key == "ant-key"
    assert config.yandex_maps_api_key == "ya-key"

def test_load_config_missing_vars_lists_all_missing():
    env = {"TELEGRAM_BOT_TOKEN": "tg-token"}
    with pytest.raises(ConfigError) as exc_info:
        load_config(env)
    message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "YANDEX_MAPS_API_KEY" in message
