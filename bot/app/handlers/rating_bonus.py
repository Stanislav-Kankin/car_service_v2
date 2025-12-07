from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from ..api_client import api_client

router = Router()


def kb_bonus_menu() -> InlineKeyboardMarkup:
    """
    Одна кнопка «В меню» под разделом бонусов.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="main:menu",
                )
            ]
        ]
    )


@router.callback_query(F.data == "main:bonus")
async def bonus_main(callback: CallbackQuery):
    """
    Раздел «🎁 Мои бонусы»:

    - ищем пользователя по telegram_id;
    - получаем баланс и историю транзакций;
    - показываем короткий список (до 10 последних).
    """
    tg_id = callback.from_user.id

    user = await api_client.get_user_by_telegram(tg_id)
    if not user:
        await callback.message.answer(
            "Похоже, вы ещё не зарегистрированы.\n"
            "Нажмите /start, чтобы пройти короткую регистрацию.",
        )
        await callback.answer()
        return

    # user может быть dict или объект, поэтому аккуратно
    if isinstance(user, dict):
        user_id = user.get("id")
    else:
        user_id = getattr(user, "id", None)

    if not user_id:
        await callback.message.answer(
            "Не удалось определить пользователя. Попробуйте позже.",
        )
        await callback.answer()
        return

    # --- баланс ---
    try:
        balance = await api_client.get_bonus_balance(user_id)
    except Exception:
        balance = None

    # --- история ---
    try:
        history = await api_client.get_bonus_history(user_id)
    except Exception:
        history = []

    lines: list[str] = ["<b>🎁 Мои бонусы</b>", ""]

    if balance is not None:
        lines.append(f"<b>Текущий баланс:</b> {balance} бонусов")
    else:
        lines.append("Не удалось получить текущий баланс бонусов.")

    if history:
        lines.append("")
        lines.append("<b>Последние операции:</b>")
        lines.append("")

        # Ограничимся 10 последними
        for tx in history[:10]:
            amount = tx.get("amount", 0)
            reason = tx.get("reason") or tx.get("description") or "Без описания"
            created_at = tx.get("created_at") or ""

            sign = "➕" if amount >= 0 else "➖"
            line = f"{sign} {amount} — {reason}"
            if created_at:
                # если дата в формате '2025-12-01T12:34:56', возьмём только день
                line += f" ({created_at[:10]})"

            lines.append(line)
    else:
        lines.append("")
        lines.append("У вас пока нет бонусных операций.")

    text = "\n".join(lines)

    # Стараемся редактировать последнее сообщение
    try:
        await callback.message.edit_text(
            text,
            reply_markup=kb_bonus_menu(),
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=kb_bonus_menu(),
        )

    await callback.answer()
