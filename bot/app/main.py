import asyncio
import logging

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

logging.basicConfig(level=logging.INFO)

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

    # ✅ ВАЖНО: deep-link /start chat_r.._s.. должен отрабатывать ПЕРВЫМ
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
                    text="Открыть MyGarage",
                    web_app=WebAppInfo(url=config.WEBAPP_URL),
                )
            )
    except Exception:
        pass

    await asyncio.gather(
        dp.start_polling(bot),
        _run_api(),
    )


async def _run_api():
    uv_config = uvicorn.Config(app, host="0.0.0.0", port=8086, log_level="info")
    server = uvicorn.Server(uv_config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
