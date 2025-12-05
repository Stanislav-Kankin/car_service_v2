from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from ..api_client import api_client

router = Router()


async def _send_profile(message: Message):
    """
    Общая логика показа профиля (чтобы использовать и из message, и из callback).
    """
    user = await api_client.get_user_by_telegram(message.from_user.id)

    if not user:
        await message.answer(
            "Похоже, вы ещё не зарегистрированы.\n"
            "Нажмите /start, чтобы пройти простую регистрацию. 🙂"
        )
        return

    full_name = user.get("full_name") or user.get("name") or "—"
    phone = user.get("phone", "—")
    city = user.get("city", "—")

    text = (
        "Ваш профиль:\n\n"
        f"Имя: {full_name}\n"
        f"Телефон: {phone}\n"
        f"Город: {city}\n\n"
        "Редактирование профиля добавим немного позже."
    )

    await message.answer(text)


@router.message(F.text == "👤 Профиль")
async def profile_show_legacy(message: Message):
    """
    Старый вариант входа по текстовой кнопке.

    Оставляем на всякий случай, вдруг у кого-то ещё висит старая reply-клава.
    Постепенно уйдём только на инлайн.
    """
    await _send_profile(message)


@router.callback_query(F.data == "main:profile")
async def profile_show_from_menu(callback: CallbackQuery):
    """
    Обработчик нажатия на пункт "👤 Профиль" в главном инлайн-меню.
    """
    await _send_profile(callback.message)
    await callback.answer()
