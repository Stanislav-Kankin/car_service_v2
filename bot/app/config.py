import os
from dotenv import load_dotenv

load_dotenv()


class BotConfig:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://127.0.0.1:8040")


config = BotConfig()
