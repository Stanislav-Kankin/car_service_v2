from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from ..api_client import api_client

router = Router()


@router.message(F.text == "📨 Мои заявки")
async def my_requests(message: Message):
    user = await api_client.get_user_by_telegram(message.chat.id)
    if not user:
        return await message.answer("Вы не зарегистрированы. Нажмите /start.")

    requests = await api_client.list_requests_by_user(user["id"])

    if not requests:
        return await message.answer("У вас пока нет заявок.")

    for req in requests:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📩 Отклики СТО",
                        callback_data=f"req_offers_{req['id']}",
                    )
                ]
            ]
        )
        text = (
            f"Заявка #{req['id']}\n"
            f"Статус: {req['status']}\n"
            f"Описание: {req['description']}\n"
        )
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "main:my_requests")
async def my_requests_from_menu(callback: CallbackQuery):
    """
    Вход в список заявок из главного инлайн-меню.
    """
    await my_requests(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("req_offers_"))
async def show_offers(call, state):
    req_id = int(call.data.split("_")[2])

    offers = await api_client.list_offers_by_request(req_id)

    if not offers:
        await call.answer()
        return await call.message.edit_text(
            "Пока нет предложений от СТО."
        )

    buttons = []
    text = "📨 Отклики СТО:\n\n"

    for offer in offers:
        sc = await api_client.get_service_center(offer["service_center_id"])
        text += (
            f"СТО: {sc['name']}\n"
            f"Цена: {offer['price']} ₽\n"
            f"Срок: {offer['term']}\n"
            f"Комментарий: {offer['comment']}\n\n"
        )

        buttons.append([
            InlineKeyboardButton(
                text=f"Выбрать {sc['name']}",
                callback_data=f"offer_accept_{offer['id']}_{req_id}_{sc['id']}",
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await call.answer()
    await call.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("offer_accept_"))
async def accept_offer(call, state):
    _, _, offer_id, req_id, sc_id = call.data.split("_")

    req_id = int(req_id)
    sc_id = int(sc_id)

    # Обновляем заявку
    await api_client.update_request(
        req_id,
        {
            "service_center_id": sc_id,
            "status": "accepted_by_service",
        }
    )

    # Уведомляем СТО
    sc = await api_client.get_service_center(sc_id)
    manager_tg = sc.get("telegram_id")

    if manager_tg:
        try:
            await call.bot.send_message(
                manager_tg,
                "🎉 Клиент выбрал ваше предложение!",
            )
        except:
            pass

    await call.answer()
    await call.message.edit_text(
        "Вы выбрали сервис! Менеджер скоро с вами свяжется."
    )
