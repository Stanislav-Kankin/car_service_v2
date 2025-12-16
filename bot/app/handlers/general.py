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
from aiogram.filters.command import CommandObject

from ..api_client import api_client

router = Router()

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip() or None


def get_main_menu(role: str | None = None) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="main:profile"),
            InlineKeyboardButton(text="🚗 Мой гараж", callback_data="main:garage"),
        ],
        [InlineKeyboardButton(text="📝 Новая заявка", callback_data="main:new_request")],
        [InlineKeyboardButton(text="📨 Мои заявки", callback_data="main:my_requests")],
        [InlineKeyboardButton(text="🎁 Мои бонусы", callback_data="main:bonus")],
    ]

    if role in ("service_owner", "admin"):
        buttons.append([InlineKeyboardButton(text="🛠 Меню СТО", callback_data="main:sto_menu")])
    else:
        buttons.append([InlineKeyboardButton(text="🔧 Зарегистрировать СТО", callback_data="main:sto_register")])

    if WEBAPP_URL:
        buttons.append([InlineKeyboardButton(text="🌐 Веб-кабинет", web_app=WebAppInfo(url=WEBAPP_URL))])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    """
    Обычный /start — показывает WebApp кнопку.

    ВАЖНО:
    Если /start пришёл с payload (deep-link), мы тут НЕ отвечаем,
    чтобы его обработал chat.py (CommandStart(deep_link=True)).
    """
    await state.clear()

    payload = (command.args or "").strip()
    if payload:
        # ✅ не перехватываем deep-link, иначе получится то, что ты видел на скрине
        return

    if not WEBAPP_URL:
        await message.answer("WEBAPP_URL не настроен. Сообщите администратору.")
        return

    await message.answer(
        "Привет! 👋\n"
        "MyGarage работает через WebApp (Mini App).\n\n"
        "Нажмите кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚀 Открыть WebApp",
                        web_app=WebAppInfo(url=WEBAPP_URL),
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data == "main:menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    user = await api_client.get_user_by_telegram(callback.from_user.id)
    role: str | None = None
    if isinstance(user, dict):
        role = user.get("role")

    try:
        await callback.message.edit_text("Выберите действие из меню ниже 👇", reply_markup=get_main_menu(role))
    except Exception:
        await callback.message.answer("Выберите действие из меню ниже 👇", reply_markup=get_main_menu(role))

    await callback.answer()
