from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from app.api_client import api_client

router = Router()


def get_main_menu():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🚗 Мой гараж")],
            [KeyboardButton(text="📝 Создать заявку")],
        ],
        resize_keyboard=True
    )
    return kb


@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)

    if user is None:
        # пользователь не зарегистрирован → отправляем в регистрацию
        await message.answer(
            "Привет! 👋\nПохоже, вы здесь впервые.\n\n"
            "Давайте зарегистрируемся, это займёт одну минуту!"
        )
        await message.answer("Введите ваше имя:")
        await state.update_data(reg_step="name")
        return

    # пользователь есть → показываем меню
    await message.answer(
        f"Рады снова видеть, {user['name']}!",
        reply_markup=get_main_menu()
    )
