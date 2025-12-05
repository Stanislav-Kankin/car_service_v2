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


# -------------------------------------------------
# FSM регистрации СТО
# -------------------------------------------------


class STORegister(StatesGroup):
    waiting_org_type = State()
    waiting_name = State()
    waiting_address_text = State()
    waiting_geo = State()
    waiting_phone = State()
    waiting_website = State()
    waiting_specs = State()
    waiting_confirm = State()


# -------------------------------------------------
# Клавиатуры
# -------------------------------------------------


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


def kb_specs(selected: list[str]) -> InlineKeyboardMarkup:
    all_specs = [
        ("Автомеханика", "mech"),
        ("Шиномонтаж", "tire"),
        ("Электрика", "elec"),
        ("Диагностика", "diag"),
        ("Кузовной", "body"),
        ("Агрегатный ремонт", "agg"),
    ]

    rows: list[list[InlineKeyboardButton]] = []
    for title, key in all_specs:
        mark = "✅ " if key in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{title}",
                    callback_data=f"sto_spec_{key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="Готово",
                callback_data="sto_spec_ok",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# -------------------------------------------------
# Старт регистрации
# -------------------------------------------------


async def _start_sto_registration(message: Message, state: FSMContext):
    """
    Общая логика старта регистрации СТО.
    Используем и из старого callback, и из нового main:sto_register.
    """
    await state.clear()
    await state.set_state(STORegister.waiting_org_type)
    await message.edit_text(
        "Регистрация автосервиса.\n\nВыберите тип организации:",
        reply_markup=kb_org_type(),
    )


@router.callback_query(F.data == "menu_service")
async def sto_start_legacy(call: CallbackQuery, state: FSMContext):
    """
    Старый вход (menu_service), оставляем для совместимости.
    """
    await _start_sto_registration(call.message, state)
    await call.answer()


@router.callback_query(F.data == "main:sto_register")
async def sto_start_from_main(call: CallbackQuery, state: FSMContext):
    """
    Новый вход из главного меню:
    кнопка "🔧 Зарегистрировать СТО" для клиентов.
    """
    await _start_sto_registration(call.message, state)
    await call.answer()


# -------------------------------------------------
# Меню СТО
# -------------------------------------------------


@router.callback_query(F.data == "main:sto_menu")
async def sto_menu_entry(callback: CallbackQuery):
    """
    Вход в раздел СТО из главного инлайн-меню.

    Для владельца СТО показываем его сервис (пока без редактирования).
    Если сервисов нет — подсказываем про регистрацию.
    """
    tg_id = callback.message.chat.id

    try:
        user = await api_client.get_user_by_telegram(tg_id)
    except Exception as e:
        logger.exception("Ошибка запроса пользователя в Меню СТО: %s", e)
        await callback.message.answer(
            "Не удалось получить данные пользователя 😔\n"
            "Попробуйте ещё раз с команды /start."
        )
        await callback.answer()
        return

    if not user:
        await callback.message.answer(
            "Пользователь не найден в системе.\n"
            "Сначала пройдите регистрацию через /start."
        )
        await callback.answer()
        return

    if user.get("role") != "service_owner":
        await callback.message.answer(
            "Раздел СТО доступен только владельцам автосервисов.\n\n"
            "Если вы хотите подключить свой сервис и получать заявки от клиентов, "
            "используйте кнопку «🔧 Зарегистрировать СТО» в главном меню."
        )
        await callback.answer()
        return

    # Пользователь – владелец СТО, получаем привязанные сервисы
    try:
        sc_list = await api_client.list_service_centers_by_user(user["id"])
    except Exception as e:
        logger.exception("Ошибка получения списка СТО: %s", e)
        await callback.message.answer(
            "Не удалось получить данные СТО 😔\n"
            "Попробуйте чуть позже."
        )
        await callback.answer()
        return

    if not sc_list:
        await callback.message.answer(
            "У вас ещё нет зарегистрированного автосервиса.\n\n"
            "Нажмите «🔧 Зарегистрировать СТО» в главном меню, "
            "чтобы создать профиль сервиса и начать получать заявки."
        )
        await callback.answer()
        return

    # Пока берём первый сервис (в будущем поддержим несколько)
    sc = sc_list[0]

    specs = sc.get("specializations") or []
    specs_text = ", ".join(specs) if specs else "—"

    text = (
        "Ваш автосервис:\n\n"
        f"Название: {sc.get('name') or '—'}\n"
        f"Адрес: {sc.get('address') or '—'}\n"
        f"Телефон: {sc.get('phone') or '—'}\n"
        f"Сайт: {sc.get('website') or '—'}\n"
        f"Специализации: {specs_text}\n\n"
        "Позже здесь добавим редактирование профиля и управление заявками."
    )

    await callback.message.answer(text)
    await callback.answer()


