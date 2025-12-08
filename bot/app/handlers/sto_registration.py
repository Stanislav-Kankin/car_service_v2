import logging

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from ..api_client import api_client

router = Router()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FSM регистрации СТО
# ---------------------------------------------------------------------------


class STORegister(StatesGroup):
    waiting_org_type = State()
    waiting_name = State()
    waiting_address_text = State()
    waiting_geo = State()
    waiting_phone = State()
    waiting_website = State()
    waiting_specs = State()
    waiting_confirm = State()


# ---------------------------------------------------------------------------
# Список специализаций (максимально близко к v1)
# код -> подпись
# ---------------------------------------------------------------------------

SERVICE_SPECIALIZATION_OPTIONS: list[tuple[str, str]] = [
    ("wash", "🧼 Автомойка"),
    ("tire", "🛞 Шиномонтаж"),
    ("electric", "⚡ Автоэлектрик"),
    ("mechanic", "🔧 Слесарные работы"),
    ("paint", "🎨 Малярные / кузовные"),
    ("maint", "🛠️ ТО / обслуживание"),
    ("agg_turbo", "🌀 Турбины"),
    ("agg_starter", "🔋 Стартеры"),
    ("agg_generator", "⚡ Генераторы"),
    ("agg_steering", "🛞 Рулевые рейки"),
]


# ---------------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------------


def kb_org_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ФЛ / Частный мастер",
                    callback_data="sto_type_ind",
                )
            ],
            [
                InlineKeyboardButton(
                    text="ЮЛ / Автосервис",
                    callback_data="sto_type_comp",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="sto_back_menu",
                )
            ],
        ]
    )


def kb_specs(selected: set[str]) -> InlineKeyboardMarkup:
    """
    Клава выбора специализаций.

    selected — множество кодов из SERVICE_SPECIALIZATION_OPTIONS.
    """
    rows: list[list[InlineKeyboardButton]] = []

    for code, label in SERVICE_SPECIALIZATION_OPTIONS:
        mark = "✅ " if code in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{label}",
                    callback_data=f"sto_spec:{code}",
                )
            ]
        )

    # Управляющие кнопки
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Готово",
                callback_data="sto_spec:done",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="sto_spec:cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Общий старт регистрации
# ---------------------------------------------------------------------------


async def _start_sto_registration(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(STORegister.waiting_org_type)
    await message.answer(
        "Регистрация автосервиса.\n\n"
        "Выберите тип организации:",
        reply_markup=kb_org_type(),
    )


# Старый вход (если ещё где-то остался)
@router.callback_query(F.data == "menu_service")
async def sto_start_legacy(callback: CallbackQuery, state: FSMContext):
    await _start_sto_registration(callback.message, state)
    await callback.answer()


# Новый вход из главного меню (кнопка «🔧 Зарегистрировать СТО»)
@router.callback_query(F.data == "main:sto_register")
async def sto_start_from_main(callback: CallbackQuery, state: FSMContext):
    await _start_sto_registration(callback.message, state)
    await callback.answer()


# ---------------------------------------------------------------------------
# Меню СТО (для уже зарегистрированных владельцев)
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "main:sto_menu")
async def sto_menu_entry(callback: CallbackQuery):
    """
    Вход в меню СТО из главного меню.
    Показываем краткую инфу по сервису и даём кнопки действий.
    """
    telegram_id = callback.from_user.id

    # 1. Получаем пользователя по Telegram ID
    user = await api_client.get_user_by_telegram(telegram_id)
    if not isinstance(user, dict) or user.get("role") != "service_owner":
        await callback.message.answer(
            "Похоже, вы ещё не зарегистрированы как владелец автосервиса.\n"
            "Перейдите в раздел «Регистрация СТО» в главном меню.",
        )
        await callback.answer()
        return

    user_id = user["id"]

    # 2. Ищем СТО, привязанные к пользователю
    service_centers = await api_client.list_service_centers_by_user(user_id)
    if not isinstance(service_centers, list) or not service_centers:
        await callback.message.answer(
            "У вас пока нет зарегистрированных автосервисов.\n"
            "Зайдите в раздел «Регистрация СТО», чтобы создать профиль.",
        )
        await callback.answer()
        return

    sc = service_centers[0]  # пока берём первый сервис

    name = sc.get("name") or "Без названия"
    city = sc.get("city") or ""
    address = sc.get("address") or ""
    specializations = sc.get("specializations") or []

    if isinstance(specializations, dict):
        specs_text = ", ".join(str(v) for v in specializations.values())
    elif isinstance(specializations, list):
        specs_text = ", ".join(str(v) for v in specializations)
    else:
        specs_text = str(specializations)

    text_lines = [
        "<b>🛠 Меню СТО</b>",
        "",
        f"<b>{name}</b>",
    ]
    if city or address:
        text_lines.append(f"📍 {city}, {address}".strip(", "))
    if specs_text:
        text_lines.append(f"🔧 Специализации: {specs_text}")

    text_lines.append("")
    text_lines.append("Выберите действие из меню ниже 👇")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📥 Заявки клиентов",
                    callback_data="sto:req_list",
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

    await callback.message.answer("\n".join(text_lines), reply_markup=kb)
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаги регистрации СТО
# ---------------------------------------------------------------------------


