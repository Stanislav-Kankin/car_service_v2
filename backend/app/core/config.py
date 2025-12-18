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

    # ---------------------- Bonus / Cashback flags ----------------------
    @staticmethod
    def _env_bool(name: str, default: bool = False) -> bool:
        val = os.getenv(name)
        if val is None:
            return default
        return str(val).strip().lower() in ("1", "true", "yes", "y", "on")

    # ВРЕМЕННО: скрываем бонусы/кэшбек (по умолчанию включено)
    BONUS_HIDDEN_MODE: bool = _env_bool("BONUS_HIDDEN_MODE", True)

    # Если позже понадобится вернуть бонус за регистрацию — просто выключите BONUS_HIDDEN_MODE
    REGISTRATION_BONUS: int = int(os.getenv("REGISTRATION_BONUS", "500"))

    # ---------------------- Other ----------------------
    WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").strip()
    BOT_API_URL = os.getenv("BOT_API_URL", "").strip()

    # ---------------------- Admin ----------------------
    # Админы определяются через env TELEGRAM_ADMIN_IDS="123,456"
    TELEGRAM_ADMIN_IDS_RAW = os.getenv("TELEGRAM_ADMIN_IDS", "").strip()
    TELEGRAM_ADMIN_IDS: list[int] = []

    if TELEGRAM_ADMIN_IDS_RAW:
        raw_admin_ids = TELEGRAM_ADMIN_IDS_RAW
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
    DEBUG: bool = os.getenv("DEBUG", "false").strip().lower() in ("1", "true", "yes", "y", "on")


settings = Settings()
