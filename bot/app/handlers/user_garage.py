from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from ..api_client import api_client

router = Router()


@router.message(F.text == "🚗 Мой гараж")
async def garage_show(message: Message):
    """Простой просмотр гаража пользователя.

    Пока только список машин. Добавление/редактирование сделаем отдельными шагами.
    """
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Вы ещё не зарегистрированы. Напишите /start")
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


@router.callback_query(F.data == "main:garage")
async def garage_show_from_menu(callback: CallbackQuery):
    """Обработчик нажатия на пункт "🚗 Мой гараж" в инлайн-меню."""
    await garage_show(callback.message)
    await callback.answer()
