from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from ..api_client import api_client
from ..states.user_states import CarCreate, CarEdit

router = Router()


# ---------- Вспомогательные клавиатуры ----------


def get_garage_keyboard_for_empty() -> InlineKeyboardMarkup:
    """
    Клавиатура, когда в гараже нет машин.
    """
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


def get_confirm_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения для шага создания авто.

    prefix:
      - "car_brand"
      - "car_model"
      - "car_year"
      - "car_plate"
      - "car_vin"
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Верно",
                    callback_data=f"{prefix}:ok",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать",
                    callback_data=f"{prefix}:edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="car_create:cancel",
                ),
            ],
        ]
    )


# ---------- Показ гаража ----------


async def _send_garage(message: Message, telegram_id: int):
    """
    Показ списка машин пользователя.

    ВАЖНО: telegram_id передаём явно, т.к. для callback message.from_user = бот.
    """
    user = await api_client.get_user_by_telegram(telegram_id)
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
        await message.answer(
            text,
            reply_markup=get_garage_keyboard_for_empty(),
        )
        return

    # Есть машины
    lines = ["<b>🚗 Мой гараж</b>", ""]
    keyboard_rows: list[list[InlineKeyboardButton]] = []

    for idx, car in enumerate(cars, start=1):
        car_id = car.get("id")
        brand = car.get("brand") or "—"
        model = car.get("model") or "—"
        year = car.get("year") or "—"
        plate = car.get("license_plate") or "—"
        vin = car.get("vin") or "—"

        lines.append(f"<b>#{idx}</b> {brand} {model}".strip())
        lines.append(f"  Год: {year}")
        lines.append(f"  Госномер: {plate}")
        lines.append(f"  VIN: {vin}")
        lines.append("")

        if car_id is not None:
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✏️ Изменить #{idx}",
                        callback_data=f"garage_edit:{car_id}",
                    ),
                    InlineKeyboardButton(
                        text=f"🗑 Удалить #{idx}",
                        callback_data=f"garage_delete:{car_id}",
                    ),
                ]
            )

    # Внизу — общие действия
    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="➕ Добавить авто",
                callback_data="garage:add",
            ),
        ]
    )
    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ В меню",
                callback_data="main:menu",
            ),
        ]
    )

    text = "\n".join(lines)

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
    )


@router.message(F.text == "🚗 Мой гараж")
async def garage_show_legacy(message: Message):
    await _send_garage(message, telegram_id=message.from_user.id)


@router.callback_query(F.data == "main:garage")
async def garage_show_from_menu(callback: CallbackQuery):
    await _send_garage(callback.message, telegram_id=callback.from_user.id)
    await callback.answer()


# ---------- Добавление авто: старт ----------


@router.callback_query(F.data == "garage:add")
async def garage_add_start(callback: CallbackQuery, state: FSMContext):
    """
    Старт сценария добавления машины.
    """
    await state.clear()
    await state.set_state(CarCreate.choosing_brand)

    await callback.message.answer(
        "Давайте добавим вашу машину.\n\n"
        "Введите <b>марку</b> (например, BMW, Kia, Lada):",
    )
    await callback.answer()


# ---------- Марка ----------


@router.message(CarCreate.choosing_brand, F.text)
async def car_create_brand(message: Message, state: FSMContext):
    brand = (message.text or "").strip()
    if not brand:
        await message.answer(
            "Марка не распознана. Пожалуйста, введите текстом."
        )
        return

    await state.update_data(brand=brand)

    await message.answer(
        f"Вы ввели марку: <b>{brand}</b>\n\n"
        "Верно?",
        reply_markup=get_confirm_keyboard("car_brand"),
    )


@router.callback_query(StateFilter(CarCreate.choosing_brand), F.data == "car_brand:edit")
async def car_brand_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Ок, давайте ещё раз.\n\nВведите <b>марку</b> автомобиля:"
    )
    await callback.answer()


@router.callback_query(StateFilter(CarCreate.choosing_brand), F.data == "car_brand:ok")
async def car_brand_ok(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CarCreate.choosing_model)
    await callback.message.answer(
        "Введите <b>модель</b> (например, 3 Series, Rio, Vesta):"
    )
    await callback.answer()


# ---------- Модель ----------


@router.message(CarCreate.choosing_model, F.text)
async def car_create_model(message: Message, state: FSMContext):
    model = (message.text or "").strip()
    if not model:
        await message.answer(
            "Модель не распознана. Пожалуйста, введите текстом."
        )
        return

    await state.update_data(model=model)

    await message.answer(
        f"Вы ввели модель: <b>{model}</b>\n\n"
        "Верно?",
        reply_markup=get_confirm_keyboard("car_model"),
    )


