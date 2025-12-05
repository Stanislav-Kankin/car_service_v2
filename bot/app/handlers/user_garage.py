from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from ..api_client import api_client
from ..states.user_states import CarCreate

router = Router()


def get_garage_keyboard(has_cars: bool) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="➕ Добавить авто",
                callback_data="garage:add",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⬅️ В меню",
                callback_data="main:menu",
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_car_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="car_create:back",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="car_create:cancel",
                ),
            ],
        ]
    )


async def _send_garage(message: Message):
    """
    Показ списка машин пользователя.
    """
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer(
            "Похоже, вы ещё не зарегистрированы.\n"
            "Нажмите /start, чтобы пройти короткую регистрацию.",
        )
        return

    user_id = user["id"] if isinstance(user, dict) else getattr(user, "id", None)
    if not user_id:
        await message.answer("Не удалось определить пользователя. Попробуйте позже.")
        return

    try:
        cars = await api_client.list_cars_by_user(user_id)
    except Exception:
        await message.answer("Не удалось загрузить гараж. Попробуйте позже.")
        return

    if not cars:
        text = (
            "<b>🚗 Мой гараж</b>\n\n"
            "У вас пока нет добавленных машин.\n"
            "Нажмите «➕ Добавить авто», чтобы добавить первую."
        )
        has_cars = False
    else:
        lines = ["<b>🚗 Мой гараж</b>", ""]
        for idx, car in enumerate(cars, start=1):
            brand = car.get("brand") or "—"
            model = car.get("model") or "—"
            year = car.get("year") or "—"
            plate = car.get("license_plate") or "—"
            vin = car.get("vin") or "—"

            lines.append(
                f"<b>#{idx}</b> {brand} {model}".strip()
            )
            lines.append(f"  Год: {year}")
            lines.append(f"  Госномер: {plate}")
            lines.append(f"  VIN: {vin}")
            lines.append("")

        text = "\n".join(lines)
        has_cars = True

    await message.answer(
        text,
        reply_markup=get_garage_keyboard(has_cars),
    )


