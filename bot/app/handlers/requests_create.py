from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import logging

from aiogram import Router, F, Bot
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

    # 6a. Предпочтительный день/время
    waiting_preferred_day = State()
    waiting_preferred_time = State()

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
    ("🧼 Автомойка", "wash"),
    ("🛞 Шиномонтаж", "tire"),
    ("⚡ Автоэлектрик", "electric"),
    ("🔧 Слесарные работы", "mechanic"),
    ("🎨 Малярные / кузовные", "paint"),
    ("🛠️ ТО / обслуживание", "maint"),
    ("🌀 Турбины", "agg_turbo"),
    ("🔋 Стартеры", "agg_starter"),
    ("⚡ Генераторы", "agg_generator"),
    ("🛞 Рулевые рейки", "agg_steering"),
]


# Маппинг категорий заявки (SERVICE_CATEGORIES) на специализации СТО
# Ключи - коды в заявке, значения - коды специализаций СТО из SERVICE_SPECIALIZATION_OPTIONS
CATEGORY_TO_SPECIALIZATIONS: dict[str, list[str]] = {
    "mech": ["mechanic"],  # Автомеханика -> слесарные работы
    "tire": ["tire"],      # Шиномонтаж
    "elec": ["electric"],  # Автоэлектрик
    # Диагностика: часто либо электрика, либо механика, либо ТО
    "diag": ["electric", "mechanic", "maint"],
    # Кузовной ремонт
    "body": ["paint"],
    # Агрегатный ремонт - несколько типов агрегатов
    "agg": ["agg_turbo", "agg_starter", "agg_generator", "agg_steering"],
}

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
                    text="Неважно",
                    callback_data="req_radius:any",
                )
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


