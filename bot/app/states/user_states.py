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


class RequestCreateFSM(StatesGroup):
    choosing_location = State()
    choosing_car_movable = State()
    choosing_radius = State()
    choosing_category = State()
    choosing_description = State()
    choosing_photos = State()
    choosing_hide_phone = State()

    # НОВОЕ:
    choosing_day = State()
    choosing_time_range = State()

    confirm = State()


class CarEdit(StatesGroup):
    waiting_for_field = State()
    waiting_for_value = State()
    confirm_delete = State()


class STOEdit(StatesGroup):
    """
    FSM для редактирования профиля СТО.
    """
    choosing_field = State()
    waiting_value = State()
    waiting_geo = State()
    choosing_specs = State()
