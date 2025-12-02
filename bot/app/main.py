import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

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

    @dp.message(F.text == "/start")
    async def cmd_start(message: Message, state: FSMContext):
        tg_id = message.from_user.id

        # пробуем найти юзера по telegram_id
        try:
            user = await api.get_user_by_telegram(tg_id)
            name = user.get("full_name") or message.from_user.full_name or "друг"
            await message.answer(f"С возвращением, {name}!")
            return
        except Exception:
            # если не нашли — идём по ветке регистрации
            pass

        await api.create_user(tg_id)
        await message.answer(
            "Добро пожаловать в CarBot V2!\n"
            "Давай заполним короткий профиль.\n\n"
            "Как к тебе обращаться?"
        )
        await state.set_state(UserRegistration.waiting_full_name)

    @dp.message(UserRegistration.waiting_full_name)
    async def reg_full_name(message: Message, state: FSMContext):
        full_name = message.text.strip()
        await state.update_data(full_name=full_name)
        await message.answer("Отправь, пожалуйста, номер телефона:")
        await state.set_state(UserRegistration.waiting_phone)

    @dp.message(UserRegistration.waiting_phone)
    async def reg_phone(message: Message, state: FSMContext):
        phone = message.text.strip()
        await state.update_data(phone=phone)
        await message.answer("Из какого ты города?")
        await state.set_state(UserRegistration.waiting_city)

    @dp.message(UserRegistration.waiting_city)
    async def reg_city(message: Message, state: FSMContext):
        city = message.text.strip()
        data = await state.get_data()

        # TODO: здесь сделаем PATCH /api/v1/users/{id}
        await message.answer(
            "Регистрация завершена!\n\n"
            f"Имя: {data.get('full_name')}\n"
            f"Телефон: {data.get('phone')}\n"
            f"Город: {city}\n\n"
            "Позже добавим гараж и создание заявок 🚗"
        )
        await state.clear()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
