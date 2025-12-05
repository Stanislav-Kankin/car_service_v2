from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from ..api_client import api_client

router = Router()


def get_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать профиль",
                    callback_data="profile:edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="main:menu",
                ),
            ],
        ]
    )


async def _send_profile(message: Message):
    """
    Общая логика показа профиля (из message / callback).
    """
    user = await api_client.get_user_by_telegram(message.from_user.id)

    if not user:
        await message.answer(
            "Похоже, вы ещё не зарегистрированы.\n"
            "Нажмите /start, чтобы пройти короткую регистрацию.",
        )
        return

    # user приходит как dict с backend-а
    if isinstance(user, dict):
        full_name = user.get("full_name") or "—"
        phone = user.get("phone") or "—"
        city = user.get("city") or "—"
        role = user.get("role") or "client"
        bonus = user.get("bonus_balance")
    else:
        # На всякий случай, если вернётся модель
        full_name = getattr(user, "full_name", None) or "—"
        phone = getattr(user, "phone", None) or "—"
        city = getattr(user, "city", None) or "—"
        role = getattr(user, "role", None) or "client"
        bonus = getattr(user, "bonus_balance", None)

    role_names = {
        "client": "Клиент",
        "service_owner": "Владелец СТО",
        "admin": "Администратор",
    }
    role_text = role_names.get(str(role), "Клиент")

    lines = [
        "<b>👤 Профиль</b>",
        "",
        f"<b>Имя:</b> {full_name}",
        f"<b>Телефон:</b> {phone}",
        f"<b>Город:</b> {city}",
        f"<b>Роль:</b> {role_text}",
    ]

    if bonus is not None:
        lines.append(f"<b>Бонусы:</b> {bonus}")

    text = "\n".join(lines)

    await message.answer(
        text,
        reply_markup=get_profile_keyboard(),
    )


# --- входы в профиль ---


@router.message(F.text == "👤 Профиль")
async def profile_show_legacy(message: Message):
    """
    Старый вариант входа по текстовой кнопке.

    Оставляем на всякий случай, если у кого-то ещё висит старая reply-клава.
    """
    await _send_profile(message)


@router.callback_query(F.data == "main:profile")
async def profile_show_from_menu(callback: CallbackQuery):
    """
    Вход из главного инлайн-меню.
    """
    await _send_profile(callback.message)
    await callback.answer()


@router.callback_query(F.data == "profile:edit")
async def profile_edit_stub(callback: CallbackQuery):
    """
    Заглушка для редактирования профиля.
    Реальную логику добавим позже.
    """
    await callback.answer()
    await callback.message.answer(
        "Редактирование профиля скоро будет доступно 🤓\n"
        "Пока вы можете изменить данные через поддержку или повторную регистрацию.",
    )
