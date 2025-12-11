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

    # ---------------------- Admins ----------------------
    # TELEGRAM_ADMIN_IDS="123456,987654"
    TELEGRAM_ADMIN_IDS: list[int] = []

    raw_admin_ids = os.getenv("TELEGRAM_ADMIN_IDS", "")
    if raw_admin_ids:
        parts = (
            raw_admin_ids.replace(";", ",").split(",")
        )  # допускаем разделение и запятой, и точкой с запятой
        for part in parts:
            part = part.strip()
            if not part:
                continue
            try:
                TELEGRAM_ADMIN_IDS.append(int(part))
            except ValueError:
                # Просто игнорируем кривой id, чтобы не падать
                continue


settings = Settings()
