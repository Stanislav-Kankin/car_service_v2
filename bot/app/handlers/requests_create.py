from aiogram import Router, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from ..api_client import api_client

router = Router()


# -----------------------------
# FSM состояния создания заявки
# -----------------------------
class RequestCreateStates(StatesGroup):
    waiting_location = State()
    waiting_car_state = State()
    waiting_evacu_type = State()
    waiting_radius = State()
    waiting_service_category = State()
    waiting_description = State()
    waiting_photo_choice = State()
    waiting_photo = State()
    waiting_hide_phone = State()
    waiting_car_choice = State()
    waiting_work_mode = State()  # 👈 НОВОЕ: выбор «способа работы со СТО»


# -----------------------------
# Вспомогательные клавиатуры
# -----------------------------

def kb_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def kb_car_state() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Едет сам")],
            [KeyboardButton(text="🚨 Нужна эвакуация/выездной мастер")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def kb_evacu_type() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚛 Эвакуатор")],
            [KeyboardButton(text="🧰 Выездной мастер")],
            [KeyboardButton(text="🚛+🧰 Оба варианта")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def kb_radius() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="3 км"),
                KeyboardButton(text="5 км"),
                KeyboardButton(text="10 км"),
            ],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def kb_photo_choice() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 Отправить фото")],
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def kb_hide_phone() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Показывать номер")],
            [KeyboardButton(text="🙈 Скрыть номер")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def kb_work_mode() -> ReplyKeyboardMarkup:
    """
    Выбор способа работы со СТО:
    - выбрать конкретный сервис из списка
    - отправить всем подходящим
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Выбрать СТО из списка")],
            [KeyboardButton(text="📡 Отправить всем подходящим СТО")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


# -----------------------------
# Общая отмена
# -----------------------------

@router.message(F.text == "❌ Отмена")
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Создание заявки отменено. Если нужно начать заново — нажмите «📝 Создать заявку».",
        reply_markup=ReplyKeyboardRemove(),
    )


# -----------------------------
# Старт создания заявки
# -----------------------------

@router.message(F.text == "📝 Создать заявку")
async def request_create_start(message: Message, state: FSMContext):
    """Стартовый шаг: проверяем пользователя и наличие машин, спрашиваем локацию."""
    await state.clear()

    tg_id = message.chat.id
    user = await api_client.get_user_by_telegram(tg_id)

    if not user:
        await message.answer(
            "Вы ещё не зарегистрированы. Напишите /start, чтобы пройти регистрацию."
        )
        return

    # Проверяем, что у пользователя есть хотя бы одна машина
    cars = await api_client.list_cars_by_user(user["id"])
    if not cars:
        await message.answer(
            "Сначала добавьте автомобиль в гараж.\n\n"
            "Зайдите в раздел «🚗 Мой гараж» и добавьте хотя бы одну машину.",
        )
        return

    # Сохраняем базовые данные в FSM
    await state.update_data(
        user_id=user["id"],
        cars=cars,
        photos=[],
    )

    await message.answer(
        "Шаг 1/8.\n\n"
        "Отправьте геолокацию места, где нужна помощь,\n"
        "или напишите адрес / район текстом.\n\n"
        "Например:\n"
        "• «Краснодар, ул. Северная 123»\n"
        "• «Энка, парковка ТРЦ»",
        reply_markup=kb_cancel(),
    )
    await state.set_state(RequestCreateStates.waiting_location)


@router.callback_query(F.data == "main:new_request")
async def request_create_start_from_menu(callback: CallbackQuery, state: FSMContext):
    """
    Старт создания заявки из главного инлайн-меню.
    """
    await request_create_start(callback.message, state)
    await callback.answer()

# -----------------------------
# Шаг 1 — Локация
# -----------------------------


@router.message(RequestCreateStates.waiting_location)
async def request_location(message: Message, state: FSMContext):
    latitude = None
    longitude = None
    address_text = None

    if message.location:
        latitude = message.location.latitude
        longitude = message.location.longitude
    elif message.text:
        address_text = message.text.strip()

    await state.update_data(
        latitude=latitude,
        longitude=longitude,
        address_text=address_text,
    )

    await message.answer(
        "Шаг 2/8.\n\n"
        "Автомобиль передвигается самостоятельно или нужна эвакуация/выездной мастер?",
        reply_markup=kb_car_state(),
    )
    await state.set_state(RequestCreateStates.waiting_car_state)


# -----------------------------
# Шаг 2 — Состояние авто
# -----------------------------

@router.message(RequestCreateStates.waiting_car_state, F.text)
async def request_car_state(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "🚗 Едет сам":
        await state.update_data(
            is_car_movable=True,
            need_tow_truck=False,
            need_mobile_master=False,
        )
        await message.answer(
            "Шаг 3/8.\n\n"
            "Выберите радиус, в котором вам будет комфортно произвести ремонт.",
            reply_markup=kb_radius(),
        )
        await state.set_state(RequestCreateStates.waiting_radius)
        return

    if text == "🚨 Нужна эвакуация/выездной мастер":
        await state.update_data(
            is_car_movable=False,
        )
        await message.answer(
            "Уточните, что именно требуется:",
            reply_markup=kb_evacu_type(),
        )
        await state.set_state(RequestCreateStates.waiting_evacu_type)
        return

    await message.answer(
        "Пожалуйста, используйте кнопки: «🚗 Едет сам» или "
        "«🚨 Нужна эвакуация/выездной мастер».",
        reply_markup=kb_car_state(),
    )


# -----------------------------
# Шаг 2b — Тип помощи (эвакуатор/мастер)
# -----------------------------

@router.message(RequestCreateStates.waiting_evacu_type, F.text)
async def request_evacu_type(message: Message, state: FSMContext):
    text = message.text.strip()

    need_tow_truck = False
    need_mobile_master = False

    if text == "🚛 Эвакуатор":
        need_tow_truck = True
    elif text == "🧰 Выездной мастер":
        need_mobile_master = True
    elif text == "🚛+🧰 Оба варианта":
        need_tow_truck = True
        need_mobile_master = True
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов с кнопок.",
            reply_markup=kb_evacu_type(),
        )
        return

    await state.update_data(
        need_tow_truck=need_tow_truck,
        need_mobile_master=need_mobile_master,
    )

    # Для эвакуации радиус пока не спрашиваем (будет отдельная логика подбора).
    await message.answer(
        "Шаг 4/8.\n\n"
        "Уточните, какая услуга вам нужна.\n"
        "Например: «Двигатель», «Ходовая», «Шиномонтаж», «Электрика» и т.п.",
        reply_markup=kb_cancel(),
    )
    await state.set_state(RequestCreateStates.waiting_service_category)


# -----------------------------
# Шаг 3 — Радиус (для «едет сам»)
# -----------------------------

@router.message(RequestCreateStates.waiting_radius, F.text)
async def request_radius(message: Message, state: FSMContext):
    text = message.text.strip()

    mapping = {
        "3 км": 3,
        "5 км": 5,
        "10 км": 10,
    }

    if text not in mapping:
        await message.answer(
            "Пожалуйста, выберите радиус с помощью кнопок.",
            reply_markup=kb_radius(),
        )
        return

    await state.update_data(radius_km=mapping[text])

    await message.answer(
        "Шаг 4/8.\n\n"
        "Уточните, какая услуга вам нужна.\n"
        "Например: «Двигатель», «Ходовая», «Шиномонтаж», «Электрика» и т.п.",
        reply_markup=kb_cancel(),
    )
    await state.set_state(RequestCreateStates.waiting_service_category)


# -----------------------------
# Шаг 4 — Тип услуги / категория
# -----------------------------

@router.message(RequestCreateStates.waiting_service_category, F.text)
async def request_service_category(message: Message, state: FSMContext):
    service_category = message.text.strip()
    await state.update_data(service_category=service_category)

    await message.answer(
        "Шаг 5/8.\n\n"
        "Опишите проблему как можно подробнее.\n"
        "Например: «При разгоне появляется вибрация», "
        "«Горит чек двигателя», «Стучу подвеску справа» и т.п.",
        reply_markup=kb_cancel(),
    )
    await state.set_state(RequestCreateStates.waiting_description)


# -----------------------------
# Шаг 5 — Описание проблемы
# -----------------------------

@router.message(RequestCreateStates.waiting_description, F.text)
async def request_description(message: Message, state: FSMContext):
    description = message.text.strip()

    if len(description) < 5:
        await message.answer(
            "Пожалуйста, опишите проблему чуть подробнее.",
            reply_markup=kb_cancel(),
        )
        return

    await state.update_data(description=description)

    await message.answer(
        "Шаг 6/8.\n\n"
        "Вы можете прикрепить 1 фото (машины, повреждения и т.п.).\n\n"
        "Выберите вариант:",
        reply_markup=kb_photo_choice(),
    )
    await state.set_state(RequestCreateStates.waiting_photo_choice)


# -----------------------------
# Шаг 6 — Выбор: фото или пропустить
# -----------------------------

@router.message(RequestCreateStates.waiting_photo_choice, F.text)
async def request_photo_choice(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "📷 Отправить фото":
        await message.answer(
            "Отправьте одно фото.\n\n"
            "После отправки фото автоматически перейдём к следующему шагу.",
            reply_markup=kb_cancel(),
        )
        await state.set_state(RequestCreateStates.waiting_photo)
        return

    if text == "⏭ Пропустить":
        await message.answer(
            "Шаг 7/8.\n\n"
            "Показывать ваш номер телефона сотруднику сервиса?",
            reply_markup=kb_hide_phone(),
        )
        await state.set_state(RequestCreateStates.waiting_hide_phone)
        return

    await message.answer(
        "Пожалуйста, используйте кнопки «📷 Отправить фото» или «⏭ Пропустить».",
        reply_markup=kb_photo_choice(),
    )


# -----------------------------
# Шаг 6b — Приём фото
# -----------------------------

@router.message(RequestCreateStates.waiting_photo)
async def request_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer(
            "Пожалуйста, отправьте именно фото или нажмите «❌ Отмена».",
            reply_markup=kb_cancel(),
        )
        return

    photo = message.photo[-1]
    file_id = photo.file_id

    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(file_id)

    await state.update_data(photos=photos)

    await message.answer(
        "Фото сохранено. ✅\n\n"
        "Шаг 7/8.\n\n"
        "Показывать ваш номер телефона сотруднику сервиса?",
        reply_markup=kb_hide_phone(),
    )
    await state.set_state(RequestCreateStates.waiting_hide_phone)


# -----------------------------
# Шаг 7 — Скрыть/показать телефон
# -----------------------------

@router.message(RequestCreateStates.waiting_hide_phone, F.text)
async def request_hide_phone(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "📞 Показывать номер":
        hide_phone = False
    elif text == "🙈 Скрыть номер":
        hide_phone = True
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов с кнопок.",
            reply_markup=kb_hide_phone(),
        )
        return

    await state.update_data(hide_phone=hide_phone)

    # Теперь выбираем автомобиль (если их несколько)
    data = await state.get_data()
    cars = data.get("cars", [])

    if len(cars) == 1:
        # Если машина одна — берём её автоматически
        await state.update_data(selected_car_id=cars[0]["id"])
        await finalize_request(message, state)
        return

    # Если машин несколько — предлагаем выбрать
    kb_rows = [
        [KeyboardButton(text=f"{c['brand']} {c['model']} ({c.get('year') or '-'})")]
        for c in cars
    ]
    kb_rows.append([KeyboardButton(text="❌ Отмена")])

    await message.answer(
        "Шаг 8/8.\n\n"
        "Выберите автомобиль, для которого создаётся заявка:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=kb_rows,
            resize_keyboard=True,
        ),
    )
    await state.set_state(RequestCreateStates.waiting_car_choice)


# -----------------------------
# Шаг 8 — Выбор авто (если несколько)
# -----------------------------

@router.message(RequestCreateStates.waiting_car_choice, F.text)
async def request_car_choice(message: Message, state: FSMContext):
    text = message.text.strip()

    data = await state.get_data()
    cars = data.get("cars", [])

    # Ищем машину по тексту кнопки
    selected_id = None
    for c in cars:
        label = f"{c['brand']} {c['model']} ({c.get('year') or '-'})"
        if text == label:
            selected_id = c["id"]
            break

    if not selected_id:
        await message.answer(
            "Пожалуйста, выберите автомобиль с кнопок ниже или нажмите «❌ Отмена».",
        )
        return

    await state.update_data(selected_car_id=selected_id)
    await finalize_request(message, state)


# -----------------------------
# Финал 1 — создание заявки в backend
# -----------------------------

async def finalize_request(message: Message, state: FSMContext):
    """
    Создаём заявку в backend, сохраняем её ID в FSM
    и ПЕРЕХОДИМ к выбору способа работы со СТО.
    """
    data = await state.get_data()

    user_id = data["user_id"]
    car_id = data["selected_car_id"]

    payload = {
        "user_id": user_id,
        "car_id": car_id,
        "service_center_id": None,
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "address_text": data.get("address_text"),
        "is_car_movable": data.get("is_car_movable", True),
        "need_tow_truck": data.get("need_tow_truck", False),
        "need_mobile_master": data.get("need_mobile_master", False),
        "radius_km": data.get("radius_km"),
        "service_category": data.get("service_category"),
        "description": data.get("description"),
        "photos": data.get("photos") or None,
        "hide_phone": data.get("hide_phone", True),
        # статус на backend-е по умолчанию будет "new"
    }

    request_obj = await api_client.create_request(payload)

    # Сохраняем ID заявки и её данные в FSM для следующего шага
    await state.update_data(
        request_id=request_obj.get("id"),
    )

    await message.answer(
        "✅ Заявка создана!\n\n"
        "Теперь выберите, как работать с сервисами:\n\n"
        "• «📋 Выбрать СТО из списка» — покажем подходящие сервисы, и вы выберете один.\n"
        "• «📡 Отправить всем подходящим СТО» — заявку получат сразу все подходящие сервисы,\n"
        "  а вы позже выберете среди их откликов.",
        reply_markup=kb_work_mode(),
    )

    await state.set_state(RequestCreateStates.waiting_work_mode)


# -----------------------------
# Шаг 9 — выбор способа работы со СТО
# -----------------------------

@router.message(RequestCreateStates.waiting_work_mode, F.text)
async def request_work_mode(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "📋 Выбрать СТО из списка":
        await handle_choose_sc_from_list(message, state)
        return

    if text == "📡 Отправить всем подходящим СТО":
        await handle_send_to_all(message, state)
        return

    await message.answer(
        "Пожалуйста, выберите один из вариантов с кнопок:\n"
        "«📋 Выбрать СТО из списка» или «📡 Отправить всем подходящим СТО».",
        reply_markup=kb_work_mode(),
    )


# -----------------------------
# Ветка: «📋 Выбрать СТО из списка»
# -----------------------------

async def handle_choose_sc_from_list(message: Message, state: FSMContext):
    data = await state.get_data()

    request_id = data.get("request_id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    radius_km = data.get("radius_km")

    params = {}

    if latitude is not None and longitude is not None:
        params["latitude"] = latitude
        params["longitude"] = longitude

    if radius_km is not None:
        params["radius_km"] = radius_km

    # Пока без фильтра по специализациям — прототип.
    # Позже можно будет передавать service_category -> specializations.
    service_centers = await api_client.list_service_centers(params=params or None)

    if not service_centers:
        await message.answer(
            "К сожалению, подходящих СТО рядом не найдено. 😔\n\n"
            "Заявка сохранена, вы можете позже вернуться к её выбору в разделе «Мои заявки».",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    # Формируем inline-клавиатуру для выбора СТО
    buttons = []
    for sc in service_centers:
        sc_id = sc["id"]
        name = sc.get("name") or "СТО без названия"
        btn = InlineKeyboardButton(
            text=name,
            callback_data=f"req_sc_{request_id}_{sc_id}",
        )
        buttons.append([btn])

    # Кнопка «Отмена выбора СТО»
    buttons.append(
        [
            InlineKeyboardButton(
                text="Отмена выбора СТО",
                callback_data=f"req_sc_cancel_{request_id}",
            )
        ]
    )

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "Выберите подходящее СТО из списка:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("req_sc_cancel_"))
async def cb_sc_cancel(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await call.message.edit_text(
        "Выбор СТО отменён. Заявка сохранена без выбранного сервиса.",
    )


@router.callback_query(F.data.startswith("req_sc_"))
async def cb_sc_choose(call: CallbackQuery, state: FSMContext):
    """
    Обрабатываем выбор СТО. Формат callback_data: "req_sc_{request_id}_{sc_id}"
    """
    parts = call.data.split("_")
    # защита от неожиданного формата
    if len(parts) != 4:
        await call.answer("Неверный формат данных.", show_alert=True)
        return

    _, _, request_id_str, sc_id_str = parts

    try:
        request_id = int(request_id_str)
        sc_id = int(sc_id_str)
    except ValueError:
        await call.answer("Ошибка данных.", show_alert=True)
        return

    # Обновляем заявку: привязываем выбранное СТО и помечаем,
    # что оно принято (для простого прототипа).
    await api_client.update_request(
        request_id,
        {
            "service_center_id": sc_id,
            "status": "accepted_by_service",  # можно будет скорректировать по бизнес-логике
        },
    )

    sc = await api_client.get_service_center(sc_id)
    name = sc.get("name") or "Выбранный сервис"

    await call.answer()
    await state.clear()

    await call.message.edit_text(
        f"Вы выбрали СТО: {name}.\n\n"
        "Заявка передана в этот сервис. Менеджер свяжется с вами в ближайшее время.",
    )


# -----------------------------
# Ветка: «📡 Отправить всем подходящим СТО»
# -----------------------------

async def handle_send_to_all(message: Message, state: FSMContext):
    """
    На этом этапе:
    - переводим заявку в status=sent
    - ищем подходящие СТО
    - рассылаем каждому СТО уведомление с кнопками для отклика
    """

    data = await state.get_data()
    request_id = data.get("request_id")

    if not request_id:
        await message.answer(
            "Не удалось определить заявку. Попробуйте создать её заново.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    # 1) Обновляем заявку
    await api_client.update_request(
        request_id,
        {"status": "sent"},
    )

    # 2) Ищем подходящие СТО
    params = {}
    if data.get("latitude") and data.get("longitude"):
        params["latitude"] = data["latitude"]
        params["longitude"] = data["longitude"]

    if data.get("radius_km"):
        params["radius_km"] = data["radius_km"]

    # На данном этапе без спецов — добавим позже
    service_centers = await api_client.list_service_centers(params=params or None)

    # 3) Рассылаем
    for sc in service_centers:
        manager_tg = sc.get("telegram_id") or sc.get("user", {}).get("telegram_id")
        if not manager_tg:
            continue

        text = (
            "🔔 *Новая заявка*\n\n"
            f"Категория: {data.get('service_category')}\n"
            f"Описание: {data.get('description')}\n\n"
            "Можете отправить клиенту предложение."
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💰 Сделать предложение",
                        callback_data=f"offer_make_{request_id}_{sc['id']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔍 Детали",
                        callback_data=f"offer_details_{request_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"offer_reject_{request_id}_{sc['id']}",
                    )
                ],
            ]
        )

        try:
            await message.bot.send_message(
                chat_id=manager_tg,
                text=text,
                reply_markup=kb,
                parse_mode="Markdown",
            )
        except Exception:
            pass  # игнорируем ошибки — сервис мог заблокировать бота

    await state.clear()

    await message.answer(
        "📡 Ваша заявка отправлена всем подходящим СТО.\n"
        "Они смогут прислать вам свои предложения.\n"
        "Вы сможете выбрать лучшее в разделе «Мои заявки».",
        reply_markup=ReplyKeyboardRemove(),
    )