@router.callback_query(StateFilter(CarCreate.choosing_model), F.data == "car_model:edit")
async def car_model_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Ок, давайте ещё раз.\n\nВведите <b>модель</b> автомобиля:"
    )
    await callback.answer()


@router.callback_query(StateFilter(CarCreate.choosing_model), F.data == "car_model:ok")
async def car_model_ok(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CarCreate.choosing_year)
    await callback.message.answer(
        "Введите <b>год выпуска</b> (4 цифры) или напишите «пропустить»:"
    )
    await callback.answer()


# ---------- Год выпуска ----------


@router.message(CarCreate.choosing_year, F.text)
async def car_create_year(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    year: int | None = None
    description: str

    if text.lower() != "пропустить":
        if not text.isdigit() or len(text) != 4:
            await message.answer(
                "Пожалуйста, введите год в формате 4 цифр (например, 2015) "
                "или напишите «пропустить».",
            )
            return
        year = int(text)
        description = f"год выпуска: <b>{year}</b>"
    else:
        description = "что хотите <b>пропустить год выпуска</b>"

    await state.update_data(year=year)

    await message.answer(
        f"Вы указали {description}.\n\nВерно?",
        reply_markup=get_confirm_keyboard("car_year"),
    )


@router.callback_query(StateFilter(CarCreate.choosing_year), F.data == "car_year:edit")
async def car_year_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Ок, давайте ещё раз.\n\n"
        "Введите <b>год выпуска</b> (4 цифры) или напишите «пропустить»:"
    )
    await callback.answer()


@router.callback_query(StateFilter(CarCreate.choosing_year), F.data == "car_year:ok")
async def car_year_ok(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CarCreate.choosing_license_plate)
    await callback.message.answer(
        "Введите <b>госномер</b> (как в СТС) или напишите «пропустить»:"
    )
    await callback.answer()


# ---------- Госномер ----------


@router.message(CarCreate.choosing_license_plate, F.text)
async def car_create_plate(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower() == "пропустить":
        plate = None
        description = "что хотите <b>пропустить госномер</b>"
    else:
        plate = text or None
        if not plate:
            await message.answer(
                "Пожалуйста, введите госномер или напишите «пропустить».",
            )
            return
        description = f"госномер: <b>{plate}</b>"

    await state.update_data(license_plate=plate)

    await message.answer(
        f"Вы указали {description}.\n\nВерно?",
        reply_markup=get_confirm_keyboard("car_plate"),
    )


@router.callback_query(
    StateFilter(CarCreate.choosing_license_plate), F.data == "car_plate:edit"
)
async def car_plate_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Ок, давайте ещё раз.\n\n"
        "Введите <b>госномер</b> (как в СТС) или напишите «пропустить»:"
    )
    await callback.answer()


@router.callback_query(
    StateFilter(CarCreate.choosing_license_plate), F.data == "car_plate:ok"
)
async def car_plate_ok(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CarCreate.choosing_vin)
    await callback.message.answer(
        "Введите <b>VIN</b> или напишите «пропустить»:"
    )
    await callback.answer()


# ---------- VIN ----------


@router.message(CarCreate.choosing_vin, F.text)
async def car_create_vin(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower() == "пропустить":
        vin = None
        description = "что хотите <b>пропустить VIN</b>"
    else:
        vin = text or None
        if not vin:
            await message.answer(
                "Пожалуйста, введите VIN или напишите «пропустить».",
            )
            return
        description = f"VIN: <b>{vin}</b>"

    await state.update_data(vin=vin)

    await message.answer(
        f"Вы указали {description}.\n\nВерно?",
        reply_markup=get_confirm_keyboard("car_vin"),
    )


@router.callback_query(StateFilter(CarCreate.choosing_vin), F.data == "car_vin:edit")
async def car_vin_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Ок, давайте ещё раз.\n\nВведите <b>VIN</b> или напишите «пропустить»:"
    )
    await callback.answer()


@router.callback_query(StateFilter(CarCreate.choosing_vin), F.data == "car_vin:ok")
async def car_vin_ok(callback: CallbackQuery, state: FSMContext):
    """
    Финальное сохранение машины.
    """
    telegram_id = callback.from_user.id

    user = await api_client.get_user_by_telegram(telegram_id)
    if not user:
        await callback.message.answer(
            "Не удалось определить пользователя. Попробуйте ещё раз через /start.",
        )
        await state.clear()
        await callback.answer()
        return

    user_id = user["id"] if isinstance(user, dict) else getattr(user, "id", None)
    if not user_id:
        await callback.message.answer(
            "Не удалось определить пользователя. Попробуйте позже."
        )
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()

    payload = {
        "user_id": user_id,
        "brand": data.get("brand"),
        "model": data.get("model"),
        "year": data.get("year"),
        "license_plate": data.get("license_plate"),
        "vin": data.get("vin"),
    }

    try:
        await api_client.create_car(payload)
    except Exception:
        await callback.message.answer(
            "Не удалось сохранить машину. Попробуйте позже.",
        )
        await state.clear()
        await callback.answer()
        return

    await callback.message.answer("Машина успешно добавлена в гараж! 🚗")

    await state.clear()
    await _send_garage(callback.message, telegram_id=telegram_id)
    await callback.answer()


