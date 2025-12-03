import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import CommandStart, Command

from .config import config
from .api_client import APIClient


logging.basicConfig(level=logging.INFO)


class UserRegistration(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_city = State()


async def main() -> None:
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    api = APIClient()

    # ---------- Тестовый пинг, чтобы проверить, что бот вообще ловит команды ----------

    @dp.message(Command("ping"))
    async def cmd_ping(message: Message):
        await message.answer("pong 🏓")

    # ---------- /start ----------

    @dp.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext):
        """
        Старт: пытаемся найти пользователя по telegram_id.
        Если нашли — приветствуем и предлагаем /profile.
        Если нет — создаём и запускаем регистрацию.
        """
        tg_id = message.from_user.id
        logging.info("Получен /start от tg_id=%s", tg_id)

        # 1. Пытаемся найти пользователя по telegram_id
        try:
            user = await api.get_user_by_telegram(tg_id)
            name = user.get("full_name") or message.from_user.full_name or "друг"
            await message.answer(
                f"С возвращением, {name}!\n\n"
                "Используй /profile чтобы посмотреть профиль.\n"
                "Позже добавим гараж и создание заявок 🚗"
            )
            await state.clear()
            return
        except Exception as e:
            logging.warning("Пользователь не найден по telegram_id или ошибка: %s", e)

        # 2. Если не нашли — создаём черновик пользователя
        try:
            logging.info("Создаём пользователя с telegram_id=%s", tg_id)
            await api.create_user(tg_id)
        except Exception as e:
            logging.exception("Ошибка при создании пользователя: %s", e)
            await message.answer(
                "Произошла ошибка при создании профиля. "
                "Попробуйте позже, пожалуйста 🙏"
            )
            return

        # 3. Запускаем регистрацию профиля
        await message.answer(
            "Добро пожаловать в CarBot V2!\n"
            "Давай заполним короткий профиль.\n\n"
            "Как к тебе обращаются?"
        )
        await state.set_state(UserRegistration.waiting_full_name)

    # ---------- Регистрация: имя ----------

    @dp.message(UserRegistration.waiting_full_name)
    async def reg_full_name(message: Message, state: FSMContext):
        full_name = message.text.strip()
        await state.update_data(full_name=full_name)
        await message.answer("Отправь, пожалуйста, номер телефона:")
        await state.set_state(UserRegistration.waiting_phone)

    # ---------- Регистрация: телефон ----------

    @dp.message(UserRegistration.waiting_phone)
    async def reg_phone(message: Message, state: FSMContext):
        phone = message.text.strip()
        await state.update_data(phone=phone)
        await message.answer("Из какого ты города?")
        await state.set_state(UserRegistration.waiting_city)

    # ---------- Регистрация: город + сохранение в backend ----------

    @dp.message(UserRegistration.waiting_city)
    async def reg_city(message: Message, state: FSMContext):
        city = message.text.strip()
        tg_id = message.from_user.id
        data = await state.get_data()

        full_name = data.get("full_name")
        phone = data.get("phone")

        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]

            await api.update_user(
                user_id,
                {
                    "full_name": full_name,
                    "phone": phone,
                    "city": city,
                    "role": user.get("role") or "client",
                },
            )
        except Exception as e:
            logging.exception("Ошибка при сохранении профиля: %s", e)
            await message.answer(
                "Регистрация почти завершена, но произошла ошибка при сохранении "
                "профиля на сервере. Попробуйте позже или нажмите /profile для проверки."
            )
            await state.clear()
            return

        await message.answer(
            "Регистрация завершена!\n\n"
            f"Имя: {full_name}\n"
            f"Телефон: {phone}\n"
            f"Город: {city}\n\n"
            "Позже добавим гараж и создание заявок 🚗\n"
            "Посмотреть профиль: /profile"
        )
        await state.clear()

    # ---------- /profile ----------

    @dp.message(Command("profile"))
    @dp.message(F.text == "/profile")
    async def cmd_profile(message: Message):
        """
        Показывает профиль и бонусы пользователя.
        """
        tg_id = message.from_user.id
        logging.info("Запрошен /profile tg_id=%s", tg_id)

        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception as e:
            logging.exception("Ошибка при получении профиля: %s", e)
            await message.answer(
                "Профиль не найден или сервер недоступен.\n"
                "Нажми /start, чтобы пройти регистрацию ещё раз."
            )
            return

        text = (
            "Ваш профиль:\n\n"
            f"Имя: {user.get('full_name') or '—'}\n"
            f"Телефон: {user.get('phone') or '—'}\n"
            f"Город: {user.get('city') or '—'}\n"
            f"Роль: {user.get('role') or '—'}\n"
            f"Бонусы: {user.get('bonus_balance', 0)}"
        )
        await message.answer(text)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