# -------------------------------------------------
# Тип организации
# -------------------------------------------------


@router.callback_query(STORegister.waiting_org_type)
async def sto_org_type(call: CallbackQuery, state: FSMContext):
    """
    Обработка выбора типа организации для регистрации СТО.
    """
    # Разрешаем только наши callback-и
    if call.data not in ("sto_type_ind", "sto_type_comp", "sto_back_menu"):
        await call.answer()
        return

    # Кнопка "⬅️ В меню"
    if call.data == "sto_back_menu":
        await state.clear()
        await call.message.edit_text("Регистрация СТО отменена.")
        await call.answer()
        return

    # Сохраняем выбранный тип
    org_type = "individual" if call.data == "sto_type_ind" else "company"
    await state.update_data(org_type=org_type)

    # Переходим к следующему шагу — ввод названия
    await state.set_state(STORegister.waiting_name)
    await call.message.edit_text(
        "Введите название сервиса.\n"
        "Если вы частный мастер — укажите ваше имя."
    )
    await call.answer()


# -------------------------------------------------
# Название
# -------------------------------------------------


@router.message(STORegister.waiting_name, F.text)
async def sto_name(message: Message, state: FSMContext):
    """
    Ввод названия сервиса для регистрации СТО.
    """
    name = (message.text or "").strip()
    if not name:
        await message.answer("Введите название сервиса, пожалуйста.")
        return

    await state.update_data(name=name)
    await state.set_state(STORegister.waiting_address_text)
    await message.answer("Введите адрес сервиса (строкой).")


# -------------------------------------------------
# Адрес текстом
# -------------------------------------------------