@router.callback_query(STORegister.waiting_org_type)
async def sto_org_type(callback: CallbackQuery, state: FSMContext):
    """
    Выбор типа организации.
    """
    if callback.data == "sto_back_menu":
        await state.clear()
        await callback.message.edit_text("Регистрация СТО отменена.")
        await callback.answer()
        return

    if callback.data not in ("sto_type_ind", "sto_type_comp"):
        await callback.answer()
        return

    org_type = "individual" if callback.data == "sto_type_ind" else "company"
    await state.update_data(org_type=org_type)

    await state.set_state(STORegister.waiting_name)
    await callback.message.edit_text(
        "Введите название сервиса.\n"
        "Если вы частный мастер — укажите ваше имя.",
    )
    await callback.answer()


@router.message(STORegister.waiting_name, F.text)
async def sto_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Введите название сервиса, пожалуйста.")
        return

    await state.update_data(name=name)
    await state.set_state(STORegister.waiting_address_text)
    await message.answer("Введите адрес сервиса (строкой).")


@router.message(STORegister.waiting_address_text, F.text)
async def sto_address(message: Message, state: FSMContext):
    addr = (message.text or "").strip()
    if not addr:
        await message.answer("Введите адрес строкой.")
        return

    await state.update_data(address_text=addr)
    await state.set_state(STORegister.waiting_geo)
    await message.answer(
        "Теперь отправьте геолокацию сервиса.\n\n"
        "Используйте кнопку 📎 → «Геопозиция».",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(STORegister.waiting_geo, F.location)
async def sto_geo(message: Message, state: FSMContext):
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await state.set_state(STORegister.waiting_phone)
    await message.answer("Введите контактный телефон сервиса.")


@router.message(STORegister.waiting_phone, F.text)
async def sto_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if not phone:
        await message.answer("Введите телефон сервиса.")
        return

    await state.update_data(phone=phone)
    await state.set_state(STORegister.waiting_website)
    await message.answer(
        "Введите сайт или ссылку на соцсети.\n"
        "Если сайта нет — напишите «пропустить».",
    )


@router.message(STORegister.waiting_website, F.text)
async def sto_website(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    website = None if txt.lower() in ("пропустить", "нет", "-", "no") else txt

    await state.update_data(website=website)
    await state.update_data(specializations=set())

    await state.set_state(STORegister.waiting_specs)
    await message.answer(
        "Выберите специализации сервиса:\n\n"
        "Можно выбрать несколько пунктов, потом нажать «✅ Готово».",
        reply_markup=kb_specs(set()),
    )


@router.callback_query(STORegister.waiting_specs)
async def sto_specs(callback: CallbackQuery, state: FSMContext):
    """
    Выбор специализаций.
    """
    data = await state.get_data()
    selected: set[str] = set(data.get("specializations") or [])

    if callback.data.startswith("sto_spec:"):
        _, code = callback.data.split(":", maxsplit=1)

        # Отмена
        if code == "cancel":
            await state.clear()
            await callback.message.edit_text("Регистрация СТО отменена.")
            await callback.answer()
            return

        # Готово -> переход к подтверждению
        if code == "done":
            await state.set_state(STORegister.waiting_confirm)
            profile = await state.get_data()
            specs_codes: set[str] = set(profile.get("specializations") or [])

            # человек мог вообще ничего не выбрать
            if not specs_codes:
                specs_text = "— (специализации не выбраны)"
            else:
                labels = []
                for c, lbl in SERVICE_SPECIALIZATION_OPTIONS:
                    if c in specs_codes:
                        labels.append(lbl)
                specs_text = ", ".join(labels) if labels else "—"

            text = (
                "Проверьте данные:\n\n"
                f"Тип: {profile.get('org_type')}\n"
                f"Название: {profile.get('name')}\n"
                f"Адрес: {profile.get('address_text')}\n"
                f"Телефон: {profile.get('phone')}\n"
                f"Сайт: {profile.get('website') or '—'}\n"
                f"Специализации: {specs_text}\n\n"
                "Подтвердить регистрацию?"
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Подтвердить",
                            callback_data="sto_reg_yes",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data="sto_reg_no",
                        )
                    ],
                ]
            )

            await callback.message.edit_text(text, reply_markup=kb)
            await callback.answer()
            return

        # Обычное переключение специализации
        codes_available = {c for c, _ in SERVICE_SPECIALIZATION_OPTIONS}
        if code not in codes_available:
            await callback.answer()
            return

        if code in selected:
            selected.remove(code)
        else:
            selected.add(code)

        await state.update_data(specializations=selected)

        try:
            await callback.message.edit_reply_markup(
                reply_markup=kb_specs(selected)
            )
        except TelegramBadRequest as e:
            # Игнорируем "message is not modified"
            if "message is not modified" not in str(e):
                logger.exception("Ошибка обновления клавиатуры спецов: %s", e)

        await callback.answer()
        return

    # Остальное игнорируем
    await callback.answer()


