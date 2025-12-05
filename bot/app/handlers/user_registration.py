from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from ..api_client import api_client
from .general import get_main_menu
from ..states.user_states import UserRegistration

router = Router()


@router.message(UserRegistration.waiting_full_name, F.text)
async def reg_full_name(message: Message, state: FSMContext):
    """
    Шаг 1: имя / ФИО.
    """
    full_name = (message.text or "").strip()
    if not full_name:
        await message.answer("Пожалуйста, введите ваше имя текстом.")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(UserRegistration.waiting_phone)

    await message.answer("Введите номер телефона:")


@router.message(UserRegistration.waiting_phone, F.text)
async def reg_phone(message: Message, state: FSMContext):
    """
    Шаг 2: телефон.
    """
    phone = (message.text or "").strip()
    if not phone:
        await message.answer("Пожалуйста, введите номер телефона.")
        return

    # Здесь можно позже добавить валидацию формата телефона
    await state.update_data(phone=phone)
    await state.set_state(UserRegistration.waiting_city)

    await message.answer("Введите ваш город:")


@router.message(UserRegistration.waiting_city, F.text)
async def reg_city(message: Message, state: FSMContext):
    """
    Шаг 3: город → создаём пользователя в backend.
    """
    city = (message.text or "").strip()
    if not city:
        await message.answer("Пожалуйста, введите название города.")
        return

    data = await state.get_data()

    payload = {
        "telegram_id": message.from_user.id,
        "full_name": data.get("full_name") or message.from_user.full_name,
        "phone": data.get("phone"),
        "city": city,
    }

    try:
        await api_client.create_user(payload)
    except Exception:
        # Логируем в api_client, пользователю — аккуратное сообщение
        await message.answer(
            "Произошла ошибка при регистрации. Попробуйте позже."
        )
        await state.clear()
        return

    await message.answer("Регистрация успешно завершена! 🎉")

    # Показываем главное меню отдельным сообщением
    # Пока считаем, что новая регистрация — это обычный клиент.
    await message.answer(
        "Выберите действие из меню ниже 👇",
        reply_markup=get_main_menu(role="client"),
    )

    await state.clear()
