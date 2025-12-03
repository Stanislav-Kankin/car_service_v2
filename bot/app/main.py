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
    waiting_photo_choice = State()   # НОВОЕ: шаг с фото
    waiting_date = State()
    waiting_date_confirm = State()
    waiting_time_slot = State()
    waiting_confirm = State()


# ==========================
#   Inline / Reply клавиатуры
# ==========================

def main_menu_inline() -> InlineKeyboardMarkup:
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
                InlineKeyboardButton(text="🏭 Я представляю автосервис", callback_data="menu_service"),
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

    # ==========================
    #   ГАРАЖ (заглушка)
    # ==========================

    @dp.callback_query(F.data == "menu_garage")
    async def cb_garage(call: CallbackQuery):
        await call.message.edit_text(
            "🚗 Раздел «Гараж» скоро появится.\n\n"
            "Ты сможешь сохранить свои автомобили, чтобы не вводить данные каждый раз.",
            reply_markup=main_menu_inline(),
        )
        await call.answer()

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
            "Если всё верно — подтверждай.\n"
            "Позже привяжем это к подбору СТО и системе бонусов."
        )

        await call.message.answer(summary, reply_markup=final_confirm_kb())
        await state.set_state(RequestCreate.waiting_confirm)
        await call.answer()

    # ---------- Финальное подтверждение ----------

    @dp.callback_query(RequestCreate.waiting_confirm, F.data == "req_confirm_yes")
    async def req_confirm_yes(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        logger.info("Черновик заявки (пока без сохранения в БД): %s", data)

        await state.clear()

        await call.message.edit_text(
            "Заявка сохранена как черновик внутри бота ✅\n\n"
            "На следующем шаге мы привяжем её к backend'у, "
            "подбору СТО и бонусам.\n\n"
            "Пока можешь вернуться в меню:",
            reply_markup=main_menu_inline(),
        )
        await call.answer("Заявка подтверждена")

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
