import logging
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

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

def kb_org_type():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ФЛ / Частный мастер", callback_data="sto_type_ind")],
        [InlineKeyboardButton(text="ЮЛ / Автосервис", callback_data="sto_type_comp")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="sto_back_menu")]
    ])


def kb_specs(selected: list[str]):
    all_specs = [
        ("Автомеханика", "mech"),
        ("Шиномонтаж", "tire"),
        ("Электрика", "elec"),
        ("Диагностика", "diag"),
        ("Кузовной", "body"),
        ("Агрегатный ремонт", "agg"),
    ]

    rows = []
    for title, key in all_specs:
        mark = "✅ " if key in selected else ""
        rows.append([InlineKeyboardButton(text=f"{mark}{title}", callback_data=f"sto_spec_{key}")])

    rows.append([InlineKeyboardButton(text="Готово", callback_data="sto_spec_ok")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# -------------------------------------------------
# Старт регистрации
# -------------------------------------------------

@router.callback_query(F.data == "menu_service")
async def sto_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(STORegister.waiting_org_type)
    await call.message.edit_text(
        "Регистрация автосервиса.\n\nВыберите тип организации:",
        reply_markup=kb_org_type(),
    )
    await call.answer()


@router.callback_query(F.data == "main:sto_menu")
async def sto_menu_entry(callback: CallbackQuery):
    """
    Вход в раздел СТО из главного инлайн-меню.

    Пока просто информируем, что раздел в разработке.
    Потом сюда повесим нормальный кабинет СТО.
    """
    await callback.answer()
    await callback.message.answer(
        "Раздел СТО будет доработан.\n"
        "Сейчас доступны регистрация СТО и работа с откликами по заявкам."
    )


# -------------------------------------------------
# Тип организации
# -------------------------------------------------

@router.callback_query(STORegister.waiting_org_type)
async def sto_org_type(call: CallbackQuery, state: FSMContext):
    if call.data not in ("sto_type_ind", "sto_type_comp"):
        await call.answer()
        return

    org_type = "individual" if call.data == "sto_type_ind" else "company"
    await state.update_data(org_type=org_type)

    await state.set_state(STORegister.waiting_name)
    await call.message.edit_text(
        "Введите название сервиса.\n"
        "Если вы частный мастер — укажите ваше имя.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await call.answer()


# -------------------------------------------------
# Название
# -------------------------------------------------

@router.message(STORegister.waiting_name)
async def sto_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Введите название.")
        return

    await state.update_data(name=name)
    await state.set_state(STORegister.waiting_address_text)
    await message.answer("Введите адрес (строкой).")


# -------------------------------------------------
# Адрес текстом
# -------------------------------------------------

@router.message(STORegister.waiting_address_text)
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

@router.message(STORegister.waiting_phone)
async def sto_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    await state.update_data(phone=phone)

    await state.set_state(STORegister.waiting_website)
    await message.answer("Введите сайт или соцсети (или напишите «Пропустить»).")


# -------------------------------------------------
# Сайт / соцсети
# -------------------------------------------------

@router.message(STORegister.waiting_website)
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
    data = await state.get_data()
    selected = data.get("specializations", [])

    if call.data.startswith("sto_spec_"):
        key = call.data.split("_", 2)[2]
        if key in selected:
            selected.remove(key)
        else:
            selected.append(key)
        await state.update_data(specializations=selected)

        await call.message.edit_reply_markup(reply_markup=kb_specs(selected))
        await call.answer()
        return

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

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="sto_reg_yes")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="sto_reg_no")],
        ])

        await call.message.edit_text(text, reply_markup=kb)
        await call.answer()
        return

    await call.answer()


# -------------------------------------------------
# Завершение регистрации
# -------------------------------------------------

@router.callback_query(STORegister.waiting_confirm)
async def sto_finish(call: CallbackQuery, state: FSMContext):
    """
    Финальный шаг регистрации СТО:
    - при "sto_reg_no" отменяем;
    - при подтверждении создаём запись сервис-центра в backend.
    """
    if call.data == "sto_reg_no":
        await state.clear()
        await call.message.edit_text("Регистрация отменена.")
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

    payload = {
        "user_id": user_id,
        "org_type": data["org_type"],
        "name": data["name"],
        "address_text": data["address_text"],
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "phone": data["phone"],
        "website": data["website"],
        "specializations": data["specializations"],
    }

    try:
        created = await api_client.create_service_center(payload)
    except Exception as e:
        logger.exception("Ошибка регистрации СТО: %s", e)
        await call.message.edit_text("Не удалось зарегистрировать СТО 😔 Попробуйте позже.")
        await call.answer()
        return

    await state.clear()

    await call.message.edit_text(
        f"СТО зарегистрировано успешно! 🎉\n\nID: {created.get('id')}\n"
        "Теперь доступен кабинет СТО.",
    )
    await call.answer()
