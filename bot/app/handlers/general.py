from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext

from ..api_client import api_client

router = Router()


def get_main_menu(role: str | None = None) -> InlineKeyboardMarkup:
    """
    Инлайн-меню главного экрана.

    role:
      - "client"        -> только клиентские пункты
      - "service_owner" -> добавляем меню СТО
      - "admin"         -> можно будет добавить отдельные пункты
    """
    buttons: list[list[InlineKeyboardButton]] = [
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
    ]

    # Кнопка "Меню СТО" только для владельцев сервисов и админов
    if role in ("service_owner", "admin"):
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🛠 Меню СТО",
                    callback_data="main:sto_menu",
                ),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    """
    Старт:

    - очищаем FSM;
    - ищем пользователя в backend;
    - если нет — запускаем сценарий регистрации (FSM UserRegistration);
    - если есть — убираем старую reply-клаву и показываем главное инлайн-меню.
    """
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)

    if user is None:
        from ..states.user_states import UserRegistration  # локальный импорт, чтобы избежать циклов

        await state.set_state(UserRegistration.waiting_full_name)

        await message.answer(
            "Привет! 👋\n"
            "Похоже, вы здесь впервые.\n\n"
            "Давайте зарегистрируемся, это займёт одну минуту!",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer("Введите ваше имя:")
        return

    # Пользователь найден — определяем имя и роль для меню
    role: str | None = None
    if isinstance(user, dict):
        role = user.get("role")
        name = (
            user.get("full_name")
            or user.get("name")
            or (message.from_user.full_name if message.from_user else None)
            or "друг"
        )
    else:
        name = message.from_user.full_name or message.from_user.first_name or "друг"

    await message.answer(
        f"Рады снова видеть, {name}!",
        reply_markup=ReplyKeyboardRemove(),
    )

    await message.answer(
        "Выберите действие из меню ниже 👇",
        reply_markup=get_main_menu(role),
    )


@router.callback_query(F.data == "main:menu")
async def main_menu_callback(callback: CallbackQuery, state: FSMContext):
    """
    Универсальный возврат в главное меню из любой точки.
    """
    await state.clear()
    user = await api_client.get_user_by_telegram(callback.from_user.id)

    role: str | None = None
    if isinstance(user, dict):
        role = user.get("role")

    await callback.message.edit_text(
        "Выберите действие из меню ниже 👇",
        reply_markup=get_main_menu(role),
    )
    await callback.answer()
