from dataclasses import dataclass

REQUIRED_VARS = ["TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "YANDEX_MAPS_API_KEY"]

class ConfigError(Exception):
    pass

@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    anthropic_api_key: str
    yandex_maps_api_key: str

def load_config(env: dict) -> Config:
    missing = [name for name in REQUIRED_VARS if not env.get(name)]
    if missing:
        raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")
    return Config(
        telegram_bot_token=env["TELEGRAM_BOT_TOKEN"],
        anthropic_api_key=env["ANTHROPIC_API_KEY"],
        yandex_maps_api_key=env["YANDEX_MAPS_API_KEY"],
    )
