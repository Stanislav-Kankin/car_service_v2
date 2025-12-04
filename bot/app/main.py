import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import CommandStart, Command, StateFilter

from typing import Optional, Any

from .config import config
from .api_client import APIClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==========================
#   FSM-классы
# ==========================


class UserRegistration(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_city = State()


class CarAdd(StatesGroup):
    waiting_brand = State()
    waiting_model = State()
    waiting_year = State()
    waiting_plate = State()
    waiting_vin = State()


class CarEdit(StatesGroup):
    """
    Полное редактирование существующего автомобиля.
    """
    waiting_brand = State()
    waiting_model = State()
    waiting_year = State()
    waiting_plate = State()
    waiting_vin = State()


class RequestCreate(StatesGroup):
    """
    Создание заявки.
    """
    waiting_location_choice = State()   # 1. Выбор способа указания локации
    waiting_geo = State()              # 2. Приём локации
    waiting_location_text = State()    # 3. Ввод адреса/района текстом
    waiting_move = State()             # 4. Авто едет / эвакуация
    waiting_radius = State()           # 5. Радиус/район (если авто едет само)
    waiting_service_type = State()     # 6. Тип услуги
    waiting_description = State()      # 7. Описание проблемы
    waiting_photo = State()            # 8. Фото (опционально)
    waiting_show_phone = State()       # 9. Скрывать / показывать номер
    waiting_select_work_mode = State() # 10. Выбрать СТО из списка / отправить всем
    waiting_select_car = State()       # 11. Выбор авто (в конце)


class ServiceCenterRegistration(StatesGroup):
    waiting_org_type = State()
    waiting_name = State()
    waiting_phone = State()
    waiting_city = State()
    waiting_address_text = State()
    waiting_geo = State()
    waiting_extra_contacts = State()
    waiting_confirm = State()


class ServiceCenterSpecs(StatesGroup):
    """
    FSM для редактирования специализаций СТО.
    """
    waiting_specs = State()


class ServiceRequestStates(StatesGroup):
    """
    Состояния при работе СТО с уже закреплённой заявкой.
    """
    waiting_conditions = State()
    waiting_decline_reason = State()


# ==========================
#   Клавиатуры
# ==========================


def main_menu_reply() -> ReplyKeyboardRemove:
    """
    Заглушка вместо главного reply-меню:
    просто убирает нижнюю клавиатуру, чтобы остались только inline-кнопки.
    """
    return ReplyKeyboardRemove()


def main_menu_inline() -> InlineKeyboardMarkup:
    """
    Главное меню (inline-клавиатура).
    """
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🆕 Новая заявка",
                    callback_data="new_request",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚗 Мой гараж",
                    callback_data="user_garage",
                ),
                InlineKeyboardButton(
                    text="📄 Мои заявки",
                    callback_data="user_requests",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👤 Профиль",
                    callback_data="user_profile",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏭 Я владелец СТО",
                    callback_data="service_owner_menu",
                ),
            ],
        ]
    )
    return kb


def cancel_kb() -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой отмены.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel",
                )
            ]
        ]
    )


def back_cancel_kb(back_cb: str = "back_to_main") -> InlineKeyboardMarkup:
    """
    Клавиатура «Назад / Отмена».
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=back_cb,
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="cancel",
                ),
            ]
        ]
    )


def garage_menu_inline(cars: list[dict]) -> InlineKeyboardMarkup:
    """
    Список машин в гараже.
    """
    rows = []

    for car in cars:
        title = f"{car.get('brand', '')} {car.get('model', '')} ({car.get('year', '')})".strip()
        if not title:
            title = f"Авто #{car['id']}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"car_{car['id']}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Добавить авто",
                callback_data="car_add",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ В главное меню",
                callback_data="back_to_main",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def car_edit_menu_kb(car_id: int) -> InlineKeyboardMarkup:
    """
    Меню редактирования авто.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать данные",
                    callback_data=f"car_edit_{car_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку авто",
                    callback_data="user_garage",
                )
            ],
        ]
    )


def request_list_kb(requests: list[dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком заявок.
    """
    rows = []

    for r in requests:
        rid = r["id"]
        status = r.get("status") or "new"
        status_map = {
            "new": "🆕 Новая",
            "sent": "📤 Отправлена",
            "accepted_by_service": "✅ Принята СТО",
            "in_work": "🔧 В работе",
            "done": "🏁 Выполнена",
            "cancelled": "🚫 Отменена",
            "rejected_by_service": "❌ Отклонена СТО",
        }
        status_text = status_map.get(status, status)
        title = f"Заявка #{rid} — {status_text}"

        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"req_{rid}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ В главное меню",
                callback_data="back_to_main",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_owner_menu_kb() -> InlineKeyboardMarkup:
    """
    Главное меню владельца СТО.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏭 Мой автосервис",
                    callback_data="service_profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧩 Мои специализации",
                    callback_data="service_specs_edit",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В главное меню",
                    callback_data="back_to_main",
                )
            ],
        ]
    )


def service_org_type_kb() -> InlineKeyboardMarkup:
    """
    Выбор типа организации СТО (ФЛ / ЮЛ).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨‍🔧 Частный мастер (ФЛ)",
                    callback_data="org_type_individual",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏢 Автосервис / компания (ЮЛ)",
                    callback_data="org_type_company",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel",
                )
            ],
        ]
    )


def request_location_choice_kb() -> InlineKeyboardMarkup:
    """
    1. Выбор способа указания местоположения для заявки.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📍 Отправить геолокацию",
                    callback_data="req_loc_geo",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗺 Указать место на карте / текстом",
                    callback_data="req_loc_text",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заявку",
                    callback_data="req_cancel",
                )
            ],
        ]
    )


def request_move_kb() -> InlineKeyboardMarkup:
    """
    2. Авто едет само / нужна эвакуация.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚗 Автомобиль передвигается самостоятельно",
                    callback_data="req_move_self",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚨 Нужна эвакуация / выездной мастер",
                    callback_data="req_move_help",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заявку",
                    callback_data="req_cancel",
                )
            ],
        ]
    )


def request_radius_kb() -> InlineKeyboardMarkup:
    """
    3. Радиус поиска сервиса.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 км", callback_data="req_radius_5"),
                InlineKeyboardButton(text="15 км", callback_data="req_radius_15"),
                InlineKeyboardButton(text="30 км", callback_data="req_radius_30"),
            ],
            [
                InlineKeyboardButton(
                    text="📍 Указать район на карте / текстом",
                    callback_data="req_radius_custom",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заявку",
                    callback_data="req_cancel",
                )
            ],
        ]
    )


def request_service_type_kb() -> InlineKeyboardMarkup:
    """
    4. Тип услуги / категория.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔧 Автомеханика", callback_data="service_type_mech"),
            ],
            [
                InlineKeyboardButton(text="🛞 Шиномонтаж", callback_data="service_type_tires"),
            ],
            [
                InlineKeyboardButton(text="🔌 Автоэлектрика", callback_data="service_type_electric"),
            ],
            [
                InlineKeyboardButton(text="📊 Диагностика", callback_data="service_type_diag"),
            ],
            [
                InlineKeyboardButton(text="🧱 Кузовной ремонт", callback_data="service_type_body"),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Агрегаты (двигатель, КПП и т.п.)",
                    callback_data="service_type_aggregates",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заявку",
                    callback_data="req_cancel",
                )
            ],
        ]
    )


def description_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Всё верно",
                    callback_data="req_desc_ok",
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data="req_desc_edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заявку",
                    callback_data="req_cancel",
                )
            ],
        ]
    )


def photo_choice_kb() -> InlineKeyboardMarkup:
    """
    Прикрепить фото / пропустить.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📷 Прикрепить фото",
                    callback_data="req_photo_add",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="req_photo_skip",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заявку",
                    callback_data="req_cancel",
                )
            ],
        ]
    )


