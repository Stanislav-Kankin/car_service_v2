from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter

from ..api_client import api_client
from .general import get_main_menu

router = Router()


# ---------------------------------------------------------------------------
# FSM для создания заявки
# ---------------------------------------------------------------------------


class RequestCreateFSM(StatesGroup):
    # 1. Сначала состояние авто
    choosing_car_move = State()

    # 2. Если авто не едет — уточняем локацию
    choosing_location_method = State()
    waiting_location_geo = State()
    waiting_location_text = State()

    # 3. Для неездящих — тип помощи (эвакуатор/мастер)
    choosing_evacu_type = State()

    # 4. Радиус
    choosing_radius = State()
    entering_custom_radius = State()

    # 5. Категория услуги
    choosing_category = State()

    # 6. Описание
    waiting_description = State()
    confirming_description = State()

    # 7. Фото (опционально)
    waiting_photos = State()

    # 8. Скрывать номер?
    confirming_hide_phone = State()

    # 9. Машина
    choosing_car = State()

    # 10. Режим работы со СТО
    choosing_work_mode = State()


# ---------------------------------------------------------------------------
# Вспомогательные данные
# ---------------------------------------------------------------------------


SERVICE_CATEGORIES: List[Tuple[str, str]] = [
    ("Автомеханика", "mech"),
    ("Шиномонтаж", "tire"),
    ("Электрика", "elec"),
    ("Диагностика", "diag"),
    ("Кузовной ремонт", "body"),
    ("Агрегатный ремонт", "agg"),
]


# ---------------------------------------------------------------------------
# Вспомогательные клавиатуры
# ---------------------------------------------------------------------------


def kb_cancel_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="req_create:cancel",
                )
            ]
        ]
    )


def kb_car_move() -> InlineKeyboardMarkup:
    """
    Первый шаг — состояние авто.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚗 Авто едет само",
                    callback_data="req_move:self",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚨 Нужна эвакуация/выездной мастер",
                    callback_data="req_move:help",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="req_create:cancel",
                )
            ],
        ]
    )


def kb_location_method() -> InlineKeyboardMarkup:
    """
    Способ указания локации — ТОЛЬКО если авто не едет.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📍 Отправить геолокацию",
                    callback_data="req_loc:geo",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗺 Ввести адрес текстом",
                    callback_data="req_loc:text",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="req_create:cancel",
                )
            ],
        ]
    )


def kb_evacu_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚚 Эвакуатор",
                    callback_data="req_evacu:tow",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛠 Выездной мастер",
                    callback_data="req_evacu:mobile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚚+🛠 Оба варианта",
                    callback_data="req_evacu:both",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="req_create:cancel",
                )
            ],
        ]
    )


def kb_radius() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="3 км",
                    callback_data="req_radius:3",
                ),
                InlineKeyboardButton(
                    text="5 км",
                    callback_data="req_radius:5",
                ),
                InlineKeyboardButton(
                    text="10 км",
                    callback_data="req_radius:10",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Другое расстояние",
                    callback_data="req_radius:custom",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="req_create:cancel",
                )
            ],
        ]
    )


def kb_categories() -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for title, key in SERVICE_CATEGORIES:
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"req_cat:{key}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data="req_create:cancel",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm_description() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Верно",
                    callback_data="req_descr:ok",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать",
                    callback_data="req_descr:edit",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="req_create:cancel",
                )
            ],
        ]
    )


def kb_photos() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить фото",
                    callback_data="req_photo:skip",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="req_create:cancel",
                )
            ],
        ]
    )


def kb_hide_phone() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, показывать номер",
                    callback_data="req_phone:show",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Нет, скрывать номер",
                    callback_data="req_phone:hide",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="req_create:cancel",
                )
            ],
        ]
    )


def kb_work_mode() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Выбрать СТО из списка",
                    callback_data="req_work:list",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📡 Отправить всем подходящим",
                    callback_data="req_work:all",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В главное меню",
                    callback_data="main:menu",
                )
            ],
        ]
    )


