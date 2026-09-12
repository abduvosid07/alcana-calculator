from dataclasses import dataclass

REQUIRED_VARS = ["TELEGRAM_BOT_TOKEN", "GOOGLE_GEMINI_API_KEY", "GOOGLE_MAPS_API_KEY"]

class ConfigError(Exception):
    pass

@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    google_gemini_api_key: str
    google_maps_api_key: str

def load_config(env: dict) -> Config:
    missing = [name for name in REQUIRED_VARS if not env.get(name)]
    if missing:
        raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")
    return Config(
        telegram_bot_token=env["TELEGRAM_BOT_TOKEN"],
        google_gemini_api_key=env["GOOGLE_GEMINI_API_KEY"],
        google_maps_api_key=env["GOOGLE_MAPS_API_KEY"],
    )
