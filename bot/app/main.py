import asyncio
import logging

from aiogram import Bot, Dispatcher, F
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

from typing import Optional

from .config import config
from .api_client import APIClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==========================
#   FSM регистрации
# ==========================

class UserRegistration(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_city = State()


# ==========================
#   FSM новой заявки
# ==========================

class RequestCreate(StatesGroup):
    waiting_move = State()
    waiting_location = State()
    waiting_location_confirm = State()
    waiting_description = State()
    waiting_description_confirm = State()
    waiting_photo_choice = State()
    waiting_date = State()
    waiting_date_confirm = State()
    waiting_time_slot = State()
    waiting_car_select = State()   # выбор авто из гаража
    waiting_confirm = State()


# ==========================
#   FSM гаража (авто)
# ==========================

class CarAdd(StatesGroup):
    """
    Добавление нового автомобиля в гараж.
    """
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


# ==========================
#   FSM регистрации СТО
# ==========================

class ServiceCenterRegistration(StatesGroup):
    """
    Регистрация автосервиса / частного мастера.
    """
    waiting_org_type = State()   # ФЛ / ЮЛ
    waiting_name = State()       # название сервиса / имя мастера
    waiting_phone = State()      # контактный телефон
    waiting_city = State()       # город
    waiting_address = State()    # адрес / ориентир
    waiting_extra = State()      # доп. контакты (сайт, соцсети)
    waiting_confirm = State()    # подтверждение и запись в backend


# ==========================
#   Inline / Reply клавиатуры
# ==========================

def main_menu_inline() -> InlineKeyboardMarkup:
    """
    Главное меню бота.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"),
                InlineKeyboardButton(text="🚗 Мой гараж", callback_data="menu_garage"),
            ],
            [
                InlineKeyboardButton(text="🆕 Новая заявка", callback_data="menu_new_request"),
            ],
            [
                InlineKeyboardButton(text="📄 Мои заявки", callback_data="menu_my_requests"),
            ],
            [
                InlineKeyboardButton(text="🏭 Я представляю автосервис", callback_data="menu_service"),
            ],
        ]
    )


def service_org_type_kb() -> InlineKeyboardMarkup:
    """
    Выбор типа организации: ФЛ / ЮЛ.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🙋‍♂️ Частный мастер (ФЛ)",
                    callback_data="service_org_fl",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏢 Юрлицо / автосервис (ООО, ИП и т.п.)",
                    callback_data="service_org_ul",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В главное меню",
                    callback_data="service_back_to_menu",
                )
            ],
        ]
    )


def service_reg_confirm_kb() -> InlineKeyboardMarkup:
    """
    Подтверждение регистрации СТО.
    """
    return InlineKeyboardMarkup(
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
    )


