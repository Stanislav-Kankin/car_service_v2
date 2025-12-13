import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo

try:
    # Опциональный Redis (если установлен и есть REDIS_URL)
    from aiogram.fsm.storage.redis import RedisStorage, Redis  # type: ignore

    HAS_REDIS = True
except ImportError:  # redis не установлен
    RedisStorage = None  # type: ignore
    Redis = None  # type: ignore
    HAS_REDIS = False

# ⚠️ ВАЖНО: используем ОТНОСИТЕЛЬНЫЕ импорты внутри пакета bot.app
from .config import config

from .handlers.general import router as general_router
from .handlers.user_registration import router as user_registration_router
from .handlers.user_profile import router as user_profile_router
from .handlers.user_garage import router as user_garage_router
from .handlers.requests_create import router as requests_create_router
from .handlers.requests_view import router as requests_view_router
from .handlers.sto_registration import router as sto_registration_router
from .handlers.sto_offers import router as sto_offers_router
# from .handlers.chat import router as chat_router
from .handlers.rating_bonus import router as rating_bonus_router
# from .handlers.admin import router as admin_router


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def get_storage():
    """
    Выбираем хранилище для FSM:
    - если есть REDIS_URL и установлен redis — используем RedisStorage,
    - иначе MemoryStorage.
    """
    redis_url = os.getenv("REDIS_URL")

    if redis_url and HAS_REDIS:
        try:
            redis = Redis.from_url(redis_url)
            logging.info("Используем RedisStorage для FSM: %s", redis_url)
            return RedisStorage(redis=redis)
        except Exception as e:
            logging.warning(
                "Не удалось подключиться к Redis (%s), fallback на MemoryStorage: %s",
                redis_url,
                e,
            )

    logging.info("Используем MemoryStorage для FSM")
    return MemoryStorage()


# -------------------------
# Notify API (backend -> bot)
# -------------------------

class NotifyPayload(BaseModel):
    recipient_type: str  # "client" | "service_center" (пока для логов)
    telegram_id: int
    message: str
    buttons: list[dict[str, str]] | None = None
    extra: dict | None = None


def build_notify_app(bot: Bot) -> FastAPI:
    app = FastAPI(title="CarBot Bot-Notify API")
    token = os.getenv("BOT_API_TOKEN", "")

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/api/v1/notify")
    async def notify(payload: NotifyPayload, authorization: str | None = Header(default=None)):
        # Простая защита токеном (если задан BOT_API_TOKEN)
        if token:
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Unauthorized")
            if authorization.split(" ", 1)[1] != token:
                raise HTTPException(status_code=403, detail="Forbidden")

        kb = None
        if payload.buttons:
            rows = []
            for b in payload.buttons:
                text = (b.get("text") or "").strip()
                url = (b.get("url") or "").strip()
                if text and url:
                    rows.append([InlineKeyboardButton(text=text, url=url)])
            if rows:
                kb = InlineKeyboardMarkup(inline_keyboard=rows)

        await bot.send_message(chat_id=payload.telegram_id, text=payload.message, reply_markup=kb)
        return {"ok": True}

    return app


async def run_notify_api(bot: Bot) -> None:
    """
    Запускает FastAPI сервер внутри процесса бота.
    """
    host = os.getenv("BOT_API_HOST", "127.0.0.1")
    port = int(os.getenv("BOT_API_PORT", "8086"))

    app = build_notify_app(bot)
    config_uv = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config_uv)
    logging.info("Notify API запущен: http://%s:%s", host, port)
    await server.serve()


async def setup_menu_button(bot: Bot) -> None:
    """
    Кнопка 'Open' / меню снизу как в BotFather (делается через Bot API).
    Работает в Telegram клиентах, где поддерживается MenuButtonWebApp.
    """
    webapp_url = os.getenv("WEBAPP_URL") or getattr(config, "WEBAPP_URL", None) or ""
    if not webapp_url:
        logging.info("WEBAPP_URL не задан — кнопку меню не ставим")
        return

    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть MeGarage",
                web_app=WebAppInfo(url=webapp_url),
            )
        )
        logging.info("Menu Button установлен: %s", webapp_url)
    except Exception as e:
        logging.warning("Не удалось установить Menu Button: %s", e)


async def main() -> None:
    setup_logging()

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    storage = get_storage()
    dp = Dispatcher(storage=storage)

    # Роутеры
    dp.include_router(user_registration_router)
    dp.include_router(sto_registration_router)
    dp.include_router(user_profile_router)
    dp.include_router(user_garage_router)
    dp.include_router(requests_create_router)
    dp.include_router(requests_view_router)
    dp.include_router(sto_offers_router)
    # dp.include_router(chat_router)
    dp.include_router(rating_bonus_router)
    # dp.include_router(admin_router)
    dp.include_router(general_router)

    # Кнопка WebApp в меню (опционально, но удобно)
    await setup_menu_button(bot)

    # Notify API (backend -> bot) параллельно с polling
    asyncio.create_task(run_notify_api(bot))

    logging.info("Бот запущен. Ожидаем обновления...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
