import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

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
# from .handlers.rating_bonus import router as rating_bonus_router
# from .handlers.admin import router as admin_router


def setup_logging() -> None:
    """
    Базовая настройка логирования.
    """
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


async def main() -> None:
    """
    Точка входа в бота:
    - создаём Bot и Dispatcher,
    - подключаем роутеры,
    - запускаем polling.
    """
    setup_logging()

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    storage = get_storage()
    dp = Dispatcher(storage=storage)

    # Подключаем роутеры по слоям/доменам
    dp.include_router(user_registration_router)
    dp.include_router(sto_registration_router)
    dp.include_router(user_profile_router)
    dp.include_router(user_garage_router)
    dp.include_router(requests_create_router)
    dp.include_router(requests_view_router)
    dp.include_router(sto_offers_router)
    # dp.include_router(chat_router)
    # dp.include_router(rating_bonus_router)
    # dp.include_router(admin_router)
    dp.include_router(general_router)

    logging.info("Бот запущен. Ожидаем обновления...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
