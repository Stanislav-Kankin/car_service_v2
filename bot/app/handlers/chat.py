import re
from typing import Any

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from ..api_client import api_client
from ..states.chat_states import ChatRelay

router = Router()

_CHAT_RE = re.compile(r"^chat_r(?P<rid>\d+)_s(?P<scid>\d+)$")


def _build_open_chat_kb(bot_username: str, request_id: int, service_center_id: int) -> InlineKeyboardMarkup:
    url = f"https://t.me/{bot_username}?start=chat_r{request_id}_s{service_center_id}"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💬 Открыть чат по заявке", url=url)]]
    )


@router.message(CommandStart(deep_link=True))
async def start_deeplink(message: Message, state: FSMContext, bot: Bot, command: CommandObject):
    """
    Deep-link формат:
      /start chat_r<request_id>_s<service_center_id>

    Открывает “чат через бота” между:
    - клиентом заявки
    - владельцем выбранного СТО

    Бот НЕ раскрывает телефон и НЕ даёт прямые контакты — только пересылка сообщений.
    """
    payload = (command.args or "").strip()
    m = _CHAT_RE.match(payload)
    if not m:
        return  # не наш payload — пусть обработают другие /start (или ничего)

    request_id = int(m.group("rid"))
    sc_id = int(m.group("scid"))

    # 1) Загружаем заявку
    try:
        req: dict[str, Any] = await api_client.get_request(request_id)
    except Exception:
        await message.answer("Не удалось открыть чат: заявка не найдена или сервер недоступен.")
        return

    user_id = req.get("user_id")
    if not user_id:
        await message.answer("Не удалось открыть чат: в заявке нет владельца (user_id).")
        return

    # 2) Загружаем клиента заявки
    try:
        client_user: dict[str, Any] = await api_client.get_user(int(user_id))
    except Exception:
        await message.answer("Не удалось открыть чат: не удалось загрузить клиента заявки.")
        return

    client_tid = client_user.get("telegram_id")

    # 3) Загружаем СТО и владельца СТО
    try:
        sc: dict[str, Any] = await api_client.get_service_center(sc_id)
    except Exception:
        await message.answer("Не удалось открыть чат: не удалось загрузить СТО.")
        return

    sc_owner_id = sc.get("user_id")
    if not sc_owner_id:
        await message.answer("Не удалось открыть чат: у СТО нет владельца (user_id).")
        return

    try:
        sc_owner_user: dict[str, Any] = await api_client.get_user(int(sc_owner_id))
    except Exception:
        await message.answer("Не удалось открыть чат: не удалось загрузить владельца СТО.")
        return

    sc_owner_tid = sc_owner_user.get("telegram_id")

    me_tid = message.from_user.id if message.from_user else None
    if not me_tid:
        await message.answer("Не удалось открыть чат: не определён telegram_id.")
        return

    # 4) Проверка: открывать чат может только клиент заявки или владелец СТО
    if me_tid == client_tid:
        my_role = "client"
        peer_tid = sc_owner_tid
        peer_label = "СТО"
    elif me_tid == sc_owner_tid:
        my_role = "service"
        peer_tid = client_tid
        peer_label = "клиента"
    else:
        await message.answer("Доступ запрещён: этот чат не для вашего аккаунта.")
        return

    if not peer_tid:
        await message.answer("Не удалось открыть чат: у второй стороны нет telegram_id.")
        return

    # 5) Сохраняем контекст чата
    await state.set_state(ChatRelay.active)
    await state.update_data(
        request_id=request_id,
        service_center_id=sc_id,
        client_tid=client_tid,
        sc_owner_tid=sc_owner_tid,
        my_role=my_role,
    )

    bot_username = (await bot.get_me()).username or ""
    kb = _build_open_chat_kb(bot_username, request_id, sc_id) if bot_username else None

    await message.answer(
        f"Чат по заявке №{request_id} открыт.\n\n"
        f"Пиши сюда — я передам сообщение {peer_label}.\n"
        f"Команда: /close — закрыть чат.",
        reply_markup=kb,
    )


@router.message(ChatRelay.active, F.text == "/close")
async def close_chat(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Чат закрыт. Чтобы открыть снова — нажми кнопку в WebApp.")


@router.message(ChatRelay.active, F.text)
async def relay_text(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    request_id = int(data.get("request_id") or 0)
    sc_id = int(data.get("service_center_id") or 0)
    client_tid = data.get("client_tid")
    sc_owner_tid = data.get("sc_owner_tid")
    my_role = data.get("my_role")

    if not request_id or not sc_id or not client_tid or not sc_owner_tid:
        await state.clear()
        await message.answer("Чат сброшен: не хватает данных. Открой чат заново из WebApp.")
        return

    if my_role == "client":
        peer_tid = sc_owner_tid
        sender_label = "Клиент"
    else:
        peer_tid = client_tid
        sender_label = "СТО"

    text = message.text or ""
    bot_username = (await bot.get_me()).username or ""
    kb = _build_open_chat_kb(bot_username, request_id, sc_id) if bot_username else None

    try:
        await bot.send_message(
            chat_id=int(peer_tid),
            text=f"💬 {sender_label} по заявке №{request_id}:\n{text}",
            reply_markup=kb,
        )
    except Exception:
        await message.answer(
            "Не удалось доставить сообщение второй стороне. "
            "Возможно, пользователь ещё не нажимал /start у бота или заблокировал бота."
        )
        return

    await message.answer("✅ Отправлено")
