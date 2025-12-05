from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext

from ..api_client import api_client  # относительный импорт внутри bot.app

router = Router()


def get_main_menu() -> InlineKeyboardMarkup:
    """Инлайн-меню главного экрана.

    Здесь только кнопки. Логику по ролям (клиент / СТО / админ)
    можно потом донастроить в самих хэндлерах.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Профиль",
                    callback_data="main:profile",
                ),
                InlineKeyboardButton(
                    text="🚗 Мой гараж",
                    callback_data="main:garage",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📝 Новая заявка",
                    callback_data="main:new_request",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📨 Мои заявки",
                    callback_data="main:my_requests",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛠 Меню СТО",
                    callback_data="main:sto_menu",
                ),
            ],
        ]
    )


@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    """Старт:

    - очищаем FSM;
    - ищем пользователя в backend;
    - если нет — отправляем в регистрацию (через reg_step);
    - если есть — показываем главное меню.
    """
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)

    if user is None:
        # пользователь не зарегистрирован → отправляем в регистрацию
        await message.answer(
            "Привет! 👋\n"
            "Похоже, вы здесь впервые.\n\n"
            "Давайте зарегистрируемся, это займёт одну минуту!",
            reply_markup=ReplyKeyboardRemove(),  # на всякий случай убираем старые reply-клавиатуры
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
            user.get("full_name")
            or user.get("name")
            or (message.from_user.full_name if message.from_user else None)
            or "друг"
        )

    # пользователь есть → показываем инлайн-меню
    await message.answer(
        f"Рады снова видеть, {name}!\nВыберите действие из меню ниже 👇",
        reply_markup=get_main_menu(),
    )