def build_cars_keyboard(cars: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    if cars:
        for car in cars:
            car_id = car.get("id")
            brand = car.get("brand") or ""
            model = car.get("model") or ""
            title = f"{brand} {model}".strip() or "Без названия"

            rows.append(
                [
                    InlineKeyboardButton(
                        text=title,
                        callback_data=f"req_car:{car_id}",
                    )
                ]
            )

    rows.append(
        [
            InlineKeyboardButton(
                text="🚗 Без привязки к машине",
                callback_data="req_car:none",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data="req_create:cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Общие хелперы
# ---------------------------------------------------------------------------


async def _back_to_main_menu(message: Message, telegram_id: int) -> None:
    user = await api_client.get_user_by_telegram(telegram_id)
    role: Optional[str] = None
    if isinstance(user, dict):
        role = user.get("role")

    await message.answer(
        "Выберите действие из меню ниже 👇",
        reply_markup=get_main_menu(role),
    )


async def _get_or_create_user(message_or_cb) -> Optional[Dict[str, Any]]:
    """
    Универсальный хелпер: получить пользователя по telegram_id.
    Если не найден — сказать про /start.
    """
    if isinstance(message_or_cb, Message):
        tg_id = message_or_cb.from_user.id
        message = message_or_cb
    else:
        tg_id = message_or_cb.from_user.id
        message = message_or_cb.message

    user = await api_client.get_user_by_telegram(tg_id)
    if not user:
        await message.answer(
            "Похоже, вы ещё не зарегистрированы.\n"
            "Нажмите /start, чтобы пройти короткую регистрацию.",
        )
        return None
    return user


async def _create_request_from_state(
    telegram_id: int,
    state: FSMContext,
) -> Optional[Dict[str, Any]]:
    """
    Собираем все данные из FSM и создаём заявку в backend.
    """
    user = await api_client.get_user_by_telegram(telegram_id)
    if not user:
        return None

    user_id = user["id"] if isinstance(user, dict) else getattr(user, "id", None)
    if not user_id:
        return None

    data = await state.get_data()

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "car_id": data.get("car_id"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "address_text": data.get("address_text"),
        "is_car_movable": data.get("is_car_movable", True),
        "need_tow_truck": data.get("need_tow_truck", False),
        "need_mobile_master": data.get("need_mobile_master", False),
        "radius_km": data.get("radius_km"),
        "service_category": data.get("service_category"),
        "description": data.get("description"),
        "photos": data.get("photos"),
        "hide_phone": data.get("hide_phone", True),
    }

    try:
        request = await api_client.create_request(payload)
    except Exception:
        return None

    return request


# ---------------------------------------------------------------------------
# Старт сценария новой заявки
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "main:new_request")
async def new_request_start(callback: CallbackQuery, state: FSMContext):
    """
    Старт «Новой заявки» из главного меню.

    Сначала спрашиваем состояние авто — едет / не едет.
    """
    await state.clear()

    # Проверяем, что пользователь зарегистрирован
    user = await _get_or_create_user(callback)
    if not user:
        await callback.answer()
        return

    await state.set_state(RequestCreateFSM.choosing_car_move)

    await callback.message.edit_text(
        "📝 <b>Новая заявка</b>\n\n"
        "Для начала уточним, в каком состоянии автомобиль:",
        reply_markup=kb_car_move(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 1 — состояние автомобиля
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_car_move),
    F.data == "req_move:self",
)
async def req_move_self(callback: CallbackQuery, state: FSMContext):
    """
    Авто едет самостоятельно.
    Геолокацию НЕ спрашиваем, сразу радиус.
    """
    await state.update_data(
        is_car_movable=True,
        need_tow_truck=False,
        need_mobile_master=False,
    )
    await state.set_state(RequestCreateFSM.choosing_radius)

    await callback.message.edit_text(
        "Автомобиль <b>может передвигаться самостоятельно</b>.\n\n"
        "Выберите радиус, в котором вам удобно рассматривать сервисы:",
        reply_markup=kb_radius(),
    )
    await callback.answer()


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_car_move),
    F.data == "req_move:help",
)
async def req_move_help(callback: CallbackQuery, state: FSMContext):
    """
    Авто не едет. Здесь уже важна точная точка:
    спрашиваем гео или адрес.
    """
    await state.update_data(
        is_car_movable=False,
    )
    await state.set_state(RequestCreateFSM.choosing_location_method)

    await callback.message.edit_text(
        "Понял, автомобиль не может ехать сам.\n\n"
        "Уточните, где он сейчас находится:\n"
        "• отправьте геолокацию точки; или\n"
        "• введите адрес/координаты текстом.",
        reply_markup=kb_location_method(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 2 (ветка «не едет») — способ указания локации
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_location_method),
    F.data == "req_loc:geo",
)
async def req_location_geo_selected(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RequestCreateFSM.waiting_location_geo)
    await callback.message.edit_text(
        "Отправьте, пожалуйста, геолокацию точки, где стоит автомобиль.\n\n"
        "Используйте кнопку «📎» → «Геопозиция».\n\n"
        "Если передумали — нажмите «Отменить».",
        reply_markup=kb_cancel_only(),
    )
    await callback.answer()


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_location_method),
    F.data == "req_loc:text",
)
async def req_location_text_selected(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RequestCreateFSM.waiting_location_text)
    await callback.message.edit_text(
        "Введите адрес или координаты текстом.\n\n"
        "Например:\n"
        "«Москва, Ленинградский проспект, 10»\n"
        "или «СПб, КАД, 25 км, внутренняя сторона».\n\n"
        "Это поможет подобрать ближайших исполнителей.",
        reply_markup=kb_cancel_only(),
    )
    await callback.answer()


