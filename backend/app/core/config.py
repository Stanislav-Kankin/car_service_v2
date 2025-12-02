import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "CarBot V2 Backend"

    # ---------------------- DB ----------------------
    DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

    if DB_TYPE == "postgres":
        DB_URL = os.getenv("DB_URL") or "postgresql+asyncpg://carbot:password@localhost/carbot_v2"
    else:
        DB_URL = os.getenv("SQLITE_DB_URL", "sqlite+aiosqlite:///./carbot_v2.db")

    # ---------------------- Redis ----------------------
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ---------------------- Other ----------------------
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"


settings = Settings()