@router.callback_query(STORegister.waiting_confirm)
async def sto_finish(callback: CallbackQuery, state: FSMContext):
    """
    Финальный шаг: создаём СТО и меняем роль пользователя.
    """
    if callback.data == "sto_reg_no":
        await state.clear()
        await callback.message.edit_text("Регистрация СТО отменена.")
        await callback.answer()
        return

    if callback.data != "sto_reg_yes":
        await callback.answer()
        return

    data = await state.get_data()
    tg_id = callback.from_user.id

    try:
        user = await api_client.get_user_by_telegram(tg_id)
    except Exception as e:
        logger.exception("Ошибка запроса пользователя при регистрации СТО: %s", e)
        await callback.message.edit_text(
            "Не удалось получить данные пользователя 😔\n"
            "Попробуйте ещё раз с команды /start."
        )
        await callback.answer()
        return

    if not user:
        await callback.message.edit_text(
            "Пользователь не найден в системе.\n"
            "Сначала завершите регистрацию как клиента через /start."
        )
        await callback.answer()
        return

    user_id = user["id"]

    # Переводим выбранные спец-коды в список строк (так же, как в v1)
    specs_codes: set[str] = set(data.get("specializations") or [])
    specializations = list(specs_codes)

    payload = {
        "user_id": user_id,
        "org_type": data.get("org_type"),
        "name": data.get("name"),
        "address": data.get("address_text"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "phone": data.get("phone"),
        "website": data.get("website"),
        "specializations": specializations,
    }

    try:
        created = await api_client.create_service_center(payload)
    except Exception as e:
        logger.exception("Ошибка регистрации СТО: %s", e)
        await callback.message.edit_text(
            "Не удалось зарегистрировать СТО 😔 Попробуйте позже."
        )
        await callback.answer()
        return

    # Обновляем роль пользователя
    try:
        await api_client.update_user(user_id, {"role": "service_owner"})
    except Exception as e:
        logger.exception(
            "Не удалось обновить роль пользователя до service_owner: %s", e
        )

    await state.clear()

    await callback.message.edit_text(
        f"СТО зарегистрировано успешно! 🎉\n\n"
        f"ID: {created.get('id')}\n"
        "Теперь вам доступно «🛠 Меню СТО» в главном меню.",
    )
    await callback.answer()
