from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from ..api_client import api_client  # относительный импорт внутри bot.app

router = Router()


def get_main_menu():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🚗 Мой гараж")],
            [KeyboardButton(text="📝 Создать заявку")],
        ],
        resize_keyboard=True,
    )
    return kb


@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    """
    Обработка /start:
    - если пользователь не найден в backend → отправляем в регистрацию;
    - если найден → показываем главное меню.
    """
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

    # на всякий случай защищаемся, если backend вернул странный формат
    if not isinstance(user, dict):
        name = message.from_user.full_name or message.from_user.first_name or "друг"
    else:
        # пробуем взять имя из backend, если нет — из Telegram
        name = (
            user.get("name")
            or user.get("full_name")
            or (message.from_user.full_name if message.from_user else None)
            or "друг"
        )

    # пользователь есть → показываем меню
    await message.answer(
        f"Рады снова видеть, {name}!",
        reply_markup=get_main_menu(),
    )