def show_phone_kb() -> InlineKeyboardMarkup:
    """
    Показывать номер телефона сотруднику?
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Показывать номер",
                    callback_data="req_phone_show",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🙈 Не показывать номер",
                    callback_data="req_phone_hide",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заявку",
                    callback_data="req_cancel",
                )
            ],
        ]
    )


def work_mode_kb() -> InlineKeyboardMarkup:
    """
    Выбор режима работы со СТО: выбрать из списка / отправить всем.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Выбрать СТО из списка",
                    callback_data="req_mode_choose",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Отправить всем подходящим СТО",
                    callback_data="req_mode_send_all",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заявку",
                    callback_data="req_cancel",
                )
            ],
        ]
    )


def car_select_for_request_kb(cars: list[dict]) -> InlineKeyboardMarkup:
    """
    Выбор авто для заявки (в конце сценария).
    """
    rows = []

    for car in cars:
        car_id = car["id"]
        title = f"{car.get('brand', '')} {car.get('model', '')} ({car.get('year', '')})".strip()
        if not title:
            title = f"Авто #{car_id}"

        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"req_car_{car_id}",
                )
            ]
        )

    # Кнопка «без привязки»
    rows.append(
        [
            InlineKeyboardButton(
                text="🚗 Без привязки к авто",
                callback_data="req_car_skip",
            )
        ]
    )

    # Кнопка отмены заявки
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отменить заявку",
                callback_data="req_cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_select_for_request_kb(
    services: list[dict],
    request_id: int,
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора СТО для только что созданной заявки.
    """
    rows: list[list[InlineKeyboardButton]] = []

    for sc in services:
        sc_id = sc["id"]
        name = (sc.get("name") or "Без названия").strip()
        city = (sc.get("city") or "").strip()

        if city:
            btn_text = f"{name} ({city})"
        else:
            btn_text = name

        # На всякий случай режем слишком длинные названия
        btn_text = btn_text[:64] or f"Сервис #{sc_id}"

        rows.append(
            [
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"req_sc_{request_id}_{sc_id}",
                )
            ]
        )

    # Отмена выбора сервиса
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отменить выбор сервиса",
                callback_data="req_cancel_choose_sc",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_assigned_actions_kb(request_id: int) -> InlineKeyboardMarkup:
    """
    Кнопки под уведомлением для СТО, когда заявка закреплена за сервисом.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Указать условия",
                    callback_data=f"svc_req_cond_{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить заявку",
                    callback_data=f"svc_req_decline_{request_id}",
                )
            ],
        ]
    )


def format_service_center_profile(sc: dict) -> str:
    """
    Красивый текст профиля СТО для кабинета.
    """
    name = (sc.get("name") or "Без названия").strip()

    org_type = sc.get("org_type")
    if org_type == "individual":
        org_title = "Частный мастер"
    elif org_type == "company":
        org_title = "Автосервис / компания"
    else:
        org_title = "Автосервис"

    phone = (sc.get("phone") or "Не указан").strip()
    city = (sc.get("city") or "").strip()
    addr = (sc.get("address_text") or "").strip()

    if city and addr:
        addr_line = f"{city}, {addr}"
    else:
        addr_line = addr or city or "Не указан"

    specs = sc.get("specializations") or []
    specs_map = {
        "mech": "🔧 Автомеханика",
        "tires": "🛞 Шиномонтаж",
        "electric": "🔌 Автоэлектрика",
        "diag": "📊 Диагностика",
        "body": "🧱 Кузовной ремонт",
        "aggregates": "⚙️ Ремонт агрегатов",
    }
    if specs:
        specs_text = ", ".join(specs_map.get(s, s) for s in specs)
    else:
        specs_text = "Не выбраны"

    geo_note = "📍 Геолокация сохранена" if sc.get("latitude") and sc.get("longitude") else "📍 Геолокация не указана"

    lines = [
        f"🏭 <b>{name}</b>",
        f"Тип: {org_title}",
        f"Телефон: {phone}",
        f"Адрес: {addr_line}",
        f"Специализации: {specs_text}",
        geo_note,
    ]

    extra = (sc.get("extra_contacts") or "").strip()
    if extra:
        lines.append(f"Доп. контакты: {extra}")

    return "\n".join(lines)