# ---------- Редактирование авто ----------


@router.callback_query(F.data.startswith("garage_edit:"))
async def garage_edit_start(callback: CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split(":")[1])
    car = await api_client.get_car(car_id)

    if not car:
        await callback.answer("Машина не найдена.")
        return

    await state.update_data(car_id=car_id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Марка", callback_data="edit_field:brand"),
                InlineKeyboardButton(text="Модель", callback_data="edit_field:model"),
            ],
            [
                InlineKeyboardButton(text="Год", callback_data="edit_field:year"),
                InlineKeyboardButton(
                    text="Гос. номер", callback_data="edit_field:license_plate"
                ),
            ],
            [
                InlineKeyboardButton(text="VIN", callback_data="edit_field:vin"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Отмена", callback_data="garage_cancel"),
            ],
        ]
    )

    await callback.message.answer(
        f"Что хотите изменить в машине?\n\n🚘 <b>{car.get('brand') or ''} "
        f"{car.get('model') or ''} ({car.get('year') or '—'})</b>",
        reply_markup=kb,
    )

    await state.set_state(CarEdit.waiting_for_field)
    await callback.answer()


@router.callback_query(CarEdit.waiting_for_field, F.data.startswith("edit_field:"))
async def garage_edit_choose_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":")[1]
    await state.update_data(edit_field=field)

    await callback.message.answer("Введите новое значение:")
    await state.set_state(CarEdit.waiting_for_value)
    await callback.answer()


@router.message(CarEdit.waiting_for_value)
async def garage_edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    car_id = data["car_id"]
    field = data["edit_field"]
    value_raw = (message.text or "").strip()

    if not value_raw:
        await message.answer("Значение не может быть пустым. Введите ещё раз.")
        return

    # Простейшая обработка года
    if field == "year":
        if not value_raw.isdigit() or len(value_raw) != 4:
            await message.answer(
                "Пожалуйста, введите год в формате 4 цифр (например, 2015)."
            )
            return
        value: int | str = int(value_raw)
    else:
        value = value_raw

    payload = {field: value}

    try:
        await api_client.update_car(car_id, payload)
        await message.answer("✔ Машина обновлена!")
    except Exception:
        await message.answer("❌ Ошибка при обновлении машины. Попробуйте позже.")
        return

    await state.clear()
    await _send_garage(message, telegram_id=message.from_user.id)


# ---------- Удаление авто ----------


@router.callback_query(F.data.startswith("garage_delete:"))
async def garage_delete_confirm(callback: CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split(":")[1])
    await state.update_data(car_id=car_id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data="garage_delete_confirmed"
                ),
            ],
            [
                InlineKeyboardButton(text="⬅️ Отмена", callback_data="garage_cancel"),
            ],
        ]
    )

    await callback.message.answer(
        "❗ Вы уверены, что хотите удалить автомобиль?",
        reply_markup=kb,
    )

    await state.set_state(CarEdit.confirm_delete)
    await callback.answer()


@router.callback_query(CarEdit.confirm_delete, F.data == "garage_delete_confirmed")
async def garage_delete_final(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    car_id = data["car_id"]

    try:
        await api_client.delete_car(car_id)
        await callback.message.answer("🗑 Машина удалена.")
    except Exception:
        await callback.message.answer("❌ Ошибка при удалении машины.")

    await state.clear()
    await _send_garage(callback.message, telegram_id=callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "garage_cancel")
async def garage_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _send_garage(callback.message, telegram_id=callback.from_user.id)
    await callback.answer()


# ---------- Общая отмена сценария создания ----------


@router.callback_query(
    StateFilter(
        CarCreate.choosing_brand,
        CarCreate.choosing_model,
        CarCreate.choosing_year,
        CarCreate.choosing_license_plate,
        CarCreate.choosing_vin,
    ),
    F.data == "car_create:cancel",
)
async def car_create_cancel(callback: CallbackQuery, state: FSMContext):
    """
    Отмена из любого шага создания авто.
    """
    telegram_id = callback.from_user.id
    await state.clear()
    await callback.message.answer("Добавление машины отменено.")
    await _send_garage(callback.message, telegram_id=telegram_id)
    await callback.answer()
