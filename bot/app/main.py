import asyncio
import os
import logging
import logging.config
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import MenuButtonWebApp, WebAppInfo

try:
    from aiogram.fsm.storage.redis import RedisStorage, Redis  # type: ignore

    HAS_REDIS = True
except ImportError:
    RedisStorage = None  # type: ignore
    Redis = None  # type: ignore
    HAS_REDIS = False

from .config import config
from .handlers.chat import router as chat_router
from .handlers.general import router as general_router
from .notify_api import build_notify_app  # ✅ ВАЖНО


def setup_logging(service_name: str) -> dict:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "/app/logs")
    log_to_file = os.getenv("LOG_TO_FILE", "1").lower() in ("1", "true", "yes", "on")
    max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10 MB
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "10"))

    Path(log_dir).mkdir(parents=True, exist_ok=True)

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": log_level,
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    }

    root_handlers = ["console"]

    if log_to_file:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": log_level,
            "formatter": "default",
            "filename": str(Path(log_dir) / f"{service_name}.log"),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        handlers["file_error"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "default",
            "filename": str(Path(log_dir) / f"{service_name}.error.log"),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        root_handlers.extend(["file", "file_error"])

    cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s"}
        },
        "handlers": handlers,
        "root": {"level": log_level, "handlers": root_handlers},
        "loggers": {
            "uvicorn": {"level": log_level, "handlers": root_handlers, "propagate": False},
            "uvicorn.error": {"level": log_level, "handlers": root_handlers, "propagate": False},
            "uvicorn.access": {"level": log_level, "handlers": ["console"], "propagate": False},

            "aiogram": {"level": log_level, "handlers": root_handlers, "propagate": False},
        },
    }

    logging.config.dictConfig(cfg)
    return cfg


LOG_CONFIG = setup_logging("bot")

# ✅ Это будет приложение notify API (/api/v1/notify, /health)
app: FastAPI = FastAPI()


async def main():
    bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)

    # FSM storage
    if HAS_REDIS and config.REDIS_URL:
        redis = Redis.from_url(config.REDIS_URL)
        storage = RedisStorage(redis=redis)
    else:
        storage = MemoryStorage()

    dp = Dispatcher(storage=storage)

    # ✅ ВАЖНО: deep-link /start chat_r._s. должен отрабатывать ПЕРВЫМ
    dp.include_router(chat_router)
    dp.include_router(general_router)

    # ✅ Встраиваем notify API, чтобы backend мог слать /api/v1/notify
    notify_app = build_notify_app(bot)
    app.mount("/", notify_app)

    # Telegram button -> WebApp
    try:
        if config.WEBAPP_URL:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="MyGarage",
                    web_app=WebAppInfo(url=config.WEBAPP_URL),
                )
            )
    except Exception:
        logging.getLogger(__name__).exception("Failed to set chat menu button")

    await asyncio.gather(
        dp.start_polling(bot),
        _run_api(),
    )


async def _run_api():
    uv_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8086,
        log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
        log_config=LOG_CONFIG,  # ✅ чтобы uvicorn.access тоже шёл в файл
    )
    server = uvicorn.Server(uv_config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
