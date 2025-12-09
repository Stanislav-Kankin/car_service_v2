from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Настройки WebApp.

    Важно:
    - читаем общий .env из корня проекта
    - НЕ ругаемся на лишние поля (bot_token и т.п.)
    - если в .env есть backend_url=..., используем его как BASE_URL backend'а
    """

    # Конфиг Pydantic Settings (v2)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # <-- ключевой момент: игнорируем лишние переменные
    )

    # URL backend'а: берём либо из backend_url в .env, либо дефолт
    BACKEND_API_URL: AnyHttpUrl | str = Field(
        default="http://127.0.0.1:8044",
        alias="backend_url",  # .env: backend_url=http://...
    )

    # Режим отладки WebApp
    DEBUG: bool = False


settings = Settings()
