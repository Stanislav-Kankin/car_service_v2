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
from ..states.user_states import STOEdit  # <-- добавили

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
    Клава выбора специализаций (регистрация).

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


def kb_specs_edit(selected: set[str]) -> InlineKeyboardMarkup:
    """
    Клава выбора специализаций при РЕДАКТИРОВАНИИ профиля СТО.
    """
    rows: list[list[InlineKeyboardButton]] = []

    for code, label in SERVICE_SPECIALIZATION_OPTIONS:
        mark = "✅ " if code in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{label}",
                    callback_data=f"sto_edit_spec:{code}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Готово",
                callback_data="sto_edit_spec:done",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ В меню СТО",
                callback_data="main:sto_menu",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Вспомогалки для меню СТО
# ---------------------------------------------------------------------------


def _format_specs_for_show(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, dict):
        return ", ".join(str(v) for v in raw.values())
    if isinstance(raw, list):
        return ", ".join(str(v) for v in raw)
    return str(raw)


def _build_sto_menu_text(sc: dict) -> str:
    name = sc.get("name") or "Без названия"
    city = sc.get("city") or ""
    address = sc.get("address") or ""
    specs_text = _format_specs_for_show(sc.get("specializations"))

    lines: list[str] = [
        "<b>🛠 Меню СТО</b>",
        "",
        f"<b>{name}</b>",
    ]
    if city or address:
        lines.append(f"📍 {city}, {address}".strip(", "))
    if specs_text:
        lines.append(f"🔧 Специализации: {specs_text}")

    lines.append("")
    lines.append("Выберите действие из меню ниже 👇")
    return "\n".join(lines)


def _build_sto_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать профиль",
                    callback_data="sto:edit_profile",
                )
            ],
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
async def sto_menu_entry(callback: CallbackQuery, state: FSMContext):
    """
    Вход в меню СТО из главного меню.
    Показываем краткую инфу по сервису и даём кнопки действий.
    """
    await state.clear()

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

    text = _build_sto_menu_text(sc)
    kb = _build_sto_menu_keyboard()

    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ---------------------------------------------------------------------------
# Редактирование профиля СТО
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "sto:edit_profile")
async def sto_edit_profile_start(callback: CallbackQuery, state: FSMContext):
    """
    Старт сценария редактирования профиля СТО.
    """
    telegram_id = callback.from_user.id

    # Берём текущий сервис через те же методы, что и в sto_menu_entry
    user = await api_client.get_user_by_telegram(telegram_id)
    if not isinstance(user, dict) or user.get("role") != "service_owner":
        await callback.message.answer(
            "Вы ещё не зарегистрированы как владелец автосервиса.\n"
            "Сначала зарегистрируйте СТО.",
        )
        await callback.answer()
        return

    user_id = user["id"]
    service_centers = await api_client.list_service_centers_by_user(user_id)
    if not isinstance(service_centers, list) or not service_centers:
        await callback.message.answer(
            "У вас пока нет зарегистрированных автосервисов.\n"
            "Сначала создайте профиль СТО.",
        )
        await callback.answer()
        return

    sc = service_centers[0]
    sc_id = sc.get("id")
    if not sc_id:
        await callback.message.answer(
            "Не удалось определить ID сервиса. Попробуйте позже."
        )
        await callback.answer()
        return

    # Сохраняем в состояние ID сервиса и текущие специализации
    specs_raw = sc.get("specializations") or []
    selected_specs: set[str] = {str(code) for code in specs_raw}

    await state.clear()
    await state.update_data(sc_id=int(sc_id), edit_specializations=selected_specs)

    text = (
        "<b>✏️ Редактирование профиля СТО</b>\n\n"
        "Выберите, что хотите изменить:"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📛 Название",
                    callback_data="sto_edit_field:name",
                ),
                InlineKeyboardButton(
                    text="📍 Адрес",
                    callback_data="sto_edit_field:address",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📌 Геолокация",
                    callback_data="sto_edit_field:geo",
                ),
                InlineKeyboardButton(
                    text="📞 Телефон",
                    callback_data="sto_edit_field:phone",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Сайт / соцсети",
                    callback_data="sto_edit_field:website",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔧 Специализации",
                    callback_data="sto_edit_field:specializations",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню СТО",
                    callback_data="main:sto_menu",
                ),
            ],
        ]
    )

    await callback.message.answer(text, reply_markup=kb)
    await state.set_state(STOEdit.choosing_field)
    await callback.answer()


