from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Настройки WebApp.

    Важно:
    - читаем общий .env из корня проекта (локально)
    - НЕ ругаемся на лишние поля
    - в docker читаем из ENV переменных контейнера
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BACKEND_API_URL: AnyHttpUrl | str = Field(
        default="http://127.0.0.1:8044",
        alias="backend_url",
    )

    DEBUG: bool = False

    # ✅ НОВОЕ: allowlist админов из env
    TELEGRAM_ADMIN_IDS: str = ""


settings = Settings()