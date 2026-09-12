import logging
import os
from dotenv import load_dotenv
from anthropic import Anthropic

from alcana_bot.config import load_config
from alcana_bot.price_data import load_price_list
from alcana_bot.lang_store import LangStore
from alcana_bot.bot import build_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

def main():
    load_dotenv()
    config = load_config(os.environ)
    price_list = load_price_list("data/price_list.json")
    lang_store = LangStore("data/user_lang.json")
    anthropic_client = Anthropic(api_key=config.anthropic_api_key)
    soffice_path = os.environ.get("SOFFICE_PATH", "soffice")

    application = build_application(config, price_list, lang_store, anthropic_client, soffice_path)
    application.run_polling()

if __name__ == "__main__":
    main()