async def main() -> None:
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    api = APIClient()

    async def _get_user_service_center(user_id: int) -> Optional[dict]:
        """
        Возвращает первый СТО пользователя или None.
        """
        try:
            sc_list = await api.list_service_centers_by_user(user_id)
        except Exception as e:
            logger.exception("Ошибка при получении СТО пользователя: %s", e)
            return None

        if not sc_list:
            return None
        return sc_list[0]

    # ---------- /ping ----------

    @dp.message(Command("ping"))
    async def cmd_ping(message: Message):
        await message.answer("pong 🏓")

    # ---------- /start ----------

    @dp.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        logger.info("--- /start от %s", tg_id)

        await state.clear()

        # пробуем найти пользователя
        user = None
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception as e:
            logger.exception("Ошибка при get_user_by_telegram: %s", e)

        if not user:
            # запускаем регистрацию
            await message.answer(
                "Добро пожаловать в CarBot V2! 🎉\n"
                "Давай заполним короткий профиль.\n\n"
                "Как к тебе обращаются?"
            )
            await state.set_state(UserRegistration.waiting_full_name)

        else:
            # пользователь уже есть
            await message.answer(
                "С возвращением в CarBot V2! 🚗\n"
                "Используй меню, чтобы продолжить работу.",
                reply_markup=main_menu_reply(),
            )
            await message.answer(
                "Выбери действие в меню:",
                reply_markup=main_menu_inline(),
            )

    # ---------- Регистрация ----------

    @dp.message(UserRegistration.waiting_full_name)
    async def reg_full_name(message: Message, state: FSMContext):
        await state.update_data(full_name=message.text.strip())
        await message.answer("Отправь, пожалуйста, номер телефона:")
        await state.set_state(UserRegistration.waiting_phone)

    @dp.message(UserRegistration.waiting_phone)
    async def reg_phone(message: Message, state: FSMContext):
        await state.update_data(phone=message.text.strip())
        await message.answer("В каком городе ты находишься?")
        await state.set_state(UserRegistration.waiting_city)

    @dp.message(UserRegistration.waiting_city)
    async def reg_city(message: Message, state: FSMContext):
        city = message.text.strip()
        data = await state.get_data()
        full_name = data["full_name"]
        phone = data["phone"]

        # создаём пользователя в backend
        tg_id = message.from_user.id
        payload = {
            "telegram_id": tg_id,
            "full_name": full_name,
            "phone": phone,
            "city": city,
        }

        try:
            user = await api.create_user(payload)
            logger.info("Создан пользователь: %s", user)
        except Exception as e:
            logger.exception("Ошибка при создании пользователя: %s", e)
            await message.answer("Произошла ошибка при сохранении профиля. Попробуй позже.")
            await state.clear()
            return

        await state.clear()
        await message.answer(
            "Готово! ✅\n"
            "Профиль создан, теперь можно пользоваться всеми возможностями бота.",
            reply_markup=main_menu_reply(),
        )
        await message.answer(
            "Выбери действие в меню:",
            reply_markup=main_menu_inline(),
        )

    # ---------- Кнопка «Профиль» ----------

    @dp.callback_query(F.data == "user_profile")
    async def user_profile(call: CallbackQuery, state: FSMContext):
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception as e:
            logger.exception("Ошибка при получении профиля: %s", e)
            await call.message.edit_text(
                "Не удалось получить профиль. Попробуй позже.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        text = (
            "👤 <b>Твой профиль</b>\n\n"
            f"Имя: {user.get('full_name')}\n"
            f"Телефон: {user.get('phone')}\n"
            f"Город: {user.get('city') or 'не указан'}\n"
        )
        await call.message.edit_text(text, reply_markup=main_menu_inline())
        await call.answer()

    # ==========================
    #   ГАРАЖ
    # ==========================

    @dp.callback_query(F.data == "user_garage")
    async def user_garage_menu(call: CallbackQuery, state: FSMContext):
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для гаража: %s", e)
            await call.message.edit_text(
                "Не удалось получить данные пользователя.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        try:
            cars = await api.list_cars_by_user(user_id)
        except Exception as e:
            logger.exception("Ошибка при list_cars_by_user: %s", e)
            cars = []

        if not cars:
            text = "Пока в гараже нет ни одного автомобиля. 🚗\nДобавим первый?"
        else:
            text = "🚗 <b>Твой гараж</b>\nВыбери авто из списка:"

        kb = garage_menu_inline(cars)
        await call.message.edit_text(text, reply_markup=kb)
        await call.answer()

    @dp.callback_query(F.data.startswith("car_"))
    async def car_detail(call: CallbackQuery, state: FSMContext):
        data = call.data
        if data == "car_add":
            # запускаем добавление нового авто
            await state.set_state(CarAdd.waiting_brand)
            await call.message.edit_text(
                "Добавление нового авто.\n\nУкажи марку автомобиля:",
                reply_markup=cancel_kb(),
            )
            await call.answer()
            return

        # просмотр конкретного авто
        try:
            car_id = int(data.split("_", 1)[1])
        except Exception:
            await call.answer()
            return

        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для car_detail: %s", e)
            await call.message.edit_text(
                "Не удалось получить данные пользователя.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        try:
            cars = await api.list_cars_by_user(user_id)
        except Exception as e:
            logger.exception("Ошибка при list_cars_by_user (detail): %s", e)
            await call.message.edit_text(
                "Ошибка при загрузке списка автомобилей.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        car = next((c for c in cars if c["id"] == car_id), None)
        if not car:
            await call.message.edit_text(
                "Автомобиль не найден.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        text = (
            "🚗 <b>Автомобиль</b>\n\n"
            f"Марка: {car.get('brand')}\n"
            f"Модель: {car.get('model')}\n"
            f"Год: {car.get('year')}\n"
            f"Номер: {car.get('license_plate') or 'не указан'}\n"
            f"VIN: {car.get('vin') or 'не указан'}\n"
        )

        await call.message.edit_text(
            text,
            reply_markup=car_edit_menu_kb(car_id),
        )
        await call.answer()

    # ---------- Добавление авто ----------

    @dp.message(CarAdd.waiting_brand)
    async def car_add_brand(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        await state.update_data(brand=message.text.strip())
        await message.answer("Укажи модель автомобиля:")
        await state.set_state(CarAdd.waiting_model)

    @dp.message(CarAdd.waiting_model)
    async def car_add_model(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        await state.update_data(model=message.text.strip())
        await message.answer("Укажи год выпуска (например, 2015):")
        await state.set_state(CarAdd.waiting_year)

    @dp.message(CarAdd.waiting_year)
    async def car_add_year(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        year_str = message.text.strip()
        if not year_str.isdigit():
            await message.answer("Введите год цифрами, например 2015.")
            return

        await state.update_data(year=int(year_str))
        await message.answer("Укажи госномер (можно пропустить, напиши «-»):")
        await state.set_state(CarAdd.waiting_plate)

    @dp.message(CarAdd.waiting_plate)
    async def car_add_plate(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        plate = message.text.strip()
        if plate == "-":
            plate = ""
        await state.update_data(license_plate=plate)

        await message.answer("Укажи VIN (можно пропустить, напиши «-»):")
        await state.set_state(CarAdd.waiting_vin)

    @dp.message(CarAdd.waiting_vin)
    async def car_add_vin(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        vin = message.text.strip()
        if vin == "-":
            vin = ""

        data = await state.get_data()
        tg_id = message.from_user.id

        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для добавления авто: %s", e)
            await message.answer("Не удалось получить данные пользователя.")
            await state.clear()
            return

        payload = {
            "user_id": user_id,
            "brand": data["brand"],
            "model": data["model"],
            "year": data["year"],
            "license_plate": data.get("license_plate", ""),
            "vin": vin,
        }

        try:
            car = await api.create_car(payload)
            logger.info("Создан автомобиль: %s", car)
        except Exception as e:
            logger.exception("Ошибка при создании автомобиля: %s", e)
            await message.answer("Ошибка при сохранении авто. Попробуй позже.")
            await state.clear()
            return

        await state.clear()
        await message.answer(
            "Автомобиль добавлен в гараж! ✅",
            reply_markup=main_menu_reply(),
        )

    # ==========================
    #   МОИ ЗАЯВКИ (просмотр)
    # ==========================

    @dp.callback_query(F.data == "user_requests")
    async def user_requests_menu(call: CallbackQuery, state: FSMContext):
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для заявок: %s", e)
            await call.message.edit_text(
                "Не удалось получить данные пользователя.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        try:
            requests_list = await api.list_requests_by_user(user_id)
        except Exception as e:
            logger.exception("Ошибка при загрузке списка заявок: %s", e)
            requests_list = []

        if not requests_list:
            text = "У тебя пока нет заявок. 📝\nСоздай первую через «🆕 Новая заявка»."
            await call.message.edit_text(
                text,
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        kb = request_list_kb(requests_list)
        await call.message.edit_text(
            "📄 <b>Твои заявки</b>\nВыбери заявку из списка:",
            reply_markup=kb,
        )
        await call.answer()

    # ==========================
    #   СОЗДАНИЕ ЗАЯВКИ
    # ==========================

    @dp.callback_query(F.data == "new_request")
    async def new_request_start(call: CallbackQuery, state: FSMContext):
        """
        Старт сценария новой заявки.
        Сначала спрашиваем состояние авто, БЕЗ запроса геолокации.
        """
        await state.clear()
        await state.set_state(RequestCreate.waiting_move)

        text = (
            "Новая заявка 🚗\n\n"
            "Сначала определимся с состоянием автомобиля:\n\n"
            "Автомобиль передвигается самостоятельно или нужна эвакуация / выездной мастер?"
        )

        await call.message.edit_text(
            text,
            reply_markup=request_move_kb(),
        )
        await call.answer()

    # ---------- Выбор способа указания локации ----------

    @dp.callback_query(RequestCreate.waiting_location_choice)
    async def req_location_choice(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "req_cancel":
            await state.clear()
            await call.message.edit_text(
                "Создание заявки отменено ❌\n\n"
                "Ты всегда можешь начать заново через «🆕 Новая заявка».",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        if data == "req_loc_geo":
            # ждём геолокацию
            await state.set_state(RequestCreate.waiting_geo)
            await call.message.edit_text(
                "Отправь, пожалуйста, геолокацию текущего или целевого места.\n\n"
                "Ты также можешь указать место на карте в приложении.",
                reply_markup=cancel_kb(),
            )
            await call.answer()
            return

        if data == "req_loc_text":
            # ждём текстовый адрес / район
            await state.set_state(RequestCreate.waiting_location_text)
            await call.message.edit_text(
                "Опиши место, где нужна услуга.\n\n"
                "Например: «Минск, Уручье» или «ул. Ленина, 10» или «весь город».",
                reply_markup=cancel_kb(),
            )
            await call.answer()
            return

        await call.answer()

    # ---------- Приём геолокации ----------

    @dp.message(RequestCreate.waiting_geo)
    async def req_get_geo(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Создание заявки отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        if not message.location:
            await message.answer(
                "Пожалуйста, отправь геолокацию через кнопку отправки местоположения.\n"
                "Или напиши «Отмена»."
            )
            return

        lat = message.location.latitude
        lon = message.location.longitude

        await state.update_data(
            location_type="geo",
            latitude=lat,
            longitude=lon,
        )

        # Дальше — выбор типа услуги (мы уже знаем, что это эвакуация/выездной мастер)
        await state.set_state(RequestCreate.waiting_service_type)
        await message.answer(
            "Отлично! 📍 Локация сохранена.\n\n"
            "Теперь выбери тип услуги / категории:",
            reply_markup=request_service_type_kb(),
        )

    # ---------- Текстовое местоположение ----------

    @dp.message(RequestCreate.waiting_location_text)
    async def req_get_location_text(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Создание заявки отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        text = (message.text or "").strip()
        if not text:
            await message.answer("Пожалуйста, опиши место или напиши «Отмена».")
            return

        await state.update_data(
            location_type="text",
            location_text=text,
        )

        # Переходим сразу к выбору типа услуги
        await state.set_state(RequestCreate.waiting_service_type)
        await message.answer(
            "Принял 👍\n\n"
            "Теперь выбери тип услуги / категории:",
            reply_markup=request_service_type_kb(),
        )

    # ---------- Отмена заявки через callback ----------

    @dp.callback_query(F.data == "req_cancel")
    async def req_cancel(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await call.message.edit_text(
            "Создание заявки отменено ❌\n\n"
            "Ты всегда можешь начать заново через «🆕 Новая заявка».",
            reply_markup=main_menu_inline(),
        )

    # ---------- Шаг 1: авто едет / эвакуация ----------

    @dp.callback_query(RequestCreate.waiting_move, F.data.in_({"req_move_self", "req_move_help"}))
    async def req_move_choice(call: CallbackQuery, state: FSMContext):
        move_type = "self" if call.data == "req_move_self" else "help"
        await state.update_data(move_type=move_type)

        # Если авто ЕДЕТ САМО — НИКАКОЙ геолокации, только радиус/район.
        if move_type == "self":
            await state.set_state(RequestCreate.waiting_radius)
            await call.message.edit_text(
                "Ок, автомобиль передвигается самостоятельно. 🚗\n\n"
                "Теперь выбери радиус или укажи район, где тебе удобно обслужиться.",
                reply_markup=request_radius_kb(),
            )
            await call.answer()
            return

        # Если нужна эвакуация / выездной мастер — сперва спрашиваем местоположение
        await state.set_state(RequestCreate.waiting_location_choice)
        await call.message.edit_text(
            "Принято. Нужна эвакуация / выездной мастер. 🚨\n\n"
            "Теперь укажи место, где находится автомобиль:",
            reply_markup=request_location_choice_kb(),
        )
        await call.answer()

    # ---------- Радиус поиска (если авто едет само) ----------

    @dp.callback_query(RequestCreate.waiting_radius)
    async def req_radius_choice(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "req_cancel":
            await state.clear()
            await call.message.edit_text(
                "Создание заявки отменено.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        if data.startswith("req_radius_"):
            radius_str = data.split("_", 2)[2]
            if radius_str.isdigit():
                radius_km = int(radius_str)
            else:
                radius_km = 5

            await state.update_data(
                radius_type="km",
                radius_km=radius_km,
            )

            await state.set_state(RequestCreate.waiting_service_type)
            await call.message.edit_text(
                f"Радиус {radius_km} км выбран. ✅\n\n"
                "Теперь выбери тип услуги:",
                reply_markup=request_service_type_kb(),
            )
            await call.answer()
            return

        if data == "req_radius_custom":
            await state.update_data(radius_type="custom")
            await state.set_state(RequestCreate.waiting_location_text)
            await call.message.edit_text(
                "Опиши район, где тебе удобно обслужиться.\n"
                "Например: «центр города», «Фрунзенский район» и т.п.",
                reply_markup=cancel_kb(),
            )
            await call.answer()
            return

        await call.answer()

    # ---------- Тип услуги ----------

    @dp.callback_query(RequestCreate.waiting_service_type)
    async def req_service_type_choice(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "req_cancel":
            await state.clear()
            await call.message.edit_text(
                "Создание заявки отменено.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        if not data.startswith("service_type_"):
            await call.answer()
            return

        service_type_key = data.split("service_type_", 1)[1]
        await state.update_data(service_type=service_type_key)

        await state.set_state(RequestCreate.waiting_description)
        await call.message.edit_text(
            "Теперь опиши проблему.\n\n"
            "Это обязательное поле — постарайся указать симптомы, ошибки, особенности.\n\n"
            "Например: «стук в подвеске справа», «горит check engine, провалы тяги», и т.п.",
            reply_markup=cancel_kb(),
        )
        await call.answer()

    # ---------- Описание проблемы ----------

    @dp.message(RequestCreate.waiting_description)
    async def req_description_step(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Создание заявки отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        text = (message.text or "").strip()
        if not text:
            await message.answer("Пожалуйста, опиши проблему или напиши «Отмена».")
            return

        await state.update_data(description=text)

        await state.set_state(RequestCreate.waiting_photo)
        summary = (
            "Описание принято ✅\n\n"
            "Хочешь прикрепить фото к заявке?\n"
            "Это поможет СТО быстрее понять проблему."
        )
        await message.answer(
            summary,
            reply_markup=photo_choice_kb(),
        )

    # ---------- Фото (опционально) ----------

    @dp.callback_query(RequestCreate.waiting_photo)
    async def req_photo_choice(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "req_cancel":
            await state.clear()
            await call.message.edit_text(
                "Создание заявки отменено.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        if data == "req_photo_skip":
            # пропускаем фото
            await state.update_data(photo_id=None)
            await state.set_state(RequestCreate.waiting_show_phone)
            await call.message.edit_text(
                "Ок, без фото. ✅\n\n"
                "Показывать твой номер телефона сотрудникам СТО сразу, "
                "или скрыть его до явного согласия?",
                reply_markup=show_phone_kb(),
            )
            await call.answer()
            return

        if data == "req_photo_add":
            await call.message.edit_text(
                "Пришли одно фото, которое лучше всего показывает проблему.\n"
                "Или напиши «Отмена».",
                reply_markup=cancel_kb(),
            )
            await state.set_state(RequestCreate.waiting_photo)
            await call.answer()
            return

        await call.answer()

    @dp.message(RequestCreate.waiting_photo, F.photo)
    async def req_get_photo(message: Message, state: FSMContext):
        """
        Приём фото.
        """
        if message.caption and message.caption.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Создание заявки отменено.",
                reply_markup=main_menu_reply(),
            )
            return

        if not message.photo:
            await message.answer("Пожалуйста, отправь именно фото, либо напиши «Отмена».")
            return

        file_id = message.photo[-1].file_id
        await state.update_data(photo_id=file_id)

        await state.set_state(RequestCreate.waiting_show_phone)
        await message.answer(
            "Фото сохранено. ✅\n\n"
            "Показывать твой номер телефона сотрудникам СТО сразу, "
            "или скрыть его до явного согласия?",
            reply_markup=show_phone_kb(),
        )

    # ---------- Показывать номер телефона ----------

    @dp.callback_query(RequestCreate.waiting_show_phone)
    async def req_show_phone_choice(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "req_cancel":
            await state.clear()
            await call.message.edit_text(
                "Создание заявки отменено.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        show_phone = True if data == "req_phone_show" else False
        await state.update_data(show_phone=show_phone)

        # Переходим к выбору режима: выбрать СТО или отправить всем
        await state.set_state(RequestCreate.waiting_select_work_mode)
        await call.message.edit_text(
            "Как будем работать со СТО?\n\n"
            "📋 Выбрать конкретный сервис из списка\n"
            "или\n"
            "📤 Отправить заявку сразу всем подходящим СТО?",
            reply_markup=work_mode_kb(),
        )
        await call.answer()
    # ---------- Режим работы со СТО ----------

    @dp.callback_query(RequestCreate.waiting_select_work_mode)
    async def req_work_mode_choice(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "req_cancel":
            await state.clear()
            await call.message.edit_text(
                "Создание заявки отменено.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        mode = "choose" if data == "req_mode_choose" else "send_all"
        await state.update_data(work_mode=mode)

        # В самом конце — выбор авто из гаража
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для выбора авто: %s", e)
            await call.message.edit_text(
                "Ошибка при получении данных пользователя.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        try:
            cars = await api.list_cars_by_user(user_id)
        except Exception as e:
            logger.exception("Ошибка при list_cars_by_user (для заявки): %s", e)
            cars = []

        await state.set_state(RequestCreate.waiting_select_car)

        if not cars:
            # Нет авто — сразу создаём заявку без привязки
            await state.update_data(car_id=None)
            await _final_create_request(call, state, api, user_id)
            await call.answer()
            return

        # Есть авто — предлагаем выбрать
        await call.message.edit_text(
            "Выбери автомобиль, к которому относится заявка.\n"
            "Либо можно оставить без привязки:",
            reply_markup=car_select_for_request_kb(cars),
        )
        await call.answer()

    @dp.callback_query(RequestCreate.waiting_select_car)
    async def req_select_car_for_request(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "req_cancel":
            await state.clear()
            await call.message.edit_text(
                "Создание заявки отменено.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для финала заявки: %s", e)
            await call.message.edit_text(
                "Ошибка при получении данных пользователя.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        if data == "req_car_skip":
            await state.update_data(car_id=None)
        elif data.startswith("req_car_"):
            try:
                car_id = int(data.split("_", 2)[2])
            except ValueError:
                car_id = None
            await state.update_data(car_id=car_id)
        else:
            await call.answer()
            return

        await _final_create_request(call, state, api, user_id)
        await call.answer()

    async def _final_create_request(
        call: CallbackQuery,
        state: FSMContext,
        api: APIClient,
        user_id: int,
    ):
        """
        Финальное создание заявки в backend.
        """
        data = await state.get_data()

        payload = {
            "user_id": user_id,
            "location_type": data.get("location_type"),
            "location_text": data.get("location_text"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "move_type": data.get("move_type"),
            "radius_type": data.get("radius_type"),
            "radius_km": data.get("radius_km"),
            "service_type": data.get("service_type"),
            "description": data.get("description"),
            "show_phone": data.get("show_phone", True),
            "work_mode": data.get("work_mode"),
            "car_id": data.get("car_id"),
        }

        try:
            req = await api.create_request(payload)
            logger.info("Создана заявка: %s", req)
        except Exception as e:
            logger.exception("Ошибка при создании заявки: %s", e)
            await call.message.edit_text(
                "Ошибка при сохранении заявки. Попробуй позже.",
                reply_markup=main_menu_inline(),
            )
            await state.clear()
            return

        # С этого момента FSM нам уже не нужен
        await state.clear()

        work_mode = data.get("work_mode") or "choose"
        request_id = req.get("id")

        # ----- Вариант 1: Выбрать СТО из списка -----
        if work_mode == "choose":
            # Пытаемся подобрать подходящие СТО
            try:
                user = await api.get_user(user_id)
            except Exception as e:
                logger.exception("Ошибка при получении пользователя для подбора СТО: %s", e)
                user = None

            filters: dict[str, Any] = {}

            # Фильтр по типу услуги
            service_type = req.get("service_type") or data.get("service_type")
            if service_type:
                filters["service_type"] = service_type

            # Фильтр по городу пользователя (если есть)
            if user:
                city = (user.get("city") or "").strip()
                if city:
                    filters["city"] = city

            try:
                services = await api.list_service_centers(filters or None)
            except Exception as e:
                logger.exception(
                    "Ошибка при подборе СТО для заявки %s: %s",
                    request_id,
                    e,
                )
                services = []

            # Если ничего не нашли — показываем стандартный текст
            if not services:
                text = (
                    "Заявка создана! ✅\n\n"
                    f"Номер заявки: #{request_id}\n"
                    "Пока не удалось найти подходящие СТО.\n\n"
                    "Следить за статусом заявки можно в разделе «📄 Мои заявки»."
                )
                await call.message.edit_text(
                    text,
                    reply_markup=main_menu_inline(),
                )
                return

            # Есть подходящие сервисы — даём список на выбор
            text_lines = [
                "Заявка создана! ✅",
                "",
                f"Номер заявки: #{request_id}",
                "",
                "Теперь выбери сервис из списка ниже:",
            ]
            await call.message.edit_text(
                "\n".join(text_lines),
                reply_markup=service_select_for_request_kb(
                    services,
                    request_id=request_id,
                ),
            )
            return

        # ----- Вариант 2: Отправить всем подходящим СТО -----

        # 1) Ставим статус sent
        try:
            await api.update_request(request_id, {"status": "sent"})
        except Exception as e:
            logger.exception(
                "Ошибка при обновлении статуса заявки %s на sent: %s",
                request_id,
                e,
            )

        # 2) Подбираем подходящие СТО (та же логика, что и для choose)
        try:
            user = await api.get_user(user_id)
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для рассылки СТО: %s", e)
            user = None

        filters: dict[str, Any] = {}

        service_type = req.get("service_type") or data.get("service_type")
        if service_type:
            filters["service_type"] = service_type

        if user:
            city = (user.get("city") or "").strip()
            if city:
                filters["city"] = city

        try:
            services = await api.list_service_centers(filters or None)
        except Exception as e:
            logger.exception(
                "Ошибка при подборе СТО для рассылки заявки %s: %s",
                request_id,
                e,
            )
            services = []

        # 3) Если вообще никого не нашли — просто говорим клиенту
        if not services:
            text = (
                "Заявка создана! ✅\n\n"
                f"Номер заявки: #{request_id}\n"
                "Но пока не удалось найти ни одного подходящего сервиса.\n\n"
                "Следить за статусом заявки можно в разделе «📄 Мои заявки»."
            )
            await call.message.edit_text(
                text,
                reply_markup=main_menu_inline(),
            )
            return

        # 4) Рассылаем всем найденным СТО
        req_desc = req.get("description") or "без описания"
        service_type_human = service_type or "не указано"

        for sc in services:
            owner_user_id = sc.get("user_id")
            if not owner_user_id:
                continue

            try:
                svc_user = await api.get_user(owner_user_id)
            except Exception as e:
                logger.exception(
                    "Ошибка при получении пользователя-владельца СТО %s: %s",
                    owner_user_id,
                    e,
                )
                continue

            svc_tg_id = svc_user.get("telegram_id")
            if not svc_tg_id:
                continue

            text_svc = (
                f"📩 Новая заявка #{request_id} от клиента.\n\n"
                f"Тип услуги: {service_type_human}\n"
                f"Описание: {req_desc}\n\n"
                "Вы можете указать свои условия или отклонить заявку."
            )

            try:
                await call.bot.send_message(
                    svc_tg_id,
                    text_svc,
                    reply_markup=service_assigned_actions_kb(request_id),
                )
            except Exception as e:
                logger.exception(
                    "Не удалось отправить заявку сервису %s: %s",
                    sc.get("id"),
                    e,
                )

        # 5) Сообщаем клиенту
        text_client = (
            "Заявка создана и отправлена всем подходящим СТО! ✅\n\n"
            f"Номер заявки: #{request_id}\n\n"
            "Сервисы смогут прислать свои условия по этой заявке.\n"
            "Следить за ответами можно в разделе «📄 Мои заявки»."
        )

        await call.message.edit_text(
            text_client,
            reply_markup=main_menu_inline(),
        )

        # ----- Вариант 2: Отправить всем (пока просто стандартный текст) -----

        text = (
            "Заявка создана! ✅\n\n"
            f"Номер заявки: #{req.get('id')}\n"
            "Скоро подходящие СТО увидят её и смогут откликнуться.\n\n"
            "Следить за статусом заявки можно в разделе «📄 Мои заявки»."
        )
        await call.message.edit_text(text, reply_markup=main_menu_inline())

    @dp.callback_query(F.data.startswith("req_sc_"))
    async def req_choose_service_for_request(call: CallbackQuery, state: FSMContext):
        """
        Пользователь выбрал конкретный СТО для заявки (режим work_mode = choose).
        callback_data: req_sc_<request_id>_<service_center_id>
        """
        raw = call.data or ""
        parts = raw.split("_")
        if len(parts) != 4:
            await call.answer()
            return

        try:
            request_id = int(parts[2])
            sc_id = int(parts[3])
        except ValueError:
            await call.answer()
            return

        # Подтягиваем данные заявки
        try:
            req = await api.get_request(request_id)
        except Exception as e:
            logger.exception("Ошибка при получении заявки %s: %s", request_id, e)
            await call.message.edit_text(
                "Не удалось найти заявку. Попробуй позже.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        # Подтягиваем данные СТО
        try:
            sc = await api.get_service_center(sc_id)
        except Exception as e:
            logger.exception("Ошибка при получении СТО %s: %s", sc_id, e)
            await call.message.edit_text(
                "Не удалось получить данные сервиса.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        # Привязываем СТО к заявке
        try:
            await api.update_request(
                request_id,
                {
                    "service_center_id": sc_id,
                    "status": "accepted_by_service",
                },
            )
        except Exception as e:
            logger.exception("Ошибка при обновлении заявки %s: %s", request_id, e)
            await call.message.edit_text(
                "Не удалось привязать сервис к заявке. Попробуй позже.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        # Пытаемся уведомить владельца СТО
        try:
            owner_user_id = sc.get("user_id")
            if owner_user_id:
                svc_user = await api.get_user(owner_user_id)
                svc_tg_id = svc_user.get("telegram_id")
                if svc_tg_id:
                    desc = req.get("description") or "без описания"
                    await bot.send_message(
                        svc_tg_id,
                        (
                            f"📩 Новая заявка #{request_id} закреплена за вашим сервисом.\n\n"
                            f"Описание: {desc}"
                        ),
                        reply_markup=service_assigned_actions_kb(request_id),
                    )

        except Exception as e:
            # Ошибку логируем, но пользователю ничего страшного не говорим
            logger.exception("Ошибка при отправке уведомления СТО: %s", e)

        name = (sc.get("name") or "Без названия").strip()
        text = (
            "Заявка закреплена за сервисом:\n\n"
            f"🏭 <b>{name}</b>\n\n"
            "Менеджер сервиса свяжется с тобой в ближайшее время.\n\n"
            "Следить за статусом можно в разделе «📄 Мои заявки»."
        )

        await state.clear()
        await call.message.edit_text(
            text,
            reply_markup=main_menu_inline(),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data == "req_cancel_choose_sc")
    async def req_cancel_choose_sc(call: CallbackQuery, state: FSMContext):
        """
        Отмена выбора сервиса после создания заявки.
        """
        await state.clear()
        await call.message.edit_text(
            "Выбор сервиса отменён.\n\n"
            "Заявка всё равно сохранена, её можно найти в разделе «📄 Мои заявки».",
            reply_markup=main_menu_inline(),
        )
        await call.answer()

    # ==========================
    #   СТО: РЕГИСТРАЦИЯ
    # ==========================

    @dp.callback_query(F.data == "service_owner_menu")
    async def service_owner_menu(call: CallbackQuery, state: FSMContext):
        """
        Вход в режим владельца СТО.
        """
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при service_owner_menu: %s", e)
            await call.message.edit_text(
                "Не удалось получить данные пользователя.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        # Проверяем, есть ли уже СТО у пользователя
        sc = await _get_user_service_center(user_id)
        if not sc:
            # Предложить зарегистрировать СТО
            await state.clear()
            await state.set_state(ServiceCenterRegistration.waiting_org_type)
            await call.message.edit_text(
                "Ты ещё не зарегистрировал автосервис.\n\n"
                "Давай добавим его в систему! 🚀\n\n"
                "Кто ты?",
                reply_markup=service_org_type_kb(),
            )
            await call.answer()
            return

        # Уже есть СТО — показываем кабинет
        profile_text = format_service_center_profile(sc)
        await call.message.edit_text(
            profile_text,
            reply_markup=service_owner_menu_kb(),
        )
        await call.answer()

    @dp.callback_query(ServiceCenterRegistration.waiting_org_type)
    async def service_org_type_step(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "cancel":
            await state.clear()
            await call.message.edit_text(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        if data not in {"org_type_individual", "org_type_company"}:
            await call.answer()
            return

        org_type = "individual" if data == "org_type_individual" else "company"
        await state.update_data(org_type=org_type)

        await state.set_state(ServiceCenterRegistration.waiting_name)
        await call.message.edit_text(
            "Как называется твой автосервис / мастерская?\n"
            "Можно указать ИП, название компании или просто название.",
            reply_markup=cancel_kb(),
        )
        await call.answer()

    @dp.message(ServiceCenterRegistration.waiting_name)
    async def service_name_step(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_reply(),
            )
            return

        name = (message.text or "").strip()
        if not name:
            await message.answer("Пожалуйста, укажи название или напиши «Отмена».")
            return

        await state.update_data(name=name)
        await state.set_state(ServiceCenterRegistration.waiting_phone)
        await message.answer(
            "Укажи контактный телефон сервиса.\n"
            "Это номер, по которому с тобой можно связаться.",
            reply_markup=cancel_kb(),
        )

    @dp.message(ServiceCenterRegistration.waiting_phone)
    async def service_phone_step(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_reply(),
            )
            return

        phone = (message.text or "").strip()
        if not phone:
            await message.answer("Пожалуйста, укажи телефон или напиши «Отмена».")
            return

        await state.update_data(phone=phone)
        await state.set_state(ServiceCenterRegistration.waiting_city)
        await message.answer(
            "В каком городе находится твой сервис?",
            reply_markup=cancel_kb(),
        )

    @dp.message(ServiceCenterRegistration.waiting_city)
    async def service_city_step(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_reply(),
            )
            return

        city = (message.text or "").strip()
        if not city:
            await message.answer("Пожалуйста, укажи город или напиши «Отмена».")
            return

        await state.update_data(city=city)
        await state.set_state(ServiceCenterRegistration.waiting_address_text)
        await message.answer(
            "Укажи адрес сервиса или основной район работы.\n"
            "Например: «ул. Ленина, 10» или «выезд по всему Минску».",
            reply_markup=cancel_kb(),
        )

    @dp.message(ServiceCenterRegistration.waiting_address_text)
    async def service_address_step(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_reply(),
            )
            return

        addr = (message.text or "").strip()
        if not addr:
            await message.answer("Пожалуйста, укажи адрес / район или напиши «Отмена».")
            return

        await state.update_data(address_text=addr)
        await state.set_state(ServiceCenterRegistration.waiting_geo)
        await message.answer(
            "Теперь отправь геолокацию сервиса или основную точку работы.\n"
            "Это нужно, чтобы подбирать тебя по расстоянию до клиента.\n\n"
            "Отправь локацию или напиши «Отмена».",
            reply_markup=cancel_kb(),
        )

    @dp.message(ServiceCenterRegistration.waiting_geo)
    async def service_geo_step(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_reply(),
            )
            return

        if not message.location:
            await message.answer(
                "Пожалуйста, отправь геолокацию через кнопку отправки местоположения.\n"
                "Или напиши «Отмена»."
            )
            return

        lat = message.location.latitude
        lon = message.location.longitude
        await state.update_data(latitude=lat, longitude=lon)

        await state.set_state(ServiceCenterRegistration.waiting_extra_contacts)
        await message.answer(
            "Если есть дополнительные контакты (сайт, соцсети, второй телефон) — пришли их.\n"
            "Или напиши «-», если ничего добавлять не нужно.",
            reply_markup=cancel_kb(),
        )

    @dp.callback_query(F.data.startswith("svc_req_cond_"))
    async def svc_request_conditions_start(call: CallbackQuery, state: FSMContext):
        """
        Старт ввода условий от СТО по заявке.
        callback_data: svc_req_cond_<request_id>
        """
        raw = call.data or ""
        parts = raw.split("_")
        if len(parts) != 4:
            await call.answer()
            return

        try:
            request_id = int(parts[3])
        except ValueError:
            await call.answer()
            return

        await state.set_state(ServiceRequestStates.waiting_conditions)
        await state.update_data(request_id=request_id)

        await call.message.edit_text(
            f"Заявка #{request_id}\n\n"
            "Напишите условия для клиента в свободной форме:\n"
            "• ориентировочная стоимость\n"
            "• срок выполнения\n"
            "• любые важные детали\n\n"
            "Сообщение будет отправлено клиенту одним блоком.",
        )
        await call.answer()

    @dp.message(ServiceRequestStates.waiting_conditions)
    async def svc_request_conditions_receive(message: Message, state: FSMContext):
        """
        Принимаем текст условий от менеджера и отправляем клиенту.
        """
        text = (message.text or "").strip()
        if not text:
            await message.answer(
                "Пожалуйста, напишите условия одним сообщением. "
                "Например: стоимость, срок, особенности."
            )
            return

        data = await state.get_data()
        request_id = data.get("request_id")
        if not request_id:
            await state.clear()
            await message.answer(
                "Не удалось определить заявку. Попробуйте ещё раз из уведомления.",
                reply_markup=main_menu_inline(),
            )
            return

        # Получаем заявку и пользователя-клиента
        try:
            req = await api.get_request(request_id)
            user_id = req.get("user_id")
            user = await api.get_user(user_id)
            client_tg_id = user.get("telegram_id")
        except Exception as e:
            logger.exception("Ошибка при подготовке условий для заявки %s: %s", request_id, e)
            await state.clear()
            await message.answer(
                "Не удалось отправить условия клиенту. Попробуйте позже.",
                reply_markup=main_menu_inline(),
            )
            return

        await state.clear()

        # Текст клиенту
        req_desc = req.get("description") or "без описания"
        service_text = (
            f"📩 По вашей заявке #{request_id} сервис прислал условия:\n\n"
            f"📝 <b>Условия:</b>\n{text}\n\n"
            f"🚗 <b>Описание заявки:</b> {req_desc}\n\n"
            "Принять эти условия?"
        )

        # Кнопки принять / отклонить
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Принять условия",
                        callback_data=f"offer_accept_{request_id}_{message.from_user.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отклонить условия",
                        callback_data=f"offer_reject_{request_id}_{message.from_user.id}",
                    )
                ],
            ]
        )

        # Отправляем клиенту
        try:
            await message.bot.send_message(
                client_tg_id,
                service_text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.exception("Не удалось отправить условия клиенту: %s", e)
            await message.answer(
                "Не удалось отправить условия клиенту. Попробуйте позже.",
                reply_markup=main_menu_inline(),
            )
            return

        # Подтверждение менеджеру
        await message.answer(
            f"Условия по заявке #{request_id} отправлены клиенту. "
            "Ожидайте его решения.",
            reply_markup=main_menu_inline(),
        )

    @dp.message(ServiceCenterRegistration.waiting_extra_contacts)
    async def service_extra_contacts_step(message: Message, state: FSMContext):
        if message.text and message.text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_reply(),
            )
            return

        extra = (message.text or "").strip()
        if extra == "-":
            extra = ""

        await state.update_data(extra_contacts=extra)

        data = await state.get_data()
        org_type = data.get("org_type")
        name = data.get("name")
        phone = data.get("phone")
        city = data.get("city")
        addr = data.get("address_text")
        lat = data.get("latitude")
        lon = data.get("longitude")

        summary = (
            "Проверь, всё ли верно:\n\n"
            f"Тип: {'Частный мастер' if org_type == 'individual' else 'Автосервис / компания'}\n"
            f"Название: {name}\n"
            f"Телефон: {phone}\n"
            f"Город: {city}\n"
            f"Адрес: {addr}\n"
            f"Геолокация: {lat}, {lon}\n"
        )
        if extra:
            summary += f"Доп. контакты: {extra}\n"

        await state.set_state(ServiceCenterRegistration.waiting_confirm)
        await message.answer(
            summary + "\n\n"
            "Если всё верно — нажми «✅ Всё верно, зарегистрировать».\n"
            "Если передумал — «❌ Отменить».",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Всё верно, зарегистрировать",
                            callback_data="service_reg_confirm_yes",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="❌ Отменить",
                            callback_data="service_reg_confirm_cancel",
                        )
                    ],
                ]
            ),
        )

    @dp.callback_query(F.data.startswith("offer_accept_"))
    async def offer_accept(call: CallbackQuery, state: FSMContext):
        """
        Клиент принимает условия сервиса по заявке.
        callback_data: offer_accept_<request_id>_<service_tg_id>
        """
        raw = call.data or ""
        parts = raw.split("_")
        if len(parts) != 4:
            await call.answer()
            return

        try:
            request_id = int(parts[2])
            service_tg_id = int(parts[3])
        except ValueError:
            await call.answer()
            return

        # 1. Смотрим текущее состояние заявки
        try:
            req = await api.get_request(request_id)
        except Exception as e:
            logger.exception("Ошибка при получении заявки %s: %s", request_id, e)
            await call.message.edit_text(
                "Не удалось получить данные заявки. Попробуй позже.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        current_status = (req.get("status") or "").lower()
        current_sc_id = req.get("service_center_id")

        # Если уже есть выбранный сервис — не даём подтвердить второй раз
        if current_status in {"in_work", "done", "accepted_by_service"} or current_sc_id:
            chosen_name = "другой сервис"
            try:
                if current_sc_id:
                    sc = await api.get_service_center(current_sc_id)
                    chosen_name = (sc.get("name") or "выбранный сервис").strip()
            except Exception as e:
                logger.exception(
                    "Не удалось получить выбранный сервис для заявки %s: %s",
                    request_id,
                    e,
                )

            # Сообщение клиенту
            await call.message.edit_text(
                f"По заявке #{request_id} уже выбран сервис: {chosen_name}.\n\n"
                "Если нужно изменить выбор — создай новую заявку "
                "или свяжись с менеджером.",
                reply_markup=main_menu_inline(),
            )

            # Уведомление сервису, который опоздал
            try:
                await call.bot.send_message(
                    service_tg_id,
                    (
                        f"ℹ️ Клиент по заявке #{request_id} уже выбрал другой сервис.\n"
                        "Ваше предложение не может быть принято."
                    ),
                )
            except Exception as e:
                logger.exception(
                    "Не удалось уведомить сервис об уже выбранном исполнителе: %s",
                    e,
                )

            await call.answer()
            return

        # 2. Пытаемся определить service_center_id по telegram сервиса
        sc_id: int | None = None
        try:
            svc_user = await api.get_user_by_telegram(service_tg_id)
            svc_user_id = svc_user.get("id")
            if svc_user_id:
                sc_list = await api.list_service_centers_by_user(svc_user_id)
                if isinstance(sc_list, list) and sc_list:
                    sc_id = sc_list[0].get("id")
        except Exception as e:
            logger.exception(
                "Не удалось привязать СТО к заявке %s по telegram %s: %s",
                request_id,
                service_tg_id,
                e,
            )

        # 3. Обновляем заявку
        payload: dict[str, Any] = {"status": "in_work"}
        if sc_id:
            payload["service_center_id"] = sc_id

        try:
            await api.update_request(request_id, payload)
        except Exception as e:
            logger.exception(
                "Ошибка при обновлении статуса заявки %s: %s",
                request_id,
                e,
            )

        # Сообщение клиенту
        await call.message.edit_text(
            f"Ты принял условия по заявке #{request_id}. 🚗\n\n"
            "Сервис может приступать к работе. "
            "Следить за статусом можно в разделе «📄 Мои заявки».",
            reply_markup=main_menu_inline(),
        )

        # Уведомление сервису
        try:
            await call.bot.send_message(
                service_tg_id,
                (
                    f"✅ Клиент принял ваши условия по заявке #{request_id}.\n\n"
                    "Можно приступать к работе."
                ),
            )
        except Exception as e:
            logger.exception("Не удалось отправить уведомление сервису: %s", e)

        await call.answer()

    @dp.callback_query(F.data.startswith("offer_reject_"))
    async def offer_reject(call: CallbackQuery, state: FSMContext):
        """
        Клиент отклоняет условия конкретного сервиса по заявке.
        callback_data: offer_reject_<request_id>_<service_tg_id>
        """
        raw = call.data or ""
        parts = raw.split("_")
        if len(parts) != 4:
            await call.answer()
            return

        try:
            request_id = int(parts[2])
            service_tg_id = int(parts[3])
        except ValueError:
            await call.answer()
            return

        # ВАЖНО: не отменяем всю заявку, только отклоняем этого исполнителя.
        await call.message.edit_text(
            f"Ты отклонил условия этого сервиса по заявке #{request_id}. ❌\n\n"
            "Заявка остаётся активной — можно дождаться других откликов "
            "или создать новую заявку с другими параметрами.",
            reply_markup=main_menu_inline(),
        )

        # Уведомление сервису
        try:
            await call.bot.send_message(
                service_tg_id,
                (
                    f"❌ Клиент отклонил предложенные условия по заявке #{request_id}.\n\n"
                    "Вы можете предложить другие условия или дождаться новых заявок."
                ),
            )
        except Exception as e:
            logger.exception("Не удалось отправить уведомление сервису: %s", e)

        await call.answer()

    @dp.callback_query(F.data.startswith("svc_req_decline_"))
    async def svc_request_decline_start(call: CallbackQuery, state: FSMContext):
        """
        СТО хочет отклонить заявку.
        callback_data: svc_req_decline_<request_id>
        """
        raw = call.data or ""
        parts = raw.split("_")
        if len(parts) != 4:
            await call.answer()
            return

        try:
            request_id = int(parts[3])
        except ValueError:
            await call.answer()
            return

        await state.set_state(ServiceRequestStates.waiting_decline_reason)
        await state.update_data(request_id=request_id)

        await call.message.edit_text(
            f"Заявка #{request_id}\n\n"
            "Напишите причину отказа, она будет отправлена клиенту.",
        )
        await call.answer()

    @dp.message(ServiceRequestStates.waiting_decline_reason)
    async def svc_request_decline_reason(message: Message, state: FSMContext):
        reason = (message.text or "").strip()
        data = await state.get_data()
        request_id = data.get("request_id")

        if not request_id:
            await state.clear()
            await message.answer(
                "Не удалось определить заявку. Попробуйте ещё раз из уведомления.",
                reply_markup=main_menu_inline(),
            )
            return

        await state.clear()

        # Обновляем статус заявки
        try:
            await api.update_request(request_id, {"status": "rejected_by_service"})
        except Exception as e:
            logger.exception("Ошибка при обновлении статуса заявки %s: %s", request_id, e)

        # Уведомляем клиента
        try:
            req = await api.get_request(request_id)
            user = await api.get_user(req.get("user_id"))
            client_tg_id = user.get("telegram_id")

            text_client = (
                f"Заявка #{request_id} была отклонена сервисом. ❌\n\n"
                f"Причина: {reason or 'не указана'}"
            )

            await message.bot.send_message(client_tg_id, text_client)
        except Exception as e:
            logger.exception("Не удалось уведомить клиента об отказе: %s", e)

        await message.answer(
            f"Заявка #{request_id} отклонена. Клиент уведомлён.",
            reply_markup=main_menu_inline(),
        )

    @dp.callback_query(ServiceCenterRegistration.waiting_confirm)
    async def service_confirm_step(call: CallbackQuery, state: FSMContext):
        data = call.data or ""
        if data == "service_reg_confirm_cancel":
            await state.clear()
            await call.message.edit_text(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        if data != "service_reg_confirm_yes":
            await call.answer()
            return

        tg_id = call.from_user.id

        # Достаём данные из FSM
        fsm = await state.get_data()
        org_type = fsm.get("org_type")
        name = fsm.get("name")
        phone = fsm.get("phone")
        city = fsm.get("city")
        addr = fsm.get("address_text")
        lat = fsm.get("latitude")
        lon = fsm.get("longitude")
        extra = fsm.get("extra_contacts") or ""

        # Получаем пользователя
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для СТО: %s", e)
            await call.message.edit_text(
                "Ошибка при поиске пользователя. Попробуй позже.",
                reply_markup=main_menu_inline(),
            )
            await state.clear()
            await call.answer()
            return

        payload = {
            "user_id": user_id,
            "org_type": org_type,
            "name": name,
            "phone": phone,
            "city": city,
            "address_text": addr,
            "latitude": lat,
            "longitude": lon,
            "extra_contacts": extra,
        }

        try:
            service_center = await api.create_service_center(payload)
            logger.info("Создан автосервис: %s", service_center)
        except Exception as e:
            logger.exception("Ошибка при создании СТО: %s", e)
            await call.message.edit_text(
                "Ошибка при сохранении автосервиса. Попробуй позже.",
                reply_markup=main_menu_inline(),
            )
            await state.clear()
            await call.answer()
            return

        # Обновляем роль пользователя до service_owner
        try:
            await api.update_user(user_id, {"role": "service_owner"})
        except Exception as e:
            logger.exception("Ошибка при обновлении роли пользователя до service_owner: %s", e)

        await state.clear()

        sc_name = service_center.get("name") or name

        await call.message.edit_text(
            "Готово! 🎯\n\n"
            f"Автосервис «{sc_name}» зарегистрирован в системе.\n"
            "Мы сохранили адрес и геолокацию, чтобы дальше искать тебя как ближайший сервис для клиентов.\n\n"
            "Пока можно вернуться в главное меню:",
            reply_markup=main_menu_inline(),
        )
        await call.answer("СТО зарегистрировано")

    @dp.callback_query(F.data == "service_specs_edit")
    async def service_specs_edit_start(call: CallbackQuery, state: FSMContext):
        """
        Запуск редактирования специализаций СТО.
        """
        tg_id = call.from_user.id

        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для спецов СТО: %s", e)
            await call.message.edit_text(
                "Не удалось получить данные пользователя.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        sc = await _get_user_service_center(user_id)
        if not sc:
            await call.message.edit_text(
                "У тебя пока нет зарегистрированного автосервиса.\n"
                "Сначала зарегистрируй СТО, чтобы управлять специализациями.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        sc_id = sc["id"]
        current_specs = sc.get("specializations") or []

        await state.set_state(ServiceCenterSpecs.waiting_specs)
        await state.update_data(
            service_center_id=sc_id,
            user_id=user_id,
            specs_selected=list(current_specs),
        )

        await call.message.edit_text(
            "Выбери специализации твоего сервиса.\n"
            "Можно выбрать несколько, кнопки переключаются.",
            reply_markup=service_specs_kb(list(current_specs)),
        )
        await call.answer()

    @dp.callback_query(ServiceCenterSpecs.waiting_specs)
    async def service_specs_edit_process(call: CallbackQuery, state: FSMContext):
        data = call.data or ""
        fsm = await state.get_data()
        selected: list[str] = fsm.get("specs_selected", [])
        sc_id = fsm.get("service_center_id")
        user_id = fsm.get("user_id")

        if data == "service_specs_cancel":
            await state.clear()
            # возвращаемся в кабинет СТО
            sc = await _get_user_service_center(user_id)
            if sc:
                await call.message.edit_text(
                    format_service_center_profile(sc),
                    reply_markup=service_owner_menu_kb(),
                )
            else:
                await call.message.edit_text(
                    "Автосервис не найден.",
                    reply_markup=main_menu_inline(),
                )
            await call.answer()
            return

        if data == "service_specs_save":
            await state.clear()
            # сохраняем выбранные специализации
            try:
                await api.update_service_center(sc_id, {"specializations": selected})
            except Exception as e:
                logger.exception("Ошибка при сохранении спецов СТО: %s", e)
                await call.message.edit_text(
                    "Ошибка при сохранении специализаций.",
                    reply_markup=main_menu_inline(),
                )
                await call.answer()
                return

            sc = await _get_user_service_center(user_id)
            if sc:
                await call.message.edit_text(
                    "Специализации обновлены ✅\n\n"
                    + format_service_center_profile(sc),
                    reply_markup=service_owner_menu_kb(),
                )
            else:
                await call.message.edit_text(
                    "Сервис не найден.",
                    reply_markup=main_menu_inline(),
                )
            await call.answer()
            return

        if data.startswith("service_spec_"):
            key = data.split("_", 2)[2]
            if key in selected:
                selected.remove(key)
            else:
                selected.append(key)
            await state.update_data(specs_selected=selected)

            await call.message.edit_reply_markup(
                reply_markup=service_specs_kb(selected),
            )
            await call.answer()
            return

        await call.answer()

    # ==========================
    #   Хендлер на «Назад в меню»
    # ==========================

    @dp.callback_query(F.data == "back_to_main")
    async def back_to_main(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await call.message.edit_text(
            "Главное меню:",
            reply_markup=main_menu_inline(),
        )
        await call.answer()

    # ==========================
    #   Запуск поллинга
    # ==========================

    logger.info("Запуск бота...")
    await dp.start_polling(bot)


def service_specs_kb(selected: list[str]) -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора специализаций СТО.
    """
    specs_map = [
        ("mech", "🔧 Автомеханика"),
        ("tires", "🛞 Шиномонтаж"),
        ("electric", "🔌 Автоэлектрика"),
        ("diag", "📊 Диагностика"),
        ("body", "🧱 Кузовной ремонт"),
        ("aggregates", "⚙️ Ремонт агрегатов"),
    ]

    rows = []
    for key, title in specs_map:
        prefix = "✅ " if key in selected else "⬜ "
        rows.append(
            [
                InlineKeyboardButton(
                    text=prefix + title,
                    callback_data=f"service_spec_{key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="💾 Сохранить",
                callback_data="service_specs_save",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="service_specs_cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


if __name__ == "__main__":
    asyncio.run(main())