def kb_preferred_time() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="До 12:00",
                    callback_data="req_time:morning",
                )
            ],
            [
                InlineKeyboardButton(
                    text="12:00–18:00",
                    callback_data="req_time:day",
                )
            ],
            [
                InlineKeyboardButton(
                    text="После 18:00",
                    callback_data="req_time:evening",
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
    state: FSMContext,
    telegram_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Собирает данные из FSM и создаёт заявку через backend.
    Возвращает dict с заявкой или None при ошибке.
    """
    # 0. Получаем пользователя по telegram_id и берём его id из БД
    try:
        user = await api_client.get_user_by_telegram(telegram_id)
    except Exception:
        return None

    if not user or not user.get("id"):
        return None

    user_id = user["id"]

    data = await state.get_data()

    car_id = data.get("car_id")
    latitude = data.get("location_lat")
    longitude = data.get("location_lon")
    address_text = data.get("address_text")
    is_car_movable = data.get("is_car_movable", True)
    need_tow_truck = data.get("need_tow_truck", False)
    need_mobile_master = data.get("need_mobile_master", False)
    radius_km = data.get("search_radius_km")
    service_category = data.get("service_category")
    hide_phone = data.get("hide_phone", False)

    # базовое описание
    description = (data.get("description") or "").strip()

    # дополнительные поля: день/время — дописываем в текст
    preferred_day = (data.get("preferred_day") or "").strip() or None
    preferred_time_slot = data.get("preferred_time_slot")

    time_mapping = {
        "morning": "до 12:00",
        "day": "12:00–18:00",
        "evening": "после 18:00",
    }
    preferred_time_text = (
        time_mapping.get(preferred_time_slot, preferred_time_slot)
        if preferred_time_slot
        else None
    )

    extra_lines: list[str] = []
    if preferred_day:
        extra_lines.append(f"Предпочтительный день: {preferred_day}")
    if preferred_time_text:
        extra_lines.append(f"Предпочтительное время: {preferred_time_text}")

    if extra_lines:
        if description:
            description = description.rstrip() + "\n\n" + "\n".join(extra_lines)
        else:
            description = "\n".join(extra_lines)

    # фото (сохраняем один file_id как строку либо null)
    photo_file_id = data.get("photo_file_id")
    photos = None
    if photo_file_id:
        photos = [photo_file_id]

    payload = {
        "user_id": user_id,
        "car_id": car_id,
        "latitude": latitude,
        "longitude": longitude,
        "address_text": address_text,
        "is_car_movable": is_car_movable,
        "need_tow_truck": need_tow_truck,
        "need_mobile_master": need_mobile_master,
        "radius_km": radius_km,
        "service_category": service_category,
        "description": description,
        "photos": photos,
        "hide_phone": hide_phone,
        "preferred_day": data.get("preferred_day"),
        "preferred_time_range": data.get("preferred_time_range"),
    }

    try:
        created = await api_client.create_request(payload)
    except Exception:
        return None

    return created


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

    # «Неважно» — ищем по всей зоне, радиус не ограничиваем явно
    if value == "any":
        await state.update_data(radius_km=None)

        await state.set_state(RequestCreateFSM.choosing_category)
        await callback.message.edit_text(
            "Радиус: <b>неважно</b> — будем искать подходящие СТО без ограничения по расстоянию.\n\n"
            "Теперь выберите категорию услуги:",
            reply_markup=kb_categories(),
        )
        await callback.answer()
        return

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

    # Аналогично: записываем и radius_km, и search_radius_km
    await state.update_data(radius_km=radius, search_radius_km=radius)

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
    await state.set_state(RequestCreateFSM.waiting_preferred_day)
    await callback.message.edit_text(
        "Отлично 👍\n\n"
        "Теперь подскажите, <b>в какой день</b> вам удобно приехать в сервис "
        "или принять выездного мастера?\n\n"
        "Например:\n"
        "• сегодня\n"
        "• завтра\n"
        "• в понедельник\n"
        "• 10 декабря\n\n"
        "Напишите ответ <b>текстом</b>.",
        reply_markup=kb_cancel_only(),
    )
    await callback.answer()


@router.message(
    RequestCreateFSM.waiting_preferred_day,
    F.text,
)
async def req_preferred_day_received(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer(
            "Пожалуйста, укажите день чуть подробнее (например, «завтра», «в понедельник», «10 декабря»)."
        )
        return

    await state.update_data(preferred_day=text)
    await state.set_state(RequestCreateFSM.waiting_preferred_time)
    await message.answer(
        "Ок, записал день.\n\n"
        "А теперь выберите, <b>в какое время</b> вам удобнее:",
        reply_markup=kb_preferred_time(),
    )

@router.callback_query(
    StateFilter(RequestCreateFSM.waiting_preferred_time),
    F.data.startswith("req_time:"),
)
async def req_preferred_time_selected(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", maxsplit=1)[1]

    time_mapping = {
        "morning": "до 12:00",
        "day": "12:00–18:00",
        "evening": "после 18:00",
    }
    time_text = time_mapping.get(value)
    if not time_text:
        await callback.answer("Не удалось распознать вариант времени.")
        return

    await state.update_data(preferred_time_slot=value)
    data = await state.get_data()
    day_text = data.get("preferred_day") or "—"

    await state.set_state(RequestCreateFSM.waiting_photos)
    await callback.message.edit_text(
        f"Записал ваши пожелания по времени:\n\n"
        f"День: <b>{day_text}</b>\n"
        f"Время: <b>{time_text}</b>\n\n"
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
    request = await _create_request_from_state(state, callback.from_user.id)
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


async def _find_suitable_service_centers_for_request(
    request: Dict[str, Any],
    use_geo: bool = True,
) -> List[Dict[str, Any]]:
    """
    Подбираем подходящие СТО под заявку.

    Логика:
    - Всегда фильтруем по is_active=True.
    - По категории заявки берём специализации СТО через CATEGORY_TO_SPECIALIZATIONS.
    - Если use_geo=True и у заявки ЕСТЬ координаты:
        * используем их;
        * радиус берём из заявки, но не больше 400 км;
        * если радиуса нет — ставим 400 км по умолчанию.
    - Если use_geo=False или координат нет:
        * НЕ передаём latitude/longitude/radius_km → backend вернёт все СТО по профилю.
    """
    params: Dict[str, Any] = {"is_active": True}

    latitude = request.get("latitude")
    longitude = request.get("longitude")
    radius_km = request.get("radius_km")
    service_category = request.get("service_category")

    # Маппинг категории заявки -> специализации СТО
    spec_codes: Optional[List[str]] = None
    if service_category:
        spec_codes = CATEGORY_TO_SPECIALIZATIONS.get(service_category)
        # если вдруг категория новая и маппинга нет – пробуем хотя бы напрямую
        if not spec_codes:
            spec_codes = [service_category]

    if spec_codes:
        # backend ждёт specializations как строку через запятую
        params["specializations"] = ",".join(spec_codes)

    MAX_RADIUS_KM = 400

    # Гео-фильтр только если use_geo=True и координаты есть
    if (
        use_geo
        and latitude is not None
        and longitude is not None
    ):
        params["latitude"] = latitude
        params["longitude"] = longitude

        if not isinstance(radius_km, (int, float)) or radius_km <= 0:
            radius_km = MAX_RADIUS_KM

        radius_km = min(int(radius_km), MAX_RADIUS_KM)
        params["radius_km"] = radius_km

    try:
        sc_list = await api_client.list_service_centers(params=params)
        logging.info(
            "Found %s service centers for request %s (use_geo=%s)",
            len(sc_list),
            request.get("id"),
            use_geo,
        )
    except Exception as e:
        logging.exception(
            "Error while fetching service centers for request %s: %s",
            request.get("id"),
            e,
        )
        return []

    return sc_list or []


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_work_mode),
    F.data.in_(("req_work:list", "req_work:all")),
)
async def req_work_mode_selected(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал режим работы с СТО после создания заявки.

    Режимы:
    - req_work:list  — показываем список подходящих СТО, пользователь выбирает один
    - req_work:all   — отправляем заявку всем подходящим СТО

    Доп. логика:
    - Если в заданном радиусе никого не нашли, делаем фолбэк:
      ищем все подходящие СТО по профилю (без фильтра по гео).
    """
    data = await state.get_data()
    request_id = data.get("created_request_id")

    if not request_id:
        await state.clear()
        await callback.message.edit_text(
            "Не удалось найти созданную заявку. Попробуйте создать её заново."
        )
        await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
        await callback.answer()
        return

    # Берём актуальную заявку из backend
    try:
        request = await api_client.get_request(request_id)
    except Exception:
        request = None

    if not request:
        await state.clear()
        await callback.message.edit_text(
            "Не удалось загрузить данные заявки. Попробуйте позже."
        )
        await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
        await callback.answer()
        return

    mode = "list" if callback.data.endswith("list") else "all"

    # --- 1) Подбираем СТО: сначала в радиусе, потом фолбэк без гео ---
    used_fallback = False

    # Для режима "список" используем гео,
    # для режима "отправить всем" игнорируем координаты (шлём всем по профилю)
    use_geo = callback.data == "req_work:list"

    service_centers = await _find_suitable_service_centers_for_request(
        request,
        use_geo=use_geo,
    )

    # если никого не нашли, а в заявке есть гео — пробуем ещё раз без гео
    latitude = request.get("latitude")
    longitude = request.get("longitude")
    radius_km = request.get("radius_km")

    if not service_centers and latitude is not None and longitude is not None:
        request_no_geo = dict(request)
        request_no_geo.pop("latitude", None)
        request_no_geo.pop("longitude", None)
        request_no_geo.pop("radius_km", None)

        service_centers = await _find_suitable_service_centers_for_request(
            request_no_geo
        )
        if service_centers:
            used_fallback = True

    # если и после фолбэка пусто — честно говорим, что никого нет
    if not service_centers:
        await state.clear()
        await callback.message.edit_text(
            f"✅ Заявка <b>№{request_id}</b> создана.\n\n"
            "Но подходящих автосервисов по вашему профилю пока не нашлось.\n"
            "Попробуйте другой район или позже загляните в раздел «📄 Мои заявки»."
        )
        await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
        await callback.answer()
        return

    # --- 2) Ветка «📋 Выбрать СТО из списка» ---
    if mode == "list":
        lines: list[str] = [f"✅ Заявка <b>№{request_id}</b> создана.\n"]

        if used_fallback and radius_km:
            lines.append(
                f"В радиусе <b>{radius_km} км</b> подходящих автосервисов не нашли.\n"
                "Показаны сервисы подходящего профиля без ограничения по расстоянию.\n"
            )
        else:
            lines.append("Нашли несколько подходящих автосервисов:\n")

        for idx, sc in enumerate(service_centers[:10], start=1):
            name = sc.get("name") or "Без названия"
            city = sc.get("city") or ""
            address = sc.get("address_text") or ""

            line_parts = [name]
            if city:
                line_parts.append(city)
            if address:
                line_parts.append(address)

            line = f"{idx}. " + " — ".join(line_parts)
            lines.append(line)

        lines.append("\nВыберите нужный сервис из списка ниже 👇")

        text = "\n".join(lines)

        # остаёмся в состоянии choosing_work_mode,
        # т.к. обработчик выбора СТО ждёт его же (req_service_center_selected)
        await callback.message.edit_text(
            text,
            reply_markup=_build_service_centers_keyboard(service_centers),
        )
        await callback.answer()
        return

    # --- 3) Ветка «📡 Отправить всем подходящим» ---
    sent_count = 0
    try:
        sent_count = await _notify_services_about_request(
            bot=callback.message.bot,
            request=request,
            service_centers=service_centers,
        )
    except Exception:
        # не валим сценарий, просто считаем, что никому не отправили
        sent_count = 0

    if used_fallback and radius_km:
        radius_info = (
            f"В радиусе <b>{radius_km} км</b> подходящих автосервисов не нашли.\n"
            "Заявка отправлена в сервисы подходящего профиля без ограничения по расстоянию.\n\n"
        )
    else:
        radius_info = ""

    if sent_count > 0:
        text = (
            f"✅ Заявка <b>№{request_id}</b> создана и отправлена "
            f"в <b>{sent_count}</b> подходящих автосервисов.\n\n"
            f"{radius_info}"
            "Как только сервисы ответят, их предложения появятся в разделе «📄 Мои заявки»."
        )
    else:
        text = (
            f"✅ Заявка <b>№{request_id}</b> создана.\n\n"
            f"{radius_info}"
            "Однако не удалось отправить уведомления автосервисам.\n"
            "Попробуйте позже или свяжитесь с поддержкой."
        )

    await state.clear()
    await callback.message.edit_text(text)
    await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
    await callback.answer()

    # ───────────────────────────────────────────────────────────
    # Ветка «📋 Выбрать СТО из списка» (пока без клика по конкретному СТО)
    # ───────────────────────────────────────────────────────────
    if callback.data.endswith("list"):
        # Сначала пытаемся по гео
        near_sc = await _find_suitable_service_centers_for_request(
            request=request,
            api_client=api_client,
            use_geo=True,
        )

        # Если по гео пусто — пробуем без гео, только по профилю
        if not near_sc:
            any_sc = await _find_suitable_service_centers_for_request(
                request=request,
                api_client=api_client,
                use_geo=False,
            )
        else:
            any_sc = near_sc

        if not any_sc:
            await state.clear()
            await callback.message.edit_text(
                f"✅ Заявка <b>№{request_id}</b> создана.\n\n"
                "Но подходящих автосервисов по вашему профилю пока не нашлось.\n"
                "Попробуйте другой район или позже загляните в раздел «📄 Мои заявки»."
            )
            await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
            await callback.answer()
            return

        # Пока просто показываем пользователю список названий/адресов без выбора
        lines = []
        for sc in any_sc:
            name = sc.get("name") or "Без названия"
            city = sc.get("city") or ""
            address = sc.get("address") or ""
            line = f"• {name}"
            if city or address:
                line += f" — {city}, {address}".strip(" ,")
            lines.append(line)

        text = (
            f"✅ Заявка <b>№{request_id}</b> создана.\n\n"
            "Подходящие автосервисы по вашему профилю:\n\n"
            + "\n".join(lines)
            + "\n\n"
            "На следующем этапе доработаем выбор конкретного сервиса из списка.\n"
            "Пока вы можете отслеживать статус заявки в разделе «📄 Мои заявки»."
        )

        await state.clear()
        await callback.message.edit_text(text)
        await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
        await callback.answer()
        return

    # ───────────────────────────────────────────────────────────
    # Ветка «📡 Отправить всем подходящим»
    # ───────────────────────────────────────────────────────────
    if callback.data.endswith("all"):
        # Фактически рассылка сейчас уже делается на этапе создания заявки
        # через _notify_services_about_request (чтобы не ломать старую логику).
        # Здесь просто аккуратно завершаем сценарий.
        await state.clear()
        await callback.message.edit_text(
            f"✅ Заявка <b>№{request_id}</b> создана и отправлена подходящим автосервисам.\n\n"
            "Вы можете отслеживать отклики в разделе «📄 Мои заявки»."
        )
        await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
        await callback.answer()
        return


async def _notify_services_about_request(
    bot: Bot,
    request: Dict[str, Any],
    service_centers: List[Dict[str, Any]],
) -> int:
    """
    Рассылаем уведомление о новой заявке всем найденным СТО
    И фиксируем распределение заявки в backend (RequestDistribution).
    """
    sent_count = 0
    sent_sc_ids: List[int] = []

    request_id = request.get("id")
    desc = (request.get("description") or "").strip() or "Описание не указано"
    addr = (request.get("address_text") or "").strip() or "Адрес не указан"

    # Инфа по машине (если есть)
    car_info = ""
    car = request.get("car")
    if isinstance(car, dict):
        brand = (car.get("brand") or "").strip()
        model = (car.get("model") or "").strip()
        if brand or model:
            car_info = f"{brand} {model}".strip()

    # Телеграм клиента (для кнопки "Написать клиенту")
    client_tg_id: Optional[int] = None
    user_id = request.get("user_id")
    if user_id:
        try:
            user = await api_client.get_user(int(user_id))
            if isinstance(user, dict):
                client_tg_id = user.get("telegram_id")
        except Exception as e:
            logging.exception(
                "Не удалось получить данные клиента для заявки %s: %s",
                request_id,
                e,
            )

    base_title = (
        f"📥 Новая заявка №{request_id:04d}"
        if request_id is not None
        else "📥 Новая заявка"
    )

    for sc in service_centers:
        try:
            sc_id = sc.get("id")
            if not sc_id:
                continue

            owner_user_id = sc.get("user_id")
            if not owner_user_id:
                continue

            # находим владельца СТО и его telegram_id
            try:
                owner = await api_client.get_user(int(owner_user_id))
            except Exception as e:
                logging.exception("Не удалось получить данные владельца СТО: %s", e)
                continue

            if not isinstance(owner, dict):
                continue

            tg_id = owner.get("telegram_id")
            if not tg_id:
                continue

            sc_name = (sc.get("name") or "").strip() or f"Автосервис #{sc_id}"

            text_lines = [
                base_title,
                "",
                f"<b>Автосервис:</b> {sc_name}",
            ]
            if car_info:
                text_lines.append(f"<b>Автомобиль:</b> {car_info}")
            text_lines.append(f"<b>Адрес/место:</b> {addr}")
            text_lines.append("")
            text_lines.append("<b>Описание проблемы:</b>")
            text_lines.append(desc)
            text_lines.append("")
            text_lines.append(
                "Чтобы отправить клиенту условия (цена, срок, комментарий), "
                "нажмите кнопку ниже и напишите одно сообщение."
            )

            base_text = "\n".join(text_lines)

            # --- Кнопки под заявкой для СТО ---
            first_row: List[InlineKeyboardButton] = [
                InlineKeyboardButton(
                    text="✉️ Ответить на заявку",
                    callback_data=f"sto:req_view:{request_id}",
                )
            ]

            # Если знаем Telegram клиента — добавляем кнопку "Написать клиенту"
            if client_tg_id:
                first_row.append(
                    InlineKeyboardButton(
                        text="💬 Написать клиенту",
                        url=f"tg://user?id={client_tg_id}",
                    )
                )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    first_row,
                    [
                        InlineKeyboardButton(
                            text="📥 Все заявки клиентов",
                            callback_data="sto:req_list",
                        )
                    ],
                ]
            )

            # 1) сообщение с текстом и кнопками
            await bot.send_message(chat_id=tg_id, text=base_text, reply_markup=kb)

            # 2) если у заявки есть сохранённые фото – отправим и их
            photos: List[str] = request.get("photos") or []
            for file_id in photos:
                try:
                    await bot.send_photo(chat_id=tg_id, photo=file_id)
                except Exception:
                    # фото не критичны, не роняем сценарий
                    pass

            sent_count += 1
            sent_sc_ids.append(int(sc_id))

        except Exception as e:
            logging.exception("Ошибка при отправке заявки в СТО: %s", e)
            continue

    # После успешной рассылки фиксируем распределение заявки по СТО в backend
    if request_id and sent_sc_ids:
        try:
            await api_client.distribute_request(int(request_id), sent_sc_ids)
        except Exception as e:
            logging.exception(
                "Не удалось зафиксировать распределение заявки %s по СТО %s: %s",
                request_id,
                sent_sc_ids,
                e,
            )

    return sent_count


