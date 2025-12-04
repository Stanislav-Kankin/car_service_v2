from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.api_client import api_client
from .general import get_main_menu

router = Router()


@router.message(F.text, F.text.as_("text"))
async def registration_flow(message: Message, state: FSMContext, text: str):
    data = await state.get_data()

    if "reg_step" not in data:
        return

    step = data["reg_step"]

    if step == "name":
        await state.update_data(name=text)
        await state.update_data(reg_step="phone")
        await message.answer("Введите номер телефона:")
        return

    if step == "phone":
        await state.update_data(phone=text)
        await state.update_data(reg_step="city")
        await message.answer("Введите ваш город:")
        return

    if step == "city":
        data = await state.get_data()

        payload = {
            "telegram_id": message.from_user.id,
            "full_name": data["name"],
            "phone": data["phone"],
            "city": text,
        }

        await api_client.create_user(payload)

        await message.answer(
            "Регистрация успешно завершена! 🎉",
            reply_markup=get_main_menu(),
        )
        await state.clear()
        return
