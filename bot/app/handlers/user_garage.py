from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from ..api_client import api_client

router = Router()


async def _send_garage(message: Message):
    """
    Общая логика показа гаража.

    Сейчас только чтение списка машин. Добавление/редактирование
    сделаем отдельными хэндлерами.
    """
    user = await api_client.get_user_by_telegram(message.chat.id)
    if not user:
        await message.answer(
            "Похоже, вы ещё не зарегистрированы.\n"
            "Нажмите /start, чтобы пройти простую регистрацию. 🙂"
        )
        return

    cars = await api_client.list_cars_by_user(user["id"])

    if not cars:
        await message.answer(
            "У вас пока нет добавленных автомобилей.\n"
            "Позже здесь появится возможность добавить и отредактировать машину.",
        )
        return

    lines = ["Ваш гараж:\n"]
    for idx, car in enumerate(cars, start=1):
        brand = car.get("brand") or "—"
        model = car.get("model") or "—"
        year = car.get("year") or "—"
        plate = car.get("license_plate") or "—"

        lines.append(
            f"{idx}. {brand} {model} ({year})\n"
            f"   Госномер: {plate}\n"
        )

    await message.answer("\n".join(lines))


@router.message(F.text == "🚗 Мой гараж")
async def garage_show_legacy(message: Message):
    """
    Старый вход по текстовой кнопке.
    Оставляем для совместимости со старыми клавиатурами.
    """
    await _send_garage(message)


@router.callback_query(F.data == "main:garage")
async def garage_show_from_menu(callback: CallbackQuery):
    """
    Обработчик нажатия на пункт "🚗 Мой гараж" в инлайн-меню.
    """
    await _send_garage(callback.message)
    await callback.answer()
