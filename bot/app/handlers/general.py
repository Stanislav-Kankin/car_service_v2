from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart

from ..api_client import api_client
from ..states.user_states import UserRegistration

router = Router()


# ---------------------------------------------------------------------------
# Главное меню
# ---------------------------------------------------------------------------


def get_main_menu(role: str | None = None) -> InlineKeyboardMarkup:
    """
    Инлайн-меню главного экрана.

    role:
      - "client"        -> только клиентские пункты + кнопка регистрации СТО
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
        [
            InlineKeyboardButton(
                text="🎁 Мои бонусы",
                callback_data="main:bonus",
            ),
        ],
    ]

    # Для владельцев СТО / админов — меню СТО
    if role in ("service_owner", "admin"):
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🛠 Меню СТО",
                    callback_data="main:sto_menu",
                ),
            ]
        )
    else:
        # Для обычных клиентов — кнопка регистрации сервиса
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔧 Зарегистрировать СТО",
                    callback_data="main:sto_register",
                ),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    Точка входа.

    Если пользователь уже есть в backend:
      - приветствуем по имени,
      - показываем главное меню в зависимости от роли.

    Если нет — запускаем FSM регистрации UserRegistration.
    """
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)

    if user:
        # Уже зарегистрирован
        full_name = None
        role = None

        if isinstance(user, dict):
            full_name = user.get("full_name") or user.get("name")
            role = user.get("role")

        if not full_name:
            full_name = message.from_user.full_name

        await message.answer(f"Рады снова видеть, {full_name}!")
        await message.answer(
            "Выберите действие из меню ниже 👇",
            reply_markup=get_main_menu(role),
        )
        return

    # Пользователь не найден — запускаем регистрацию
    await state.set_state(UserRegistration.waiting_full_name)

    await message.answer(
        "Привет! 👋\n"
        "Похоже, вы здесь впервые.\n\n"
        "Давайте зарегистрируемся, это займёт одну минуту.\n\n"
        "Введите ваше имя / ФИО:",
    )


# ---------------------------------------------------------------------------
# Кнопка «В меню» из любых сценариев
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "main:menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    """
    Универсальный возврат в главное меню из любой точки.
    """
    await state.clear()

    user = await api_client.get_user_by_telegram(callback.from_user.id)
    role: str | None = None
    if isinstance(user, dict):
        role = user.get("role")

    # Чтобы не плодить сообщения — редактируем текст последнего
    try:
        await callback.message.edit_text(
            "Выберите действие из меню ниже 👇",
            reply_markup=get_main_menu(role),
        )
    except Exception:
        # Если сообщение уже не отредактировать (например, старое),
        # просто отправляем новое.
        await callback.message.answer(
            "Выберите действие из меню ниже 👇",
            reply_markup=get_main_menu(role),
        )

    await callback.answer()