# --- входы в гараж ---


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
    Вход из главного инлайн-меню.
    """
    await _send_garage(callback.message)
    await callback.answer()


# --- добавление авто ---


@router.callback_query(F.data == "garage:add")
async def garage_add_start(callback: CallbackQuery, state: FSMContext):
    """
    Старт сценария добавления машины.
    """
    await state.set_state(CarCreate.choosing_brand)
    await callback.message.answer(
        "Давайте добавим вашу машину.\n\n"
        "Введите <b>марку</b> (например, BMW, Kia, Lada):",
        reply_markup=get_car_create_keyboard(),
    )
    await callback.answer()


@router.message(CarCreate.choosing_brand, F.text)
async def car_create_brand(message: Message, state: FSMContext):
    brand = (message.text or "").strip()
    if not brand:
        await message.answer(
            "Марка не распознана. Пожалуйста, введите текстом.",
            reply_markup=get_car_create_keyboard(),
        )
        return

    await state.update_data(brand=brand)
    await state.set_state(CarCreate.choosing_model)

    await message.answer(
        "Введите <b>модель</b> (например, 3 Series, Rio, Vesta):",
        reply_markup=get_car_create_keyboard(),
    )


@router.message(CarCreate.choosing_model, F.text)
async def car_create_model(message: Message, state: FSMContext):
    model = (message.text or "").strip()
    if not model:
        await message.answer(
            "Модель не распознана. Пожалуйста, введите текстом.",
            reply_markup=get_car_create_keyboard(),
        )
        return

    await state.update_data(model=model)
    await state.set_state(CarCreate.choosing_year)

    await message.answer(
        "Введите <b>год выпуска</b> (4 цифры) или напишите «пропустить»:",
        reply_markup=get_car_create_keyboard(),
    )


@router.message(CarCreate.choosing_year, F.text)
async def car_create_year(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    year: int | None = None

    if text.lower() != "пропустить":
        if not text.isdigit() or len(text) != 4:
            await message.answer(
                "Пожалуйста, введите год в формате 4 цифр (например, 2015) "
                "или напишите «пропустить».",
                reply_markup=get_car_create_keyboard(),
            )
            return
        year = int(text)

    await state.update_data(year=year)
    await state.set_state(CarCreate.choosing_license_plate)

    await message.answer(
        "Введите <b>госномер</b> (как в СТС) или напишите «пропустить»:",
        reply_markup=get_car_create_keyboard(),
    )


@router.message(CarCreate.choosing_license_plate, F.text)
async def car_create_plate(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    plate = None if text.lower() == "пропустить" else text or None

    await state.update_data(license_plate=plate)
    await state.set_state(CarCreate.choosing_vin)

    await message.answer(
        "Введите <b>VIN</b> или напишите «пропустить»:",
        reply_markup=get_car_create_keyboard(),
    )


@router.message(CarCreate.choosing_vin, F.text)
async def car_create_vin(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    vin = None if text.lower() == "пропустить" else text or None

    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer(
            "Не удалось определить пользователя. Попробуйте ещё раз через /start.",
        )
        await state.clear()
        return

    user_id = user["id"] if isinstance(user, dict) else getattr(user, "id", None)
    if not user_id:
        await message.answer("Не удалось определить пользователя. Попробуйте позже.")
        await state.clear()
        return

    data = await state.get_data()

    payload = {
        "user_id": user_id,
        "brand": data.get("brand"),
        "model": data.get("model"),
        "year": data.get("year"),
        "license_plate": data.get("license_plate"),
        "vin": vin,
    }

    try:
        await api_client.create_car(payload)
    except Exception:
        await message.answer(
            "Не удалось сохранить машину. Попробуйте позже.",
        )
        await state.clear()
        return

    await message.answer("Машина успешно добавлена в гараж! 🚗")

    await state.clear()
    # Показываем обновлённый гараж
    await _send_garage(message)


# --- кнопки Назад / Отмена во время создания авто ---


@router.callback_query(CarCreate, F.data == "car_create:cancel")
async def car_create_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Добавление машины отменено.")
    await _send_garage(callback.message)
    await callback.answer()


@router.callback_query(CarCreate, F.data == "car_create:back")
async def car_create_back(callback: CallbackQuery, state: FSMContext):
    """
    Примитивный «Назад» между шагами.
    Просто возвращаемся на предыдущий вопрос.
    """
    current = await state.get_state()

    if current == CarCreate.choosing_model.state:
        await state.set_state(CarCreate.choosing_brand)
        await callback.message.answer(
            "Вернулись на шаг выбора марки.\n\n"
            "Введите <b>марку</b> автомобиля:",
            reply_markup=get_car_create_keyboard(),
        )
    elif current == CarCreate.choosing_year.state:
        await state.set_state(CarCreate.choosing_model)
        await callback.message.answer(
            "Вернулись на шаг выбора модели.\n\n"
            "Введите <b>модель</b> автомобиля:",
            reply_markup=get_car_create_keyboard(),
        )
    elif current == CarCreate.choosing_license_plate.state:
        await state.set_state(CarCreate.choosing_year)
        await callback.message.answer(
            "Вернулись на шаг указания года.\n\n"
            "Введите год выпуска (4 цифры) или напишите «пропустить»:",
            reply_markup=get_car_create_keyboard(),
        )
    elif current == CarCreate.choosing_vin.state:
        await state.set_state(CarCreate.choosing_license_plate)
        await callback.message.answer(
            "Вернулись на шаг указания госномера.\n\n"
            "Введите госномер или напишите «пропустить»:",
            reply_markup=get_car_create_keyboard(),
        )
    else:
        # На всякий случай — если что-то пошло не так, просто выходим
        await state.clear()
        await callback.message.answer("Сценарий сброшен.")
        await _send_garage(callback.message)

    await callback.answer()
