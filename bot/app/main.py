import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import CommandStart, Command

from .config import config
from .api_client import APIClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- FSM регистрации ----------

class UserRegistration(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_city = State()


# ---------- Inline клавиатуры ----------

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


async def main() -> None:
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    api = APIClient()

    # ---------- /start ----------

    @dp.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        logger.info("--- /start от %s", tg_id)

        # пробуем найти пользователя
        user = None
        try:
            user = await api.get_user_by_telegram(tg_id)
        except Exception:
            pass

        # если профиль есть → показываем меню
        if user and (user.get("full_name") or user.get("phone") or user.get("city")):
            name = user.get("full_name") or "друг"
            await message.answer(
                f"С возвращением, {name}! 🚗\nВыберите действие:",
                reply_markup=main_menu_inline(),
            )
            return

        # если нет — создаём черновик
        if not user:
            try:
                user = await api.create_user(tg_id)
            except Exception as e:
                logger.exception(e)
                await message.answer("Ошибка при создании профиля 😔")
                return

        # запускаем регистрацию
        await message.answer("Как к тебе обращаются?")
        await state.set_state(UserRegistration.waiting_full_name)

    # ---------- Регистрация: имя ----------

    @dp.message(UserRegistration.waiting_full_name)
    async def reg_full_name(message: Message, state: FSMContext):
        await state.update_data(full_name=message.text.strip())
        await message.answer("Отправь номер телефона:")
        await state.set_state(UserRegistration.waiting_phone)

    # ---------- Регистрация: телефон ----------

    @dp.message(UserRegistration.waiting_phone)
    async def reg_phone(message: Message, state: FSMContext):
        await state.update_data(phone=message.text.strip())
        await message.answer("Из какого ты города?")
        await state.set_state(UserRegistration.waiting_city)

    # ---------- Регистрация: город + сохранение ----------

    @dp.message(UserRegistration.waiting_city)
    async def reg_city(message: Message, state: FSMContext):
        data = await state.get_data()
        tg_id = message.from_user.id

        try:
            user = await api.get_user_by_telegram(tg_id)
            user_id = user["id"]

            await api.update_user(
                user_id,
                {
                    "full_name": data["full_name"],
                    "phone": data["phone"],
                    "city": message.text.strip(),
                    "role": "client",
                },
            )
        except Exception as e:
            logger.exception(e)
            await message.answer("Ошибка сохранения профиля 😔")
            return

        await state.clear()

        await message.answer(
            "Регистрация завершена! 🎉\n\nВыберите действие:",
            reply_markup=main_menu_inline(),
        )

    # ---------- ПРОФИЛЬ / inline обработчик ----------

    @dp.callback_query(F.data == "menu_profile")
    async def cb_profile(call: CallbackQuery):
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
        except:
            await call.message.answer("Профиль не найден 😔")
            return

        text = (
            "Ваш профиль:\n\n"
            f"Имя: {user.get('full_name')}\n"
            f"Телефон: {user.get('phone')}\n"
            f"Город: {user.get('city')}\n"
            f"Роль: {user.get('role')}\n"
            f"Бонусы: {user.get('bonus_balance', 0)}"
        )

        await call.message.edit_text(text, reply_markup=main_menu_inline())

    # ---------- ГАРАЖ ----------

    @dp.callback_query(F.data == "menu_garage")
    async def cb_garage(call: CallbackQuery):
        await call.message.edit_text(
            "🚗 Раздел «Гараж» скоро появится.\n"
            "Ты сможешь сохранять автомобили и быстро выбирать их при создании заявки.",
            reply_markup=main_menu_inline(),
        )

    # ---------- НОВАЯ ЗАЯВКА ----------

    @dp.callback_query(F.data == "menu_new_request")
    async def cb_new_request(call: CallbackQuery):
        await call.message.edit_text(
            "Создание новой заявки скоро будет доступно!\n\n"
            "По плану заказчика:\n"
            "• геолокация\n"
            "• тип проблемы\n"
            "• фото\n"
            "• выбор времени\n"
            "• подбор ближайших СТО",
            reply_markup=main_menu_inline(),
        )

    # ---------- СТО: смена роли ----------

    @dp.callback_query(F.data == "menu_service")
    async def cb_service(call: CallbackQuery):
        tg_id = call.from_user.id
        try:
            user = await api.get_user_by_telegram(tg_id)
            await api.update_user(user["id"], {"role": "service_owner"})
        except:
            await call.message.answer("Ошибка при смене роли 😔")
            return

        await call.message.edit_text(
            "Теперь ты отмечен как представитель автосервиса 🏭\n"
            "Скоро добавим регистрацию СТО и панель управления!",
            reply_markup=main_menu_inline(),
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
