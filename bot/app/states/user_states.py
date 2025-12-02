from aiogram.fsm.state import StatesGroup, State


class UserRegistration(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_city = State()
