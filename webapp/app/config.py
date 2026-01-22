from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    TELEGRAM_ADMIN_IDS: str = ""

    # ✅ BONUS HIDDEN MODE
    BONUS_HIDDEN_MODE: bool = True

    # auth mode: app|telegram|mixed
    AUTH_MODE: str = "mixed"

    # Android TWA (Trusted Web Activity)
    # Package name of the Android app shell
    TWA_ANDROID_PACKAGE: str = ""
    # Comma-separated SHA256 certificate fingerprints (AA:BB:...)
    TWA_SHA256_CERT_FINGERPRINTS: str = ""


settings = Settings()