def request_move_kb() -> InlineKeyboardMarkup:
    """
    Вопрос: авто едет / нужна эвакуация.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚗 Едет самостоятельно",
                    callback_data="req_move_self",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🆘 Нужна эвакуация / выездной мастер",
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


def location_reply_kb() -> ReplyKeyboardMarkup:
    """
    Обычная клавиатура на шаге гео:
    - Отправить геолокацию
    - Пропустить
    - Отменить заявку
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📍 Отправить геолоцацию",
                    request_location=True,
                ),
            ],
            [
                KeyboardButton(text="Пропустить"),
            ],
            [
                KeyboardButton(text="Отменить заявку"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Отправь геолокацию или напиши адрес…",
        one_time_keyboard=True,
    )


def photo_reply_kb() -> ReplyKeyboardMarkup:
    """
    Клавиатура для шага с фото:
    - Отправить фото (текстовая кнопка-подсказка)
    - Пропустить
    - Отменить заявку
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📷 Отправить фото"),
            ],
            [
                KeyboardButton(text="Пропустить"),
            ],
            [
                KeyboardButton(text="Отменить заявку"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Прикрепи фото или нажми «Пропустить»…",
        one_time_keyboard=True,
    )


def request_time_slot_kb() -> InlineKeyboardMarkup:
    """
    Временной интервал + отмена.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕘 До 12:00",
                    callback_data="req_slot_morning",
                ),
                InlineKeyboardButton(
                    text="🕒 12:00–18:00",
                    callback_data="req_slot_day",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🌙 После 18:00",
                    callback_data="req_slot_evening",
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


def location_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Всё верно",
                    callback_data="req_loc_ok",
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data="req_loc_edit",
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


def date_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Всё верно",
                    callback_data="req_date_ok",
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data="req_date_edit",
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


def car_select_kb(cars: list[dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора авто из гаража.
    Каждая машина — отдельная строка.
    Внизу:
    - «Без привязки к авто»
    - «Отменить заявку»
    """
    rows: list[list[InlineKeyboardButton]] = []

    for car in cars:
        car_id = car.get("id")
        if car_id is None:
            continue

        parts = []
        brand = (car.get("brand") or "").strip()
        model = (car.get("model") or "").strip()
        plate = (car.get("license_plate") or "").strip()
        year = car.get("year")

        title_parts = []
        if brand:
            title_parts.append(brand)
        if model:
            title_parts.append(model)

        title = " ".join(title_parts) if title_parts else f"Авто #{car_id}"

        if plate:
            title += f" • {plate}"
        elif year:
            title += f" • {year} г."

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


def final_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить заявку",
                    callback_data="req_confirm_yes",
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


# ==========================
#   main()
# ==========================

async def main() -> None:
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    api = APIClient()

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
            logger.warning("get_user_by_telegram error: %s", e)

        # если профиль есть → показываем меню
        if user and (user.get("full_name") or user.get("phone") or user.get("city")):
            name = user.get("full_name") or message.from_user.full_name or "друг"
            await message.answer(
                f"С возвращением, {name}! 🚗\n\n"
                "Я помогу найти автосервис, оформить заявку или управлять гаражом.\n"
                "Выбери, что делаем:",
                reply_markup=main_menu_inline(),
            )
            return

        # если нет — создаём черновик
        if not user:
            try:
                logger.info("Создаём пользователя tg_id=%s", tg_id)
                user = await api.create_user(tg_id)
            except Exception as e:
                logger.exception("Ошибка при создании пользователя: %s", e)
                await message.answer(
                    "Произошла ошибка при создании профиля 😔\n"
                    "Попробуй ещё раз чуть позже."
                )
                return

        # запускаем регистрацию
        await message.answer(
            "Добро пожаловать в CarBot V2! 🎉\n"
            "Давай заполним короткий профиль.\n\n"
            "Как к тебе обращаются?"
        )
        await state.set_state(UserRegistration.waiting_full_name)

    # ---------- Регистрация ----------

    @dp.message(UserRegistration.waiting_full_name)
    async def reg_full_name(message: Message, state: FSMContext):
        await state.update_data(full_name=message.text.strip())
        await message.answer("Отправь, пожалуйста, номер телефона:")
        await state.set_state(UserRegistration.waiting_phone)

    @dp.message(UserRegistration.waiting_phone)
    async def reg_phone(message: Message, state: FSMContext):
        await state.update_data(phone=message.text.strip())
        await message.answer("Из какого ты города?")
        await state.set_state(UserRegistration.waiting_city)

    @dp.message(UserRegistration.waiting_city)
    async def reg_city(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        city = message.text.strip()
        data = await state.get_data()
        full_name = data.get("full_name")
        phone = data.get("phone")

        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]

            await api.update_user(
                user_id,
                {
                    "full_name": full_name,
                    "phone": phone,
                    "city": city,
                    "role": user.get("role") or "client",
                },
            )
        except Exception as e:
            logger.exception("Ошибка при сохранении профиля: %s", e)
            await message.answer(
                "Регистрация почти завершена, но сервер временно недоступен.\n"
                "Попробуй позже или нажми /profile для проверки."
            )
            await state.clear()
            return

        await state.clear()

        await message.answer(
            "Регистрация завершена! ✅\n\n"
            f"Имя: {full_name}\n"
            f"Телефон: {phone}\n"
            f"Город: {city}\n\n"
            "Теперь можно переходить к гаражу и заявкам 🚗\n"
            "Выбери действие:",
            reply_markup=main_menu_inline(),
        )

    # ---------- /profile и кнопка профиля ----------

    @dp.message(Command("profile"))
    async def cmd_profile_command(message: Message):
        tg_id = message.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception as e:
            logger.exception("Ошибка при получении профиля: %s", e)
            await message.answer(
                "Профиль не найден или сервер недоступен.\n"
                "Нажми /start, чтобы пройти регистрацию."
            )
            return

        text = (
            "Ваш профиль:\n\n"
            f"Имя: {user.get('full_name') or '—'}\n"
            f"Телефон: {user.get('phone') or '—'}\n"
            f"Город: {user.get('city') or '—'}\n"
            f"Роль: {user.get('role') or '—'}\n"
            f"Бонусы: {user.get('bonus_balance', 0)}"
        )

        await message.answer(text, reply_markup=main_menu_inline())

    @dp.callback_query(F.data == "menu_profile")
    async def cb_profile(call: CallbackQuery):
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception:
            await call.message.answer(
                "Профиль не найден или сервер недоступен.\n"
                "Нажми /start, чтобы пройти регистрацию."
            )
            await call.answer()
            return

        text = (
            "Ваш профиль:\n\n"
            f"Имя: {user.get('full_name') or '—'}\n"
            f"Телефон: {user.get('phone') or '—'}\n"
            f"Город: {user.get('city') or '—'}\n"
            f"Роль: {user.get('role') or '—'}\n"
            f"Бонусы: {user.get('bonus_balance', 0)}"
        )

        await call.message.edit_text(text, reply_markup=main_menu_inline())
        await call.answer()

    # ---------- /menu ----------

    @dp.message(Command("menu"))
    async def cmd_menu(message: Message):
        await message.answer("Главное меню 👇", reply_markup=main_menu_inline())
    
    def _format_car_title(car: dict) -> str:
        """
        Краткое название авто для кнопок/списков.
        """
        car_id = car.get("id")
        brand = (car.get("brand") or "").strip()
        model = (car.get("model") or "").strip()
        plate = (car.get("license_plate") or "").strip()
        year = car.get("year")

        parts = []
        if brand:
            parts.append(brand)
        if model:
            parts.append(model)

        title = " ".join(parts) if parts else f"Авто #{car_id or ''}"

        if plate:
            title += f" • {plate}"
        elif year:
            title += f" • {year} г."

        return title

    # ==========================
    #   МОИ ЗАЯВКИ
    # ==========================

    @dp.callback_query(F.data == "menu_my_requests")
    async def cb_my_requests(call: CallbackQuery, state: FSMContext):
        """
        Просмотр списка заявок пользователя.
        """
        await state.clear()
        tg_id = call.from_user.id

        # 1. Находим пользователя по telegram_id
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для 'Мои заявки': %s", e)
            await call.message.edit_text(
                "Не получилось найти твой профиль 😔\n"
                "Нажми /start, чтобы пройти регистрацию заново.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        user_id = user["id"]

        # 2. Получаем список заявок
        try:
            requests_list = await api.list_requests_by_user(user_id)
        except Exception as e:
            logger.exception("Ошибка при получении списка заявок: %s", e)
            requests_list = []

        if not requests_list:
            text = (
                "📄 У тебя пока нет заявок.\n\n"
                "Можешь создать первую через кнопку «🆕 Новая заявка»."
            )
        else:
            # отображаем максимум 10 последних
            items = requests_list[:10]

            status_titles = {
                "new": "🟡 Новая",
                "sent": "📨 Разослана СТО",
                "accepted_by_service": "✅ Принята СТО",
                "in_work": "🛠 В работе",
                "done": "🎉 Выполнена",
                "cancelled": "❌ Отменена",
                "rejected_by_service": "🚫 Отклонена СТО",
            }

            lines = ["📄 Твои заявки:\n"]

            for r in items:
                rid = r.get("id")
                status_raw = r.get("status")
                # статус может приходить как строка Enum-а, типа "new" или "RequestStatus.NEW"
                if isinstance(status_raw, str) and status_raw.startswith("RequestStatus."):
                    status_key = status_raw.split(".", 1)[1]
                else:
                    status_key = status_raw

                status_text = status_titles.get(str(status_key), str(status_raw) or "—")

                addr = (r.get("address_text") or "").strip()
                if not addr:
                    addr = "Адрес не указан"

                short_descr = (r.get("description") or "").strip()
                if len(short_descr) > 80:
                    short_descr = short_descr[:77] + "..."

                lines.append(
                    f"• Заявка #{rid} — {status_text}\n"
                    f"  📍 {addr}\n"
                    f"  🔧 {short_descr}\n"
                )

            text = "\n".join(lines)
            text += "\n\nПока это краткий список. В детализацию и чат по заявке пойдём на следующих шагах 😉"

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить список",
                        callback_data="menu_my_requests",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ В главное меню",
                        callback_data="myreq_to_menu",
                    )
                ],
            ]
        )

        await call.message.edit_text(text, reply_markup=kb)
        await call.answer()

    @dp.callback_query(F.data == "myreq_to_menu")
    async def cb_my_requests_to_menu(call: CallbackQuery, state: FSMContext):
        """
        Возврат из 'Мои заявки' в главное меню.
        """
        await state.clear()
        await call.message.edit_text(
            "Главное меню:",
            reply_markup=main_menu_inline(),
        )
        await call.answer()

    # ==========================
    #   ГАРАЖ
    # ==========================

    @dp.callback_query(F.data == "menu_garage")
    async def cb_garage(call: CallbackQuery, state: FSMContext):
        """
        Главный экран гаража: список машин + кнопка добавить.
        """
        tg_id = call.from_user.id

        # Получаем пользователя
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для гаража: %s", e)
            await call.message.edit_text(
                "Не смог найти твой профиль 😔\n"
                "Нажми /start, чтобы пройти регистрацию.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        user_id = user["id"]

        # Получаем список машин
        try:
            cars = await api.list_cars(user_id=user_id)
        except Exception as e:
            logger.exception("Ошибка при получении списка машин: %s", e)
            cars = []

        if cars:
            lines = ["🚗 Твой гараж:\n"]
            for car in cars:
                lines.append(f"• {_format_car_title(car)}")
            text = "\n".join(lines)
            text += (
                "\n\nТы можешь добавить новый автомобиль "
                "или выбрать существующий для редактирования."
            )
        else:
            text = (
                "🚗 В гараже пока нет ни одного автомобиля.\n\n"
                "Добавь свой первый авто, чтобы не вводить данные каждый раз."
            )

        # Клавиатура: по кнопке на каждую машину + кнопка "Добавить" + "В меню"
        kb_rows = []

        for car in cars:
            car_id = car.get("id")
            if car_id is None:
                continue
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✏️ {_format_car_title(car)}",
                        callback_data=f"garage_edit_{car_id}",
                    )
                ]
            )

        kb_rows.append(
            [
                InlineKeyboardButton(
                    text="➕ Добавить авто",
                    callback_data="garage_add",
                )
            ]
        )
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️ В главное меню",
                    callback_data="garage_to_menu",
                )
            ]
        )

        await state.clear()
        await call.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        )
        await call.answer()

    @dp.callback_query(F.data == "garage_to_menu")
    async def cb_garage_to_menu(call: CallbackQuery, state: FSMContext):
        """
        Возврат в главное меню из гаража.
        """
        await state.clear()
        await call.message.edit_text(
            "Главное меню:",
            reply_markup=main_menu_inline(),
        )
        await call.answer()

        # ---------- Добавление нового авто ----------

    @dp.callback_query(F.data == "garage_add")
    async def cb_garage_add(call: CallbackQuery, state: FSMContext):
        """
        Старт добавления нового авто.
        """
        await state.set_state(CarAdd.waiting_brand)
        await state.update_data(edit_car_id=None)

        # В edit_text НЕ передаём ReplyKeyboardRemove — только текст.
        await call.message.edit_text(
            "Добавление автомобиля в гараж.\n\n"
            "Шаг 1 из 5.\n"
            "Напиши марку авто (например, BMW).\n\n"
            "Если передумал — напиши «Отмена».",
        )
        await call.answer()

    @dp.message(CarAdd.waiting_brand)
    async def car_add_brand(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пожалуйста, введи марку авто или напиши «Отмена».")
            return
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.", reply_markup=main_menu_inline()
            )
            return

        await state.update_data(brand=text)
        await state.set_state(CarAdd.waiting_model)
        await message.answer(
            "Шаг 2 из 5.\n\n"
            "Теперь введи модель авто (например, X5).\n\n"
            "Если передумал — напиши «Отмена».",
        )

    @dp.message(CarAdd.waiting_model)
    async def car_add_model(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пожалуйста, введи модель авто или напиши «Отмена».")
            return
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.", reply_markup=main_menu_inline()
            )
            return

        await state.update_data(model=text)
        await state.set_state(CarAdd.waiting_year)
        await message.answer(
            "Шаг 3 из 5.\n\n"
            "Введи год выпуска авто (например, 2015)\n"
            "или напиши «Пропустить», если не хочешь указывать.",
        )

    @dp.message(CarAdd.waiting_year)
    async def car_add_year(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.", reply_markup=main_menu_inline()
            )
            return

        year: Optional[int] = None
        if text.lower() not in ("пропустить", "skip", "-"):
            try:
                year_val = int(text)
                if year_val < 1950 or year_val > 2100:
                    raise ValueError
                year = year_val
            except ValueError:
                await message.answer(
                    "Пожалуйста, введи год цифрами (например, 2015)\n"
                    "или напиши «Пропустить».",
                )
                return

        await state.update_data(year=year)
        await state.set_state(CarAdd.waiting_plate)
        await message.answer(
            "Шаг 4 из 5.\n\n"
            "Введи госномер (например, А123ВС77)\n"
            "или напиши «Пропустить».",
        )

    @dp.message(CarAdd.waiting_plate)
    async def car_add_plate(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.", reply_markup=main_menu_inline()
            )
            return

        plate: Optional[str] = None
        if text.lower() not in ("пропустить", "skip", "-"):
            plate = text

        await state.update_data(license_plate=plate)
        await state.set_state(CarAdd.waiting_vin)
        await message.answer(
            "Шаг 5 из 5.\n\n"
            "Введи VIN (17 символов) или напиши «Пропустить».",
        )

    @dp.message(CarAdd.waiting_vin)
    async def car_add_vin(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Добавление авто отменено.", reply_markup=main_menu_inline()
            )
            return

        vin: Optional[str] = None
        if text.lower() not in ("пропустить", "skip", "-"):
            vin = text

        data = await state.get_data()
        brand = data.get("brand")
        model = data.get("model")
        year = data.get("year")
        plate = data.get("license_plate")

        tg_id = message.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя при добавлении авто: %s", e)
            await state.clear()
            await message.answer(
                "Не удалось сохранить авто: не найден профиль пользователя 😔\n"
                "Попробуй ещё раз через /start.",
                reply_markup=main_menu_inline(),
            )
            return

        payload = {
            "user_id": user_id,
            "brand": brand,
            "model": model,
            "year": year,
            "license_plate": plate,
            "vin": vin,
        }

        try:
            car = await api.create_car(payload)
        except Exception as e:
            logger.exception("Ошибка при создании авто в backend: %s", e)
            await state.clear()
            await message.answer(
                "Не получилось сохранить автомобиль 😔\n"
                "Попробуй ещё раз чуть позже.",
                reply_markup=main_menu_inline(),
            )
            return

        await state.clear()

        await message.answer(
            "Автомобиль сохранён в твоём гараже ✅\n\n"
            f"{_format_car_title(car)}\n\n"
            "В любой момент ты сможешь отредактировать его в разделе «Мой гараж».",
            reply_markup=main_menu_inline(),
        )

    # ---------- Редактирование существующего авто ----------
    @dp.callback_query(F.data.startswith("garage_edit_"))
    async def cb_garage_edit(call: CallbackQuery, state: FSMContext):
        raw = call.data or ""
        try:
            car_id = int(raw.split("_")[-1])
        except ValueError:
            await call.answer()
            return

        try:
            car = await api.get_car(car_id)
        except Exception as e:
            logger.exception("Ошибка при загрузке авто для редактирования: %s", e)
            await call.message.edit_text(
                "Не удалось загрузить данные автомобиля 😔",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        await state.set_state(CarEdit.waiting_brand)
        await state.update_data(edit_car_id=car_id)

        text = (
            "Редактирование автомобиля.\n\n"
            "Текущие данные:\n"
            f"Марка: {car.get('brand') or '—'}\n"
            f"Модель: {car.get('model') or '—'}\n"
            f"Год: {car.get('year') or '—'}\n"
            f"Госномер: {car.get('license_plate') or '—'}\n"
            f"VIN: {car.get('vin') or '—'}\n\n"
            "Шаг 1 из 5.\n"
            "Напиши новую марку авто (или повтори текущую).\n\n"
            "Если передумал — напиши «Отмена»."
        )

        # Снова: edit_text без ReplyKeyboardRemove
        await call.message.edit_text(text)
        await call.answer()

    @dp.message(CarEdit.waiting_brand)
    async def car_edit_brand(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Редактирование авто отменено.", reply_markup=main_menu_inline()
            )
            return

        await state.update_data(brand=text)
        await state.set_state(CarEdit.waiting_model)
        await message.answer(
            "Шаг 2 из 5.\n\n"
            "Теперь введи модель авто.",
        )

    @dp.message(CarEdit.waiting_model)
    async def car_edit_model(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Редактирование авто отменено.", reply_markup=main_menu_inline()
            )
            return

        await state.update_data(model=text)
        await state.set_state(CarEdit.waiting_year)
        await message.answer(
            "Шаг 3 из 5.\n\n"
            "Введи год выпуска (или напиши «Пропустить»).",
        )

    @dp.message(CarEdit.waiting_year)
    async def car_edit_year(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Редактирование авто отменено.", reply_markup=main_menu_inline()
            )
            return

        year: Optional[int] = None
        if text.lower() not in ("пропустить", "skip", "-"):
            try:
                year_val = int(text)
                if year_val < 1950 or year_val > 2100:
                    raise ValueError
                year = year_val
            except ValueError:
                await message.answer(
                    "Пожалуйста, введи год цифрами (например, 2015)\n"
                    "или напиши «Пропустить».",
                )
                return

        await state.update_data(year=year)
        await state.set_state(CarEdit.waiting_plate)
        await message.answer(
            "Шаг 4 из 5.\n\n"
            "Введи госномер (или напиши «Пропустить»).",
        )

    @dp.message(CarEdit.waiting_plate)
    async def car_edit_plate(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Редактирование авто отменено.", reply_markup=main_menu_inline()
            )
            return

        plate: Optional[str] = None
        if text.lower() not in ("пропустить", "skip", "-"):
            plate = text

        await state.update_data(license_plate=plate)
        await state.set_state(CarEdit.waiting_vin)
        await message.answer(
            "Шаг 5 из 5.\n\n"
            "Введи VIN (или напиши «Пропустить»).",
        )

    @dp.message(CarEdit.waiting_vin)
    async def car_edit_vin(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Редактирование авто отменено.", reply_markup=main_menu_inline()
            )
            return

        vin: Optional[str] = None
        if text.lower() not in ("пропустить", "skip", "-"):
            vin = text

        data = await state.get_data()
        car_id = data.get("edit_car_id")
        if not car_id:
            await state.clear()
            await message.answer(
                "Что-то пошло не так при редактировании авто 😔",
                reply_markup=main_menu_inline(),
            )
            return

        brand = data.get("brand")
        model = data.get("model")
        year = data.get("year")
        plate = data.get("license_plate")

        payload = {
            "brand": brand,
            "model": model,
            "year": year,
            "license_plate": plate,
            "vin": vin,
        }

        try:
            car = await api.update_car(car_id, payload)
        except Exception as e:
            logger.exception("Ошибка при обновлении авто в backend: %s", e)
            await state.clear()
            await message.answer(
                "Не получилось сохранить изменения автомобиля 😔\n"
                "Попробуй ещё раз чуть позже.",
                reply_markup=main_menu_inline(),
            )
            return

        await state.clear()

        await message.answer(
            "Данные автомобиля обновлены ✅\n\n"
            f"{_format_car_title(car)}",
            reply_markup=main_menu_inline(),
        )

    # ==========================
    #   СТО: регистрация
    # ==========================

    @dp.callback_query(F.data == "menu_service")
    async def cb_service_start(call: CallbackQuery, state: FSMContext):
        """
        Старт регистрации автосервиса / частного мастера.
        """
        tg_id = call.from_user.id

        # Проверяем, что пользователь существует
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception as e:
            logger.exception("Ошибка при получении пользователя для регистрации СТО: %s", e)
            await call.message.edit_text(
                "Не удалось найти твой профиль 😔\n"
                "Нажми /start и пройди регистрацию ещё раз.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        await state.clear()
        await state.set_state(ServiceCenterRegistration.waiting_org_type)

        await call.message.edit_text(
            "Ты указал(а), что представляешь автосервис.\n\n"
            "Давай зарегистрируем его в системе.\n\n"
            "Кто ты по форме работы?",
            reply_markup=service_org_type_kb(),
        )
        await call.answer()

    @dp.callback_query(ServiceCenterRegistration.waiting_org_type)
    async def cb_service_org_type(call: CallbackQuery, state: FSMContext):
        data = call.data or ""

        if data == "service_back_to_menu":
            await state.clear()
            await call.message.edit_text(
                "Главное меню:",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        if data not in {"service_org_fl", "service_org_ul"}:
            await call.answer()
            return

        org_type = "individual" if data == "service_org_fl" else "company"
        await state.update_data(org_type=org_type)

        await state.set_state(ServiceCenterRegistration.waiting_name)
        await call.message.edit_text(
            "Шаг 1 из 5.\n\n"
            "Как называется твой сервис?\n"
            "▫️ Для частника можно просто указать имя / направление\n"
            "   (например, «Иван, выездной автоэлектрик»)\n"
            "▫️ Для сервиса — официальное название (например, «АвтоСервис 24»).",
        )
        await call.answer()

    @dp.message(ServiceCenterRegistration.waiting_name)
    async def service_name_step(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пожалуйста, укажи название сервиса.")
            return
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_inline(),
            )
            return

        await state.update_data(name=text)
        await state.set_state(ServiceCenterRegistration.waiting_phone)

        await message.answer(
            "Шаг 2 из 5.\n\n"
            "Укажи контактный телефон для клиентов.\n"
            "Можно в любом формате (с кодом страны или без)."
        )

    @dp.message(ServiceCenterRegistration.waiting_phone)
    async def service_phone_step(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пожалуйста, укажи телефон или напиши «Отмена».")
            return
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_inline(),
            )
            return

        await state.update_data(phone=text)
        await state.set_state(ServiceCenterRegistration.waiting_city)

        await message.answer(
            "Шаг 3 из 5.\n\n"
            "В каком городе ты работаешь?",
        )

    @dp.message(ServiceCenterRegistration.waiting_city)
    async def service_city_step(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пожалуйста, укажи город или напиши «Отмена».")
            return
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_inline(),
            )
            return

        await state.update_data(city=text)
        await state.set_state(ServiceCenterRegistration.waiting_address)

        await message.answer(
            "Шаг 4 из 5.\n\n"
            "Укажи адрес сервиса или основной район работы.\n"
            "Например: «ул. Ленина, 10» или «выезд по всему Минску».",
        )

    @dp.message(ServiceCenterRegistration.waiting_address)
    async def service_address_step(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пожалуйста, укажи адрес / район или напиши «Отмена».")
            return
        if text.lower() == "отмена":
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_inline(),
            )
            return

        await state.update_data(address=text)
        await state.set_state(ServiceCenterRegistration.waiting_extra)

        await message.answer(
            "Шаг 5 из 5.\n\n"
            "Укажи доп. контакты (если есть): сайт, Instagram, WhatsApp, Telegram-ник и т.п.\n"
            "Если ничего добавлять не нужно — напиши «Пропустить».",
        )

    @dp.message(ServiceCenterRegistration.waiting_extra)
    async def service_extra_step(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text.lower() in {"отмена"}:
            await state.clear()
            await message.answer(
                "Регистрация СТО отменена.",
                reply_markup=main_menu_inline(),
            )
            return

        extra = None
        if text.lower() not in {"пропустить", "skip", "-"}:
            extra = text

        data = await state.get_data()

        org_type = data.get("org_type")
        org_title = "Частный мастер" if org_type == "individual" else "Автосервис / компания"

        name = data.get("name")
        phone = data.get("phone")
        city = data.get("city")
        address = data.get("address")

        await state.update_data(extra=extra)

        summary_lines = [
            "Проверь, пожалуйста, данные СТО:\n",
            f"👤 Тип: {org_title}",
            f"🏷 Название: {name}",
            f"📞 Телефон: {phone}",
            f"🏙 Город: {city}",
            f"📍 Адрес / район: {address}",
        ]
        if extra:
            summary_lines.append(f"🌐 Доп. контакты: {extra}")

        summary = "\n".join(summary_lines)

        await state.set_state(ServiceCenterRegistration.waiting_confirm)
        await message.answer(
            summary + "\n\n"
            "Если всё верно — нажми «✅ Всё верно, зарегистрировать».\n"
            "Если передумал — «❌ Отменить».",
            reply_markup=service_reg_confirm_kb(),
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
        fsm_data = await state.get_data()
        org_type = fsm_data.get("org_type")
        name = fsm_data.get("name")
        phone = fsm_data.get("phone")
        city = fsm_data.get("city")
        address = fsm_data.get("address")
        extra = fsm_data.get("extra")

        # Находим пользователя
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя при финале регистрации СТО: %s", e)
            await state.clear()
            await call.message.edit_text(
                "Не получилось найти твой профиль 😔\n"
                "Попробуй ещё раз через /start.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        # Формируем payload для backend-а
        payload = {
            "user_id": user_id,
            "org_type": org_type,          # "individual" / "company"
            "name": name,
            "phone": phone,
            "city": city,
            "address_text": address,
            "extra_contacts": extra,       # если в схеме такого поля нет — уберём позже
        }

        logger.info("Регистрируем СТО в backend: %s", payload)

        # Создаём СТО через нормальный метод API-клиента
        try:
            service_center = await api.create_service_center(payload)
        except Exception as e:
            logger.exception("Ошибка при создании СТО в backend: %s", e)
            await state.clear()
            await call.message.edit_text(
                "Не получилось сохранить автосервис на сервере 😔\n"
                "Попробуй ещё раз чуть позже.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        # Обновляем роль пользователя → service_owner
        try:
            await api.update_user(
                user_id,
                {"role": "service_owner"},
            )
        except Exception as e:
            logger.exception("Ошибка при обновлении роли пользователя до service_owner: %s", e)
            # не падаем, роль можно будет поправить позже

        await state.clear()

        sc_name = service_center.get("name") or name

        await call.message.edit_text(
            "Готово! 🎯\n\n"
            f"Автосервис «{sc_name}» зарегистрирован в системе.\n"
            "Скоро добавим выбор специализаций, зону обслуживания и приём заявок от клиентов.\n\n"
            "Пока можно вернуться в главное меню:",
            reply_markup=main_menu_inline(),
        )
        await call.answer("СТО зарегистрировано")

    # ==========================
    #   НОВАЯ ЗАЯВКА
    # ==========================

    @dp.callback_query(F.data == "menu_new_request")
    async def cb_new_request_start(call: CallbackQuery, state: FSMContext):
        """
        Старт мастера: сначала спрашиваем,
        едет ли авто или нужна эвакуация.
        """
        await state.clear()
        await state.set_state(RequestCreate.waiting_move)

        await call.message.answer(
            "Создаём новую заявку 🚗\n\n"
            "Шаг 1.\n"
            "Автомобиль передвигается самостоятельно\n"
            "или нужна эвакуация / выездной мастер?",
            reply_markup=request_move_kb(),
        )
        await call.answer()

    # ---------- Отмена заявки (inline, глобально для FSM RequestCreate) ----------

    @dp.callback_query(StateFilter(RequestCreate), F.data == "req_cancel")
    async def req_cancel(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await call.message.edit_text(
            "Создание заявки отменено ❌\n\n"
            "Ты всегда можешь начать заново через «🆕 Новая заявка».",
            reply_markup=main_menu_inline(),
        )
        await call.answer("Заявка отменена")

    # ---------- Отмена заявки (reply-клавиатура: текст «Отменить заявку») ----------

    @dp.message(StateFilter(RequestCreate), F.text.casefold() == "отменить заявку")
    async def req_cancel_text(message: Message, state: FSMContext):
        await state.clear()
        await message.answer(
            "Создание заявки отменено ❌\n\n"
            "Ты всегда можешь начать заново через «🆕 Новая заявка».",
            reply_markup=main_menu_inline(),
        )

    # ---------- Шаг 1: авто едет / эвакуация ----------

    @dp.callback_query(RequestCreate.waiting_move, F.data.in_({"req_move_self", "req_move_help"}))
    async def req_move_choice(call: CallbackQuery, state: FSMContext):
        move_type = "self" if call.data == "req_move_self" else "help"
        await state.update_data(move_type=move_type)

        # Если авто ЕДЕТ САМО — шаг с гео пропускаем.
        if move_type == "self":
            # Сразу ставим "виртуальное" местоположение
            await state.update_data(
                latitude=None,
                longitude=None,
                address=None,
                loc_text="Местоположение не указано (авто едет самостоятельно)",
            )

            await call.message.answer(
                "Шаг 2.\n\n"
                "Опиши проблему своими словами.\n"
                "Чем точнее описание — тем точнее диагностика и оценка стоимости.",
            )
            await state.set_state(RequestCreate.waiting_description)
            await call.answer()
            return

        # Если нужна эвакуация / выездной мастер — спрашиваем место
        text = (
            "Шаг 2.\n\n"
            "Где находится автомобиль или откуда удобнее забрать?\n\n"
            "▫️ Отправь геолокацию кнопкой ниже\n"
            "▫️ Или напиши адрес / ориентир текстом\n"
            "▫️ В крайнем случае можно нажать «Пропустить», "
            "но тогда подобрать эвакуацию будет сложнее."
        )

        await call.message.answer(text, reply_markup=location_reply_kb())
        await state.set_state(RequestCreate.waiting_location)
        await call.answer()

    # ---------- Шаг 2: локация (только для эвакуации) ----------

    @dp.message(RequestCreate.waiting_location)
    async def req_location(message: Message, state: FSMContext):
        """
        Принимаем:
        - геолокацию (кнопка)
        - текст (адрес / район)
        - слово «Пропустить»
        - «Отменить заявку» обрабатывается отдельным хендлером
        """
        latitude = None
        longitude = None
        address = None
        loc_text = ""

        if message.location:
            latitude = message.location.latitude
            longitude = message.location.longitude

            # Яндекс.Карты
            url = f"https://yandex.ru/maps/?ll={longitude:.6f}%2C{latitude:.6f}&z=16"
            loc_text = f"Яндекс.Карты: {url}"
        else:
            text = (message.text or "").strip()
            if text.lower() == "пропустить":
                loc_text = "Местоположение не указано"
            else:
                # Любой другой текст трактуем как адрес
                address = text
                loc_text = f"Адрес / ориентир: {address}"

        await state.update_data(
            latitude=latitude,
            longitude=longitude,
            address=address,
            loc_text=loc_text,
        )

        # убираем reply-клавиатуру
        await message.answer("Спасибо! Зафиксировал местоположение.", reply_markup=ReplyKeyboardRemove())

        # подтверждение
        await message.answer(
            "Ты указал(а):\n"
            f"{loc_text}\n\n"
            "Всё верно?",
            reply_markup=location_confirm_kb(),
        )
        await state.set_state(RequestCreate.waiting_location_confirm)

    @dp.callback_query(RequestCreate.waiting_location_confirm, F.data == "req_loc_ok")
    async def req_location_ok(call: CallbackQuery, state: FSMContext):
        await call.answer("Местоположение подтверждено")

        await call.message.answer(
            "Шаг 3.\n\n"
            "Опиши проблему своими словами.\n"
            "Чем точнее описание — тем точнее диагностика и оценка стоимости.",
        )
        await state.set_state(RequestCreate.waiting_description)

    @dp.callback_query(RequestCreate.waiting_location_confirm, F.data == "req_loc_edit")
    async def req_location_edit(call: CallbackQuery, state: FSMContext):
        await call.answer("Измени местоположение")

        await call.message.answer(
            "Ок, давай ещё раз укажем место.\n\n"
            "▫️ Отправь геолокацию кнопкой ниже\n"
            "▫️ Или напиши адрес / район текстом\n"
            "▫️ Или нажми «Пропустить».",
            reply_markup=location_reply_kb(),
        )
        await state.set_state(RequestCreate.waiting_location)

    # ---------- Шаг 3: описание + подтверждение ----------

    @dp.message(RequestCreate.waiting_description)
    async def req_description(message: Message, state: FSMContext):
        description = message.text.strip()
        await state.update_data(description=description)

        await message.answer(
            "Ты описал(а) проблему так:\n\n"
            f"«{description}»\n\n"
            "Всё верно?",
            reply_markup=description_confirm_kb(),
        )
        await state.set_state(RequestCreate.waiting_description_confirm)

    @dp.callback_query(RequestCreate.waiting_description_confirm, F.data == "req_desc_ok")
    async def req_description_ok(call: CallbackQuery, state: FSMContext):
        await call.answer("Описание подтверждено")

        await call.message.answer(
            "Шаг 4.\n\n"
            "Прикрепи одно фото, если есть:\n"
            "повреждения, приборка, ошибка на панели и т.п.\n\n"
            "▫️ Отправь фото одним сообщением\n"
            "▫️ Или нажми «Пропустить»",
            reply_markup=photo_reply_kb(),
        )
        await state.set_state(RequestCreate.waiting_photo_choice)

    @dp.callback_query(RequestCreate.waiting_description_confirm, F.data == "req_desc_edit")
    async def req_description_edit(call: CallbackQuery, state: FSMContext):
        await call.answer("Измени описание")

        await call.message.answer(
            "Ок, опиши проблему ещё раз.\n"
            "Можно коротко: как проявляется, при каких условиях.",
        )
        await state.set_state(RequestCreate.waiting_description)

    # ---------- Шаг 4: фото (опционально) ----------

    @dp.message(RequestCreate.waiting_photo_choice)
    async def req_photo(message: Message, state: FSMContext):
        """
        Принимаем:
        - message.photo (одно фото)
        - текст «Пропустить»
        - текст «Отменить заявку» — обрабатывается отдельным хендлером
        - текст «Отправить фото» — просто подсказка, ждём реальное фото
        """
        text = (message.text or "").strip().lower() if message.text else ""

        if text == "пропустить":
            await state.update_data(photo_file_id=None)
            await message.answer("Окей, идём дальше без фото.", reply_markup=ReplyKeyboardRemove())

            await message.answer(
                "Шаг 5.\n\n"
                "На какую дату удобно записаться?\n"
                "Можно написать в свободной форме:\n"
                "«сегодня вечером», «5 декабря», "
                "«любой будний день после обеда» и т.п.",
            )
            await state.set_state(RequestCreate.waiting_date)
            return

        if text.startswith("📷 отправить фото".lower()) or "отправить фото" in text:
            await message.answer(
                "Прикрепи, пожалуйста, одно фото автомобиля одним сообщением 📷\n"
                "После этого продолжим."
            )
            return

        if message.photo:
            file_id = message.photo[-1].file_id
            await state.update_data(photo_file_id=file_id)
            await message.answer("Фото прикреплено ✅", reply_markup=ReplyKeyboardRemove())

            await message.answer(
                "Шаг 5.\n\n"
                "На какую дату удобно записаться?\n"
                "Можно написать в свободной форме:\n"
                "«сегодня вечером», «5 декабря», "
                "«любой будний день после обеда» и т.п.",
            )
            await state.set_state(RequestCreate.waiting_date)
            return

        await message.answer(
            "Пожалуйста, отправь одно фото автомобиля как медиа-сообщение "
            "или нажми «Пропустить».\n"
            "Если передумал(а) — напиши «Отменить заявку».",
        )

    # ---------- Шаг 5: дата + подтверждение ----------

    @dp.message(RequestCreate.waiting_date)
    async def req_date(message: Message, state: FSMContext):
        date_text = message.text.strip()
        await state.update_data(date_text=date_text)

        await message.answer(
            "Ты указал(а) дату так:\n\n"
            f"«{date_text}»\n\n"
            "Всё верно?",
            reply_markup=date_confirm_kb(),
        )
        await state.set_state(RequestCreate.waiting_date_confirm)

    @dp.callback_query(RequestCreate.waiting_date_confirm, F.data == "req_date_ok")
    async def req_date_ok(call: CallbackQuery, state: FSMContext):
        await call.answer("Дата подтверждена")

        await call.message.answer(
            "Шаг 6.\n\n"
            "Выбери удобный диапазон времени:",
            reply_markup=request_time_slot_kb(),
        )
        await state.set_state(RequestCreate.waiting_time_slot)

    @dp.callback_query(RequestCreate.waiting_date_confirm, F.data == "req_date_edit")
    async def req_date_edit(call: CallbackQuery, state: FSMContext):
        await call.answer("Измени дату")

        await call.message.answer(
            "Ок, напиши удобную дату ещё раз.\n"
            "Можно свободным текстом.",
        )
        await state.set_state(RequestCreate.waiting_date)

    # ---------- Шаг 6: диапазон времени ----------

    @dp.callback_query(RequestCreate.waiting_time_slot)
    async def req_time_slot(call: CallbackQuery, state: FSMContext):
        mapping = {
            "req_slot_morning": "До 12:00",
            "req_slot_day": "12:00–18:00",
            "req_slot_evening": "После 18:00",
        }

        if call.data not in mapping:
            await call.answer()
            return

        slot_title = mapping[call.data]
        await state.update_data(time_slot=slot_title)

        data = await state.get_data()
        move_type = data.get("move_type")
        move_text = (
            "Едет самостоятельно"
            if move_type == "self"
            else "Нужна эвакуация / выездной мастер"
        )

        loc_text = data.get("loc_text") or "Не указано"
        description = data.get("description") or "Не указано"
        date_text = data.get("date_text") or "Не указано"
        photo_id = data.get("photo_file_id")
        photo_text = "прикреплено" if photo_id else "нет"

        summary = (
            "Проверь, пожалуйста, заявку:\n\n"
            f"📍 Местоположение: {loc_text}\n"
            f"🚗 Состояние авто: {move_text}\n"
            f"🔧 Описание: {description}\n"
            f"📅 Дата: {date_text}\n"
            f"⏰ Время: {slot_title}\n"
            f"📷 Фото: {photo_text}\n\n"
            "Далее выберем автомобиль из гаража (если он есть).\n"
        )

        # показываем резюме без кнопок
        await call.message.answer(summary)

        # Получаем пользователя, чтобы узнать его машины
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]
        except Exception as e:
            logger.exception("Ошибка при получении пользователя на шаге выбора авто: %s", e)
            # Фолбэк: идём сразу к финальному подтверждению без авто
            await call.message.answer(
                "Не получилось получить список автомобилей 😔\n"
                "Заявка будет сохранена без привязки к машине.",
                reply_markup=final_confirm_kb(),
            )
            await state.set_state(RequestCreate.waiting_confirm)
            await call.answer()
            return

        # Пытаемся получить список машин
        try:
            cars = await api.list_cars(user_id=user_id)
        except Exception as e:
            logger.exception("Ошибка при получении списка машин: %s", e)
            cars = []

        if cars:
            await call.message.answer(
                "Теперь выбери автомобиль из своего гаража для этой заявки:",
                reply_markup=car_select_kb(cars),
            )
            await state.set_state(RequestCreate.waiting_car_select)
        else:
            await call.message.answer(
                "У тебя пока нет сохранённых автомобилей.\n"
                "Заявка будет сохранена без привязки к машине.\n"
                "Позже ты сможешь добавить авто в разделе «Мой гараж».",
                reply_markup=final_confirm_kb(),
            )
            await state.set_state(RequestCreate.waiting_confirm)

        await call.answer()
    
        # ---------- Шаг 7: выбор автомобиля из гаража ----------

    @dp.callback_query(RequestCreate.waiting_car_select)
    async def req_car_select(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        cb_data = call.data or ""

        if cb_data == "req_car_skip":
            # Пользователь решил не привязывать авто
            await state.update_data(car_id=None)
            car_text = "без привязки к конкретному авто"
        elif cb_data.startswith("req_car_"):
            try:
                car_id = int(cb_data.split("_")[-1])
            except ValueError:
                await call.answer()
                return
            await state.update_data(car_id=car_id)
            car_text = f"автомобиль #{car_id}"
        else:
            await call.answer()
            return

        # Показываем финальный шаг подтверждения
        await call.message.edit_text(
            "Автомобиль для заявки выбран: "
            f"{car_text}.\n\n"
            "Если всё верно — подтверди заявку:",
            reply_markup=final_confirm_kb(),
        )
        await state.set_state(RequestCreate.waiting_confirm)
        await call.answer()

        # ---------- Финальное подтверждение ----------

    @dp.callback_query(RequestCreate.waiting_confirm, F.data == "req_confirm_yes")
    async def req_confirm_yes(call: CallbackQuery, state: FSMContext):
        tg_id = call.from_user.id

        data = await state.get_data()
        logger.info("Подтверждение заявки, tg_id=%s, data=%s", tg_id, data)

        # 1. Пытаемся получить пользователя по telegram_id
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception as e:
            logger.exception("Ошибка при получении пользователя tg_id=%s: %s", tg_id, e)
            await call.answer(
                "Не получилось найти профиль пользователя 😔\n"
                "Попробуй ещё раз через /start.",
                show_alert=True,
            )
            return

        user_id = user["id"]

        # 2. Разбираем данные из FSM
        move_type = data.get("move_type")  # "self" или "help"
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        address = data.get("address")
        description = (data.get("description") or "").strip()
        date_text = (data.get("date_text") or "").strip()
        time_slot = (data.get("time_slot") or "").strip()
        photo_id = data.get("photo_file_id")
        car_id = data.get("car_id")  # может быть None

        # Добавим дату/время к описанию, чтобы информация не потерялась
        extra_parts = []
        if date_text:
            extra_parts.append(f"Дата/когда удобно: {date_text}")
        if time_slot:
            extra_parts.append(f"Предпочитаемое время: {time_slot}")

        if extra_parts:
            if description:
                description_full = description + "\n\n" + "\n".join(extra_parts)
            else:
                description_full = "\n".join(extra_parts)
        else:
            description_full = description or "Описание не указано"

        # 3. Маппинг состояния авто в поля схемы
        is_car_movable = move_type == "self"
        need_tow_truck = move_type == "help"
        need_mobile_master = move_type == "help"

        # 4. Формируем payload под RequestCreate
        request_payload = {
            "user_id": user_id,
            "car_id": car_id,  # 🔥 теперь берём из FSM

            "latitude": latitude,
            "longitude": longitude,
            "address_text": address,

            "is_car_movable": is_car_movable,
            "need_tow_truck": need_tow_truck,
            "need_mobile_master": need_mobile_master,

            "radius_km": None,          # TODO: выбор радиуса / района
            "service_category": None,   # TODO: выбор типа услуги

            "description": description_full,
            "photos": [photo_id] if photo_id else [],

            "hide_phone": True,         # TODO: отдельный шаг "Показывать номер?"
        }

        logger.info("Отправляем заявку в backend: %s", request_payload)

        # 5. Пытаемся создать заявку в backend-е
        try:
            created = await api.create_request(request_payload)
        except Exception as e:
            logger.exception("Ошибка при создании заявки в backend: %s", e)
            await state.clear()
            await call.message.edit_text(
                "Не получилось сохранить заявку на сервере 😔\n"
                "Попробуй ещё раз чуть позже.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        # 6. Очищаем состояние и показываем результат
        await state.clear()

        request_id = created.get("id")
        request_id_text = f"#{request_id}" if request_id is not None else "без номера"

        await call.message.edit_text(
            "Заявка сохранена в системе ✅\n\n"
            "Мы зафиксировали все данные и скоро добавим:\n"
            "подбор подходящих СТО, отклики и бонусы.\n\n"
            f"Номер твоей заявки: {request_id_text}\n\n"
            "Можешь вернуться в главное меню:",
            reply_markup=main_menu_inline(),
        )
        await call.answer("Заявка отправлена")

        # 5. Пытаемся создать заявку в backend-е
        try:
            created = await api.create_request(request_payload)
        except Exception as e:
            logger.exception("Ошибка при создании заявки в backend: %s", e)
            await state.clear()
            await call.message.edit_text(
                "Не получилось сохранить заявку на сервере 😔\n"
                "Попробуй ещё раз чуть позже.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        # 6. Очищаем состояние и показываем результат
        await state.clear()

        request_id = created.get("id")
        request_id_text = f"#{request_id}" if request_id is not None else "без номера"

        await call.message.edit_text(
            "Заявка сохранена в системе ✅\n\n"
            "Мы зафиксировали все данные и скоро добавим:\n"
            "подбор подходящих СТО, отклики и бонусы.\n\n"
            f"Номер твоей заявки: {request_id_text}\n\n"
            "Можешь вернуться в главное меню:",
            reply_markup=main_menu_inline(),
        )
        await call.answer("Заявка отправлена")

    # ==========================
    #   СТО: смена роли
    # ==========================

    @dp.callback_query(F.data == "menu_service")
    async def cb_service(call: CallbackQuery):
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            await api.update_user(user["id"], {"role": "service_owner"})
        except Exception as e:
            logger.exception("Ошибка при смене роли: %s", e)
            await call.message.answer(
                "Не удалось обновить роль до «автосервис» 😔\n"
                "Попробуй позже или напиши /profile для проверки.",
                reply_markup=main_menu_inline(),
            )
            await call.answer()
            return

        await call.message.edit_text(
            "Отлично! 🎯\n"
            "Теперь ты отмечен как представитель автосервиса.\n"
            "Скоро добавим регистрацию СТО, адрес, услуги и приём заявок.",
            reply_markup=main_menu_inline(),
        )
        await call.answer()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
