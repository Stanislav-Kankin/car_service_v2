from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from ..api_client import api_client

router = Router()


@router.message(F.text == "👤 Профиль")
async def profile_show(message: Message):
    """Показать профиль пользователя.

    Пока без редактирования, просто читаем данные из backend.
    """
    user = await api_client.get_user_by_telegram(message.from_user.id)

    if not user:
        await message.answer("Вы ещё не зарегистрированы. Напишите /start")
        return

    full_name = user.get("full_name") or user.get("name") or "—"

    text = (
        "Ваш профиль:\n\n"
        f"Имя: {full_name}\n"
        f"Телефон: {user.get('phone', '—')}\n"
        f"Город: {user.get('city', '—')}\n\n"
        "Редактирование добавим чуть позже."
    )

    await message.answer(text)


@router.callback_query(F.data == "main:profile")
async def profile_show_from_menu(callback: CallbackQuery):
    """Обработчик нажатия на пункт "👤 Профиль" в главном инлайн-меню."""
    await profile_show(callback.message)
    await callback.answer()