@router.message(
    RequestCreateFSM.waiting_location_geo,
    F.location,
)
async def req_location_geo_received(message: Message, state: FSMContext):
    loc = message.location
    await state.update_data(
        latitude=loc.latitude,
        longitude=loc.longitude,
    )

    await state.set_state(RequestCreateFSM.choosing_evacu_type)
    await message.answer(
        "📍 Локация получена.\n\n"
        "Теперь уточните, что нужно:\n"
        "эвакуатор, выездной мастер или оба варианта?",
        reply_markup=kb_evacu_type(),
    )


@router.message(
    RequestCreateFSM.waiting_location_geo,
)
async def req_location_geo_invalid(message: Message):
    await message.answer(
        "Пожалуйста, отправьте именно геолокацию через кнопку «📎».\n"
        "Если передумали — нажмите «Отменить» внизу.",
        reply_markup=kb_cancel_only(),
    )


@router.message(
    RequestCreateFSM.waiting_location_text,
    F.text,
)
async def req_location_text_received(message: Message, state: FSMContext):
    address = (message.text or "").strip()
    if not address:
        await message.answer(
            "Адрес не распознан. Введите, пожалуйста, текстом адрес или координаты."
        )
        return

    await state.update_data(
        address_text=address,
    )

    await state.set_state(RequestCreateFSM.choosing_evacu_type)
    await message.answer(
        f"📍 Вы указали адрес/координаты:\n<b>{address}</b>\n\n"
        "Теперь уточните, что нужно:\n"
        "эвакуатор, выездной мастер или оба варианта?",
        reply_markup=kb_evacu_type(),
    )


