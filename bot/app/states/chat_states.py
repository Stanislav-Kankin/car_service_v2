from aiogram.fsm.state import StatesGroup, State


class ChatRelay(StatesGroup):
    """Состояние пересылки сообщений между клиентом и СТО по заявке."""
    active = State()