@router.callback_query(STOEdit.choosing_field, F.data.startswith("sto_edit_field:"))
async def sto_edit_choose_field(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал, какое поле редактировать.
    """
    _, field = callback.data.split(":", maxsplit=1)

    if field in ("name", "address", "phone", "website"):
        prompts = {
            "name": "Введите новое <b>название сервиса</b>:",
            "address": "Введите новый <b>адрес сервиса</b> (строкой):",
            "phone": "Введите новый <b>контактный телефон</b>:",
            "website": (
                "Введите новый <b>сайт или ссылку на соцсети</b>.\n"
                "Если хотите очистить поле — напишите «пропустить»."
            ),
        }
        await state.update_data(edit_field=field)
        await callback.message.answer(prompts[field])
        await state.set_state(STOEdit.waiting_value)
        await callback.answer()
        return

    if field == "geo":
        await state.set_state(STOEdit.waiting_geo)
        await callback.message.answer(
            "Отправьте новую <b>геолокацию сервиса</b>.\n\n"
            "Используйте кнопку 📎 → «Геопозиция».",
            reply_markup=ReplyKeyboardRemove(),
        )
        await callback.answer()
        return

    if field == "specializations":
        data = await state.get_data()
        selected_specs: set[str] = set(data.get("edit_specializations") or [])
        await state.set_state(STOEdit.choosing_specs)
        await callback.message.answer(
            "Выберите актуальные специализации сервиса.\n\n"
            "Можно выбрать несколько пунктов, затем нажать «✅ Готово».",
            reply_markup=kb_specs_edit(selected_specs),
        )
        await callback.answer()
        return

    # На всякий случай
    await callback.answer()


@router.message(STOEdit.waiting_value)
async def sto_edit_save_text_value(message: Message, state: FSMContext):
    """
    Сохраняем текстовые значения: name, address, phone, website.
    """
    data = await state.get_data()
    sc_id = data.get("sc_id")
    field = data.get("edit_field")

    if not sc_id or field not in ("name", "address", "phone", "website"):
        await message.answer("Не удалось определить, что редактировать. Попробуйте ещё раз.")
        await state.clear()
        return

    text = (message.text or "").strip()

    # website можно очистить
    if field == "website" and text.lower() in ("пропустить", "нет", "-", "no"):
        value = None
    else:
        if not text:
            await message.answer("Значение не может быть пустым. Введите ещё раз.")
            return
        value = text

    payload = {field: value}

    try:
        await api_client.update_service_center(int(sc_id), payload)
        await message.answer("✔ Профиль СТО обновлён.")
    except Exception as e:
        logger.exception("Ошибка обновления профиля СТО (%s): %s", field, e)
        await message.answer("❌ Не удалось сохранить изменения. Попробуйте позже.")
        await state.clear()
        return

    # Покажем актуальное меню СТО
    try:
        sc = await api_client.get_service_center(int(sc_id))
        if isinstance(sc, dict):
            text = _build_sto_menu_text(sc)
            kb = _build_sto_menu_keyboard()
            await message.answer(text, reply_markup=kb)
    except Exception as e:
        logger.exception("Ошибка получения СТО после обновления: %s", e)

    await state.clear()


@router.message(STOEdit.waiting_geo, F.location)
async def sto_edit_save_geo(message: Message, state: FSMContext):
    """
    Сохраняем новые координаты сервиса.
    """
    data = await state.get_data()
    sc_id = data.get("sc_id")
    if not sc_id:
        await message.answer("Не удалось определить сервис. Попробуйте ещё раз.")
        await state.clear()
        return

    lat = message.location.latitude
    lon = message.location.longitude

    payload = {"latitude": lat, "longitude": lon}

    try:
        await api_client.update_service_center(int(sc_id), payload)
        await message.answer("✔ Геолокация сервиса обновлена.")
    except Exception as e:
        logger.exception("Ошибка обновления геолокации СТО: %s", e)
        await message.answer("❌ Не удалось сохранить геолокацию. Попробуйте позже.")
        await state.clear()
        return

    # Покажем актуальное меню СТО
    try:
        sc = await api_client.get_service_center(int(sc_id))
        if isinstance(sc, dict):
            text = _build_sto_menu_text(sc)
            kb = _build_sto_menu_keyboard()
            await message.answer(text, reply_markup=kb)
    except Exception as e:
        logger.exception("Ошибка получения СТО после обновления гео: %s", e)

    await state.clear()


@router.callback_query(STOEdit.choosing_specs)
async def sto_edit_specs(callback: CallbackQuery, state: FSMContext):
    """
    Выбор специализаций при редактировании профиля.
    """
    data = await state.get_data()
    sc_id = data.get("sc_id")
    if not sc_id:
        await callback.message.answer("Не удалось определить сервис. Попробуйте ещё раз.")
        await state.clear()
        await callback.answer()
        return

    selected: set[str] = set(data.get("edit_specializations") or [])

    if not callback.data.startswith("sto_edit_spec:"):
        await callback.answer()
        return

    _, code = callback.data.split(":", maxsplit=1)

    if code == "done":
        # Сохраняем специализации
        payload = {"specializations": list(selected)}
        try:
            await api_client.update_service_center(int(sc_id), payload)
            await callback.message.edit_text("✔ Специализации сервиса обновлены.")
        except Exception as e:
            logger.exception("Ошибка обновления специализаций СТО: %s", e)
            await callback.message.edit_text(
                "❌ Не удалось сохранить специализации. Попробуйте позже."
            )
            await state.clear()
            await callback.answer()
            return

        # Покажем актуальное меню СТО
        try:
            sc = await api_client.get_service_center(int(sc_id))
            if isinstance(sc, dict):
                text = _build_sto_menu_text(sc)
                kb = _build_sto_menu_keyboard()
                await callback.message.answer(text, reply_markup=kb)
        except Exception as e:
            logger.exception("Ошибка получения СТО после обновления спецов: %s", e)

        await state.clear()
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

    await state.update_data(edit_specializations=selected)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=kb_specs_edit(selected)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.exception("Ошибка обновления клавиатуры спецов (edit): %s", e)

    await callback.answer()


# ---------------------------------------------------------------------------
# Шаги регистрации СТО (оставляем как было)
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
    Выбор специализаций (регистрация).
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

            # ✅ НОВОЕ: нельзя подтверждать без выбранных специализаций
            if not specs_codes:
                await callback.answer("Выберите хотя бы одну специализацию", show_alert=True)
                # возвращаем пользователя к выбору, не переводим в confirm реально
                await state.set_state(STORegister.waiting_specs)
                await callback.answer()
                return

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
            if "message is not modified" not in str(e):
                logger.exception("Ошибка обновления клавиатуры спецов: %s", e)

        await callback.answer()
        return

    await callback.answer()


@router.callback_query(STORegister.waiting_confirm)
async def sto_finish(callback: CallbackQuery, state: FSMContext):
    """
    Финальный шаг: создаём СТО.
    ВАЖНО: роль пользователя НЕ меняем до модерации админом.
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
        # ✅ НОВОЕ: модерация — создаём неактивной
        "is_active": False,
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

    # ✅ НОВОЕ: роль НЕ меняем здесь. Её выставит админ при активации СТО.
    await state.clear()

    await callback.message.edit_text(
        "Заявка на регистрацию СТО отправлена на модерацию ✅\n\n"
        f"ID: {created.get('id')}\n"
        "Ожидайте подтверждения администратором.",
    )
    await callback.answer()