# ---------------------------------------------------------------------------
# Шаг 3 (ветка «не едет») — тип помощи (эвакуатор/мастер)
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_evacu_type),
    F.data.startswith("req_evacu:"),
)
async def req_evacu_type_selected(callback: CallbackQuery, state: FSMContext):
    data = callback.data.split(":", maxsplit=1)[1]

    need_tow = data in ("tow", "both")
    need_mobile = data in ("mobile", "both")

    await state.update_data(
        need_tow_truck=need_tow,
        need_mobile_master=need_mobile,
    )

    await state.set_state(RequestCreateFSM.choosing_radius)
    await callback.message.edit_text(
        "Принято.\n\n"
        "Теперь выберите радиус поиска подходящих сервисов:",
        reply_markup=kb_radius(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 4 — радиус (общий для обеих веток)
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_radius),
    F.data.startswith("req_radius:"),
)
async def req_radius_selected(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", maxsplit=1)[1]

    if value == "custom":
        await state.set_state(RequestCreateFSM.entering_custom_radius)
        await callback.message.edit_text(
            "Введите радиус в километрах числом, например:\n<b>15</b>",
            reply_markup=kb_cancel_only(),
        )
        await callback.answer()
        return

    try:
        radius = int(value)
    except ValueError:
        await callback.answer("Некорректный радиус.")
        return

    await state.update_data(radius_km=radius)

    await state.set_state(RequestCreateFSM.choosing_category)
    await callback.message.edit_text(
        f"Радиус: <b>{radius} км</b>.\n\n"
        "Теперь выберите категорию услуги:",
        reply_markup=kb_categories(),
    )
    await callback.answer()


@router.message(
    RequestCreateFSM.entering_custom_radius,
    F.text,
)
async def req_radius_custom_entered(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer(
            "Пожалуйста, введите радиус в километрах числом, например 15."
        )
        return

    radius = int(text)
    if radius <= 0 or radius > 200:
        await message.answer(
            "Радиус должен быть от 1 до 200 км.\n"
            "Введите другое значение."
        )
        return

    await state.update_data(radius_km=radius)

    await state.set_state(RequestCreateFSM.choosing_category)
    await message.answer(
        f"Радиус: <b>{radius} км</b>.\n\n"
        "Теперь выберите категорию услуги:",
        reply_markup=kb_categories(),
    )


# ---------------------------------------------------------------------------
# Шаг 5 — категория услуги
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_category),
    F.data.startswith("req_cat:"),
)
async def req_category_selected(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", maxsplit=1)[1]

    title = next(
        (t for t, k in SERVICE_CATEGORIES if k == key),
        None,
    )
    if not title:
        await callback.answer("Не удалось распознать категорию.")
        return

    await state.update_data(service_category=key)

    await state.set_state(RequestCreateFSM.waiting_description)
    await callback.message.edit_text(
        f"Категория: <b>{title}</b>.\n\n"
        "Теперь опишите проблему текстом.\n\n"
        "Примеры:\n"
        "• «Стучит спереди справа, на кочках усиливается»\n"
        "• «Не заводится, стартер крутит»\n"
        "• «Нужно поменять масло и фильтры»",
        reply_markup=kb_cancel_only(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 6 — описание проблемы (с подтверждением)
# ---------------------------------------------------------------------------


@router.message(
    RequestCreateFSM.waiting_description,
    F.text,
)
async def req_description_received(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer(
            "Постарайтесь описать проблему чуть подробнее (минимум 5 символов)."
        )
        return

    await state.update_data(description=text)
    await state.set_state(RequestCreateFSM.confirming_description)

    await message.answer(
        "Проверьте описание проблемы:\n\n"
        f"<i>{text}</i>\n\n"
        "Всё верно?",
        reply_markup=kb_confirm_description(),
    )


@router.callback_query(
    StateFilter(RequestCreateFSM.confirming_description),
    F.data == "req_descr:edit",
)
async def req_description_edit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RequestCreateFSM.waiting_description)
    await callback.message.edit_text(
        "Хорошо, опишите проблему ещё раз текстом:",
        reply_markup=kb_cancel_only(),
    )
    await callback.answer()


@router.callback_query(
    StateFilter(RequestCreateFSM.confirming_description),
    F.data == "req_descr:ok",
)
async def req_description_ok(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RequestCreateFSM.waiting_photos)
    await callback.message.edit_text(
        "Если нужно, прикрепите <b>одно фото</b> к заявке "
        "(например, повреждение или ошибка на приборке).\n\n"
        "Просто отправьте фото сообщением.\n"
        "Или нажмите «Пропустить фото».",
        reply_markup=kb_photos(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 7 — фото (опционально, одно)
# ---------------------------------------------------------------------------


@router.message(
    RequestCreateFSM.waiting_photos,
    F.photo,
)
async def req_photo_received(message: Message, state: FSMContext):
    photo = message.photo[-1]
    await state.update_data(photos=[photo.file_id])

    await state.set_state(RequestCreateFSM.confirming_hide_phone)
    await message.answer(
        "Фото сохранено 📷.\n\n"
        "Теперь решим вопрос с номером телефона:",
        reply_markup=kb_hide_phone(),
    )


@router.callback_query(
    StateFilter(RequestCreateFSM.waiting_photos),
    F.data == "req_photo:skip",
)
async def req_photo_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photos=None)
    await state.set_state(RequestCreateFSM.confirming_hide_phone)
    await callback.message.edit_text(
        "Ок, без фото.\n\n"
        "Теперь решим вопрос с номером телефона:",
        reply_markup=kb_hide_phone(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 8 — скрытие телефона
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(RequestCreateFSM.confirming_hide_phone),
    F.data.in_(("req_phone:show", "req_phone:hide")),
)
async def req_hide_phone_selected(callback: CallbackQuery, state: FSMContext):
    hide = callback.data.endswith(":hide")
    await state.update_data(hide_phone=hide)

    # Переходим к выбору машины
    user = await _get_or_create_user(callback)
    if not user:
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

    try:
        cars = await api_client.list_cars_by_user(user_id)
    except Exception:
        cars = []

    await state.set_state(RequestCreateFSM.choosing_car)

    if not cars:
        await callback.message.edit_text(
            "У вас пока нет добавленных машин.\n\n"
            "Можете продолжить без привязки к авто — выберите пункт ниже:",
            reply_markup=build_cars_keyboard([]),
        )
    else:
        await callback.message.edit_text(
            "Теперь выберите, к какой машине относится заявка "
            "или продолжите без привязки:",
            reply_markup=build_cars_keyboard(cars),
        )

    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 9 — выбор машины
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_car),
    F.data.startswith("req_car:"),
)
async def req_car_selected(callback: CallbackQuery, state: FSMContext):
    suffix = callback.data.split(":", maxsplit=1)[1]
    if suffix == "none":
        car_id = None
    else:
        try:
            car_id = int(suffix)
        except ValueError:
            await callback.answer("Некорректный выбор машины.")
            return

    await state.update_data(car_id=car_id)

    # На этом этапе у нас есть все данные для создания заявки
    request = await _create_request_from_state(callback.from_user.id, state)
    if not request:
        await callback.message.edit_text(
            "Не удалось сохранить заявку. Попробуйте позже.",
            reply_markup=kb_cancel_only(),
        )
        await state.clear()
        await callback.answer()
        return

    request_id = request.get("id")

    await state.update_data(created_request_id=request_id)
    await state.set_state(RequestCreateFSM.choosing_work_mode)

    await callback.message.edit_text(
        f"✅ Заявка <b>№{request_id}</b> создана.\n\n"
        "Как вы хотите работать с СТО по этой заявке?",
        reply_markup=kb_work_mode(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 10 — способ работы со СТО (пока заглушки)
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_work_mode),
    F.data.in_(("req_work:list", "req_work:all")),
)
async def req_work_mode_selected(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    request_id = data.get("created_request_id")

    if callback.data.endswith("list"):
        text = (
            f"Заявка №{request_id} сохранена.\n\n"
            "Режим «Выбрать СТО из списка» пока в разработке.\n"
            "Скоро здесь появится список подходящих сервисов.\n\n"
            "Пока вы можете посмотреть заявку в разделе «Мои заявки»."
        )
    else:
        text = (
            f"Заявка №{request_id} сохранена.\n\n"
            "Режим «Отправить всем подходящим СТО» "
            "будет добавлен в следующем этапе разработки.\n\n"
            "Пока вы можете посмотреть заявку в разделе «Мои заявки»."
        )

    await state.clear()
    await callback.message.edit_text(text)

    # Возвращаем главное меню
    await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
    await callback.answer()


# ---------------------------------------------------------------------------
# Общая отмена сценария
# ---------------------------------------------------------------------------


@router.callback_query(
    StateFilter(
        RequestCreateFSM.choosing_car_move,
        RequestCreateFSM.choosing_location_method,
        RequestCreateFSM.waiting_location_geo,
        RequestCreateFSM.waiting_location_text,
        RequestCreateFSM.choosing_evacu_type,
        RequestCreateFSM.choosing_radius,
        RequestCreateFSM.entering_custom_radius,
        RequestCreateFSM.choosing_category,
        RequestCreateFSM.waiting_description,
        RequestCreateFSM.confirming_description,
        RequestCreateFSM.waiting_photos,
        RequestCreateFSM.confirming_hide_phone,
        RequestCreateFSM.choosing_car,
        RequestCreateFSM.choosing_work_mode,
    ),
    F.data == "req_create:cancel",
)
async def req_create_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Создание заявки отменено.")
    await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
    await callback.answer()