@router.message(STORegister.waiting_address_text, F.text)
async def sto_addr(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt:
        await message.answer("Введите адрес строкой.")
        return

    await state.update_data(address_text=txt)
    await state.set_state(STORegister.waiting_geo)
    await message.answer(
        "Отправьте геолокацию сервиса.",
        reply_markup=ReplyKeyboardRemove(),
    )


# -------------------------------------------------
# Геолокация
# -------------------------------------------------


@router.message(STORegister.waiting_geo, F.location)
async def sto_geo(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude

    await state.update_data(latitude=lat, longitude=lon)
    await state.set_state(STORegister.waiting_phone)
    await message.answer("Введите телефон сервиса.")


# -------------------------------------------------
# Телефон
# -------------------------------------------------


@router.message(STORegister.waiting_phone, F.text)
async def sto_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    await state.update_data(phone=phone)

    await state.set_state(STORegister.waiting_website)
    await message.answer("Введите сайт или соцсети (или напишите «Пропустить»).")


# -------------------------------------------------
# Сайт / соцсети
# -------------------------------------------------


@router.message(STORegister.waiting_website, F.text)
async def sto_site(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    website = None if txt.lower() in ("пропустить", "-", "skip") else txt
    await state.update_data(website=website)

    await state.update_data(specializations=[])
    await state.set_state(STORegister.waiting_specs)
    await message.answer(
        "Выберите специализации:",
        reply_markup=kb_specs([]),
    )


# -------------------------------------------------
# Выбор спецов
# -------------------------------------------------


@router.callback_query(STORegister.waiting_specs)
async def sto_specs(call: CallbackQuery, state: FSMContext):
    """
    Выбор специализаций для СТО.
    """
    data = await state.get_data()
    selected = data.get("specializations", [])

    # Клик по конкретной специализации
    if call.data.startswith("sto_spec_"):
        key = call.data.split("_", 2)[2]

        if key in selected:
            selected.remove(key)
        else:
            selected.append(key)

        await state.update_data(specializations=selected)

        # Обновляем клавиатуру, но спокойно переживаем "message is not modified"
        try:
            await call.message.edit_reply_markup(reply_markup=kb_specs(selected))
        except TelegramBadRequest as e:
            # Если Телега ругается, что ничего не изменилось — просто игнорируем
            if "message is not modified" not in str(e):
                logger.exception("Ошибка обновления клавиатуры спецов: %s", e)

        await call.answer()
        return

    # Кнопка "Готово"
    if call.data == "sto_spec_ok":
        await state.set_state(STORegister.waiting_confirm)
        profile = await state.get_data()

        text = (
            "Проверьте данные:\n\n"
            f"Тип: {profile['org_type']}\n"
            f"Название: {profile['name']}\n"
            f"Адрес: {profile['address_text']}\n"
            f"Телефон: {profile['phone']}\n"
            f"Сайт: {profile['website']}\n"
            f"Специализации: {', '.join(profile['specializations']) or '—'}\n\n"
            "Подтвердить регистрацию?"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data="sto_reg_yes")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="sto_reg_no")],
            ]
        )

        await call.message.edit_text(text, reply_markup=kb)
        await call.answer()
        return

    # На всякий случай — остальные коллбеки просто игнорируем
    await call.answer()


# -------------------------------------------------
# Завершение регистрации
# -------------------------------------------------


@router.callback_query(STORegister.waiting_confirm)
async def sto_finish(call: CallbackQuery, state: FSMContext):
    """
    Финальный шаг регистрации СТО:
    - при "sto_reg_no" отменяем;
    - при подтверждении создаём запись сервис-центра в backend
      и обновляем роль пользователя на service_owner.
    """
    if call.data == "sto_reg_no":
        await state.clear()
        await call.message.edit_text("Регистрация СТО отменена.")
        await call.answer()
        return

    data = await state.get_data()
    tg_id = call.from_user.id

    try:
        user = await api_client.get_user_by_telegram(tg_id)
    except Exception as e:
        logger.exception("Ошибка запроса пользователя при регистрации СТО: %s", e)
        await call.message.edit_text(
            "Не удалось получить данные пользователя 😔\n"
            "Попробуйте ещё раз с команды /start."
        )
        await call.answer()
        return

    if not user:
        await call.message.edit_text(
            "Пользователь не найден в системе.\n"
            "Сначала завершите регистрацию как клиента через /start."
        )
        await call.answer()
        return

    user_id = user["id"]

    # Приводим payload к схеме backend-а (address вместо address_text)
    payload = {
        "user_id": user_id,
        "org_type": data.get("org_type"),
        "name": data.get("name"),
        "address": data.get("address_text"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "phone": data.get("phone"),
        "website": data.get("website"),
        "specializations": data.get("specializations"),
    }

    try:
        created = await api_client.create_service_center(payload)
    except Exception as e:
        logger.exception("Ошибка регистрации СТО: %s", e)
        await call.message.edit_text(
            "Не удалось зарегистрировать СТО 😔 Попробуйте позже."
        )
        await call.answer()
        return

    # После успешной регистрации переводим пользователя в роль service_owner
    try:
        await api_client.update_user(user_id, {"role": "service_owner"})
    except Exception as e:
        logger.exception(
            "Не удалось обновить роль пользователя до service_owner: %s", e
        )
        # Не фейлим регистрацию СТО, просто логируем

    await state.clear()

    await call.message.edit_text(
        f"СТО зарегистрировано успешно! 🎉\n\nID: {created.get('id')}\n"
        "Теперь вам доступно «🛠 Меню СТО» в главном меню.",
    )
    await call.answer()
