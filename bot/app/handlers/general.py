import os

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart

from ..api_client import api_client
from ..states.user_states import UserRegistration

router = Router()

# URL веб-приложения для Telegram WebApp (Mini App)
# ОБЯЗАТЕЛЬНО задай в .env переменную WEBAPP_URL, например:
# WEBAPP_URL=https://dev-cloud-ksa.ru
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip() or None


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

    # Кнопка открытия WebApp / Mini App (если задан WEBAPP_URL)
    if WEBAPP_URL:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🌐 Веб-кабинет",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
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

    Теперь регистрация делается через WebApp.
    В боте /start всегда показывает меню + кнопку WebApp.
    """
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)

    if user:
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

    # ✅ Новый пользователь: не запускаем FSM регистрацию в боте
    if WEBAPP_URL:
        await message.answer(
            "Привет! 👋\n"
            "Регистрация и заполнение профиля теперь делаются в WebApp.\n\n"
            "Нажмите кнопку ниже, чтобы открыть веб-кабинет:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🚀 Открыть WebApp",
                            web_app=WebAppInfo(url=WEBAPP_URL),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🌐 Веб-кабинет (в меню)",
                            callback_data="main:menu",
                        )
                    ],
                ]
            ),
        )
    else:
        await message.answer(
            "Привет! 👋\n"
            "WebApp не настроен (переменная WEBAPP_URL пустая).\n"
            "Сообщите администратору."
        )

    # Покажем базовое меню (роль неизвестна — как клиент)
    await message.answer(
        "Меню доступно ниже 👇",
        reply_markup=get_main_menu("client"),
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
