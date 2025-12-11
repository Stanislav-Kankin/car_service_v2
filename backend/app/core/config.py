import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "CarBot V2 Backend"

    # ---------------------- Telegram ----------------------
    # ВАЖНО: тот же токен, что использует бот.
    # Берётся из переменной окружения BOT_TOKEN.
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    if not BOT_TOKEN:
        # Явно падаем при старте, чтобы не отлавливать
        # потом непонятные 403 Invalid hash.
        raise RuntimeError(
            "BOT_TOKEN is not set. "
            "Добавь BOT_TOKEN в .env (тот же токен, что у бота)."
        )

    # ---------------------- DB ----------------------
    DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

    if DB_TYPE == "postgres":
        DB_URL = (
            os.getenv("DB_URL")
            or "postgresql+asyncpg://carbot:password@localhost/carbot_v2"
        )
    else:
        DB_URL = os.getenv(
            "SQLITE_DB_URL",
            "sqlite+aiosqlite:///./carbot_v2.db",
        )

    # ---------------------- Redis ----------------------
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ---------------------- Other ----------------------
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"


settings = Settings()
