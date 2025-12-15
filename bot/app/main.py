import asyncio
import logging

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

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

from .handlers.general import router as general_router
from .handlers.chat import router as chat_router

logging.basicConfig(level=logging.INFO)

app = FastAPI()


class NotifyPayload(BaseModel):
    telegram_id: int
    text: str


@app.post("/notify")
async def notify(
    payload: NotifyPayload,
    x_api_token: str = Header(default=""),
):
    if x_api_token != config.BOT_API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await app.state.bot.send_message(payload.telegram_id, payload.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


async def main():
    bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)

    # FSM storage
    if HAS_REDIS and config.REDIS_URL:
        redis = Redis.from_url(config.REDIS_URL)
        storage = RedisStorage(redis=redis)
    else:
        storage = MemoryStorage()

    dp = Dispatcher(storage=storage)
    dp.include_router(general_router)
    dp.include_router(chat_router)

    app.state.bot = bot

    # Telegram button -> WebApp
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть MyGarage",
                web_app=WebAppInfo(url=config.WEBAPP_URL),
            )
        )
    except Exception:
        pass

    # параллельно: бот-поллинг + FastAPI notify
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
