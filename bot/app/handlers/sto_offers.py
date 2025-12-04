from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from app.api_client import api_client

router = Router()


class OfferFSM(StatesGroup):
    waiting_price = State()
    waiting_term = State()
    waiting_comment = State()


# Хэндлер на кнопку "💰 Сделать предложение"
@router.callback_query(F.data.startswith("offer_make_"))
async def offer_make_start(call: CallbackQuery, state: FSMContext):
    _, _, request_id, sc_id = call.data.split("_")

    await call.answer()

    await state.update_data(
        request_id=int(request_id),
        service_center_id=int(sc_id),
    )

    await call.message.answer(
        "Введите цену (в рублях):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(OfferFSM.waiting_price)


@router.message(OfferFSM.waiting_price)
async def offer_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
    except ValueError:
        await message.answer("Введите число, например: 4500")
        return

    await state.update_data(price=price)

    await message.answer("Введите срок выполнения (например: «1 день»):")
    await state.set_state(OfferFSM.waiting_term)


@router.message(OfferFSM.waiting_term)
async def offer_term(message: Message, state: FSMContext):
    await state.update_data(term=message.text.strip())

    await message.answer("Оставьте комментарий (или '-' если без комментария):")
    await state.set_state(OfferFSM.waiting_comment)


@router.message(OfferFSM.waiting_comment)
async def offer_comment(message: Message, state: FSMContext):
    data = await state.get_data()

    payload = {
        "request_id": data["request_id"],
        "service_center_id": data["service_center_id"],
        "price": data["price"],
        "term": data["term"],
        "comment": message.text.strip(),
    }

    offer = await api_client.create_offer(payload)

    await message.answer(
        "Предложение отправлено клиенту! 🎉\n"
        "Когда он выберет сервис — вы получите уведомление.",
        reply_markup=ReplyKeyboardRemove(),
    )

    await state.clear()