@router.callback_query(
    StateFilter(RequestCreateFSM.choosing_work_mode),
    F.data.startswith("req_sc:"),
)
async def req_service_center_selected(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал конкретный автосервис из списка.
    Фиксируем его в заявке и отправляем заявку этому сервису.
    """
    fsm_data = await state.get_data()
    # Исправляем ключ: мы сохраняли created_request_id после создания заявки
    request_id = fsm_data.get("created_request_id")

    if not request_id:
        await callback.message.answer(
            "Не удалось связать выбор сервиса с заявкой. "
            "Попробуйте создать заявку заново.",
        )
        await state.clear()
        await callback.answer()
        return

    try:
        _, sc_id_str = callback.data.split(":", maxsplit=1)
        service_center_id = int(sc_id_str)
    except (ValueError, IndexError):
        await callback.answer()
        return

    # Обновляем заявку: привязываем выбранный сервис и переводим в статус "sent"
        # Обновляем заявку: привязываем выбранный сервис и переводим в статус "sent"
    try:
        await api_client.update_request(
            request_id,
            {
                "status": "sent",
                "distribution_mode": "select",
                "service_center_id": service_center_id,
            },
        )
    except Exception:
        await callback.message.answer(
            "Не получилось отправить заявку в выбранный сервис. Попробуйте позже.",
        )
        await state.clear()
        await callback.answer()
        return

    # Фиксируем распределение заявки: она отправлена КОНКРЕТНО этому СТО
    try:
        await api_client.distribute_request(
            request_id,
            [service_center_id],
        )
    except Exception as e:
        logging.exception(
            "Не удалось зафиксировать распределение заявки %s для СТО %s: %s",
            request_id,
            service_center_id,
            e,
        )

    # Пытаемся уведомить выбранное СТО так же, как в режиме «отправить всем»
    try:
        request = await api_client.get_request(request_id)
    except Exception:
        request = None

    service_center = None
    try:
        service_center_data = await api_client.get_service_center(service_center_id)
        if isinstance(service_center_data, dict):
            service_center = service_center_data
    except Exception:
        service_center = None

    if request and service_center:
        try:
            await _notify_services_about_request(
                bot=callback.message.bot,
                request=request,
                service_centers=[service_center],
            )
        except Exception:
            # Не роняем сценарий, если уведомление не дошло
            pass

    await callback.message.edit_text(
        f"✅ Заявка <b>№{request_id}</b> отправлена в выбранный автосервис.\n\n"
        "Как только сервис ответит, его предложение появится в разделе «📄 Мои заявки».",
    )

    await state.clear()
    await _back_to_main_menu(callback.message, telegram_id=callback.from_user.id)
    await callback.answer()


# ---------- Подбор подходящих СТО ----------

async def _find_suitable_service_centers(fsm_data: dict) -> list[dict]:
    """
    Подбираем СТО по данным заявки.
    Здесь мы просто прокидываем параметры в backend,
    а фильтрацию делаем там.
    """
    params: dict[str, object] = {}

    service_category = fsm_data.get("service_category")
    if service_category:
        params["service_category"] = service_category

    # флаги эвакуатор / выездной мастер (если были собраны при создании заявки)
    if fsm_data.get("need_tow_truck"):
        params["has_tow_truck"] = True
    if fsm_data.get("need_mobile_master"):
        params["has_mobile_service"] = True

    # гео + радиус (если есть)
    lat = fsm_data.get("location_lat")
    lon = fsm_data.get("location_lon")
    radius_km = fsm_data.get("search_radius_km")
    if lat is not None and lon is not None and radius_km:
        params["latitude"] = lat
        params["longitude"] = lon
        params["radius_km"] = radius_km

    try:
        service_centers = await api_client.list_service_centers(params=params or None)
    except Exception:  # на всякий случай не валим бота
        import logging
        logging.exception("Не удалось получить список СТО для заявки")
        service_centers = []

    # backend может вернуть что угодно, нам достаточно списка dict-ов
    return list(service_centers or [])


def _build_service_centers_keyboard(service_centers: list[dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора СТО для режима «Выбрать из списка».
    callback_data: req_sc:<service_center_id>
    """
    buttons: list[list[InlineKeyboardButton]] = []

    for sc in service_centers[:10]:  # не спамим, максимум 10 штук
        sc_id = sc.get("id")
        name = sc.get("name") or "Без названия"
        city = sc.get("city") or ""
        address = sc.get("address_text") or ""

        title_parts = [name]
        if city:
            title_parts.append(city)
        if address:
            title_parts.append(address)

        title = " — ".join(title_parts)

        if sc_id is None:
            continue

        buttons.append([
            InlineKeyboardButton(
                text=title[:64],  # ограничим длину подписи
                callback_data=f"req_sc:{sc_id}",
            )
        ])

    # строка "Назад / Отмена"
    buttons.append([
        InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="req_create:cancel",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
        RequestCreateFSM.waiting_preferred_day,
        RequestCreateFSM.waiting_preferred_time,
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
