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


    # ---------------------- Auth (Standalone App) ----------------------
    # Вход по телефону + одноразовый код (OTP)
    OTP_TTL_SECONDS: int = int(os.getenv("OTP_TTL_SECONDS", "300"))  # 5 минут
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    OTP_RESEND_COOLDOWN_SECONDS: int = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "30"))

    # Сессии (server-side) — срок жизни (по умолчанию 30 дней)
    AUTH_SESSION_TTL_SECONDS: int = int(os.getenv("AUTH_SESSION_TTL_SECONDS", "2592000"))

    # Cookie, в которой хранится session token
    AUTH_COOKIE_NAME: str = os.getenv("AUTH_COOKIE_NAME", "session_id")
    AUTH_COOKIE_DOMAIN: str = os.getenv("AUTH_COOKIE_DOMAIN", ".dev-cloud-ksa.ru")
    AUTH_COOKIE_SAMESITE: str = os.getenv("AUTH_COOKIE_SAMESITE", "none")  # none|lax|strict
    # Secure по умолчанию включён. В локальной разработке можно выключить через AUTH_COOKIE_SECURE=0
    AUTH_COOKIE_SECURE: bool = _env_bool("AUTH_COOKIE_SECURE", True)



    # Режим авторизации:
    # - telegram: только Telegram WebApp auth
    # - app: только standalone (email/пароль, OTP и т.п.)
    # - mixed: оба режима (по умолчанию)
    AUTH_MODE: str = os.getenv("AUTH_MODE", "mixed").strip().lower()

    # Пароли (email+password)
    PASSWORD_HASH_ITERATIONS: int = int(os.getenv("PASSWORD_HASH_ITERATIONS", "200000"))
    PASSWORD_MIN_LENGTH: int = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))

    # DEV: для тестов можно вернуть код в ответе (только если DEBUG=true или DEV_SMS_RETURN_CODE=true)
    DEV_SMS_RETURN_CODE: bool = _env_bool("DEV_SMS_RETURN_CODE", False)
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
