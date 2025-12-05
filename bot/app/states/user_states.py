from aiogram.fsm.state import StatesGroup, State


class UserRegistration(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_city = State()


class CarCreate(StatesGroup):
    choosing_brand = State()
    choosing_model = State()
    choosing_year = State()
    choosing_license_plate = State()
    choosing_vin = State()
