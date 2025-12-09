from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from ..api_client import api_client
from .general import get_main_menu

router = Router()

# ---------------------------------------------------------------------------
# Константы статусов (для человека)
# ---------------------------------------------------------------------------

# Статусы заявки — подогнаны под ТЗ:
# new, sent, accepted_by_service, in_work, done, cancelled, rejected_by_service
STATUS_LABELS: Dict[str, str] = {
    "new": "🆕 Новая",
    "sent": "📡 Отправлена СТО",
    "accepted_by_service": "✅ Принята сервисом",
    "in_work": "🛠 В работе",
    "done": "🎉 Выполнена",
    "cancelled": "❌ Отменена",
    "rejected_by_service": "🚫 Отклонена сервисом",
}

# Статусы отклика — значения могут отличаться,
# НО в backend у тебя Enum OfferStatus, там всё видно.
# Если что-то не совпадёт, достаточно поправить значения здесь.
OFFER_STATUS_LABELS: Dict[str, str] = {
    "new": "🆕 Новый",
    "accepted": "✅ Выбран клиентом",
    "rejected": "🚫 Отклонён",
}


# Какие строковые значения мы шлём в backend при выборе отклика
# (если в OfferStatus другие значения — поменяй эти строки).
OFFER_ACCEPT_STATUS = "accepted"          # OfferStatus.ACCEPTED.value
REQUEST_ACCEPT_STATUS = "accepted_by_service"  # RequestStatus.ACCEPTED_BY_SERVICE.value


def _format_request_number(request_id: int | None) -> str:
    """
    Форматируем номер заявки как четырёхзначный: 0001, 0002, ...
    """
    if not request_id:
        return "—"
    try:
        return f"{int(request_id):04d}"
    except Exception:
        return str(request_id)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _status_to_text(status: Optional[str]) -> str:
    if not status:
        return "Неизвестен"
    return STATUS_LABELS.get(status, status)


def _offer_status_to_text(status: Optional[str]) -> str:
    if not status:
        return "Неизвестен"
    return OFFER_STATUS_LABELS.get(status, status)


async def _back_to_main_menu(message: Message, telegram_id: int):
    user = await api_client.get_user_by_telegram(telegram_id)
    role: Optional[str] = None
    if isinstance(user, dict):
        role = user.get("role")

    await message.answer(
        "Выберите действие из меню ниже 👇",
        reply_markup=get_main_menu(role),
    )


async def _get_current_user(message_or_cb) -> Optional[Dict[str, Any]]:
    """
    Общий helper: найти пользователя по telegram_id.
    Если не найден — показываем подсказку про /start.
    """
    if isinstance(message_or_cb, Message):
        tg_id = message_or_cb.from_user.id
        message = message_or_cb
    else:
        tg_id = message_or_cb.from_user.id
        message = message_or_cb.message

    user = await api_client.get_user_by_telegram(tg_id)
    if not user:
        await message.answer(
            "Похоже, вы ещё не зарегистрированы.\n"
            "Нажмите /start, чтобы пройти короткую регистрацию.",
        )
        return None
    return user


def _build_requests_list_kb(requests: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    if requests:
        for req in requests:
            req_id = req.get("id")
            status = _status_to_text(req.get("status"))
            text = f"#{_format_request_number(req_id)} — {status}"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=text,
                        callback_data=f"req_view:{req_id}",
                    )
                ]
            )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ В меню",
                callback_data="main:menu",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_request_detail_kb(request_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура под карточкой заявки.
    Кнопка «📨 Отклики по заявке» всегда есть — если откликов нет, мы честно скажем.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📨 Отклики по заявке",
                    callback_data=f"req_offers:list:{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку заявок",
                    callback_data="req_list:back",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="main:menu",
                )
            ],
        ]
    )


def _build_offers_list_kb(request_id: int, offers: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    if offers:
        for off in offers:
            offer_id = off.get("id")
            status = _offer_status_to_text(off.get("status"))
            # название СТО мы покажем в тексте, в кнопке оставим коротко
            text = f"Отклик #{offer_id} — {status}"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=text,
                        callback_data=f"req_offer:view:{request_id}:{offer_id}",
                    )
                ]
            )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ К заявке",
                callback_data=f"req_view:{request_id}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ В меню",
                callback_data="main:menu",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_offer_detail_kb(
    request_id: int,
    offer_id: int,
    service_center_id: int,
) -> InlineKeyboardMarkup:
    """
    Кнопки под конкретным откликом:
    - выбрать сервис
    - назад к списку откликов
    - в меню
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Выбрать этот сервис",
                    callback_data=f"req_offer:choose:{request_id}:{offer_id}:{service_center_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К откликам",
                    callback_data=f"req_offers:list:{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="main:menu",
                )
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Список заявок
# ---------------------------------------------------------------------------


async def _send_requests_list(message: Message, user_id: int):
    try:
        requests = await api_client.list_requests_by_user(user_id)
    except Exception:
        await message.answer(
            "Не удалось загрузить список заявок. Попробуйте позже."
        )
        return

    if not requests:
        await message.answer(
            "<b>📨 Мои заявки</b>\n\n"
            "У вас пока нет заявок.\n"
            "Создайте первую через меню «📝 Новая заявка».",
            reply_markup=_build_requests_list_kb([]),
        )
        return

    lines: List[str] = ["<b>📨 Мои заявки</b>", ""]
    for req in requests:
        req_id = req.get("id")
        status = _status_to_text(req.get("status"))
        desc = (req.get("description") or "").strip()
        if len(desc) > 60:
            desc = desc[:57] + "..."

        lines.append(f"#{req_id} — {status}")
        if desc:
            lines.append(f"  {desc}")
        lines.append("")

    text = "\n".join(lines)

    await message.answer(
        text,
        reply_markup=_build_requests_list_kb(requests),
    )


@router.message(F.text == "📨 Мои заявки")
async def my_requests_legacy(message: Message):
    """
    Вход по старой текстовой кнопке.
    """
    user = await _get_current_user(message)
    if not user:
        return

    user_id = user["id"] if isinstance(user, dict) else getattr(user, "id", None)
    if not user_id:
        await message.answer("Не удалось определить пользователя. Попробуйте позже.")
        return

    await _send_requests_list(message, user_id)


@router.callback_query(F.data.in_(("main:my_requests", "main:requests")))
async def my_requests_from_menu(callback: CallbackQuery):
    """
    Вход из главного меню по callback.
    """
    user = await _get_current_user(callback)
    if not user:
        await callback.answer()
        return

    user_id = user["id"] if isinstance(user, dict) else getattr(user, "id", None)
    if not user_id:
        await callback.message.answer(
            "Не удалось определить пользователя. Попробуйте позже."
        )
        await callback.answer()
        return

    await _send_requests_list(callback.message, user_id)
    await callback.answer()


@router.callback_query(F.data == "req_list:back")
async def back_to_requests_list(callback: CallbackQuery):
    """
    Кнопка «⬅️ К списку заявок» из карточки заявки.
    """
    user = await _get_current_user(callback)
    if not user:
        await callback.answer()
        return

    user_id = user["id"] if isinstance(user, dict) else getattr(user, "id", None)
    if not user_id:
        await callback.message.answer(
            "Не удалось определить пользователя. Попробуйте позже."
        )
        await callback.answer()
        return

    await _send_requests_list(callback.message, user_id)
    await callback.answer()


# ---------------------------------------------------------------------------
# Детальная карточка заявки
# ---------------------------------------------------------------------------


async def _load_request_detail(request_id: int) -> Optional[Dict[str, Any]]:
    try:
        return await api_client.get_request(request_id)
    except Exception:
        return None


@router.callback_query(F.data.startswith("req_view:"))
async def request_detail(callback: CallbackQuery):
    """
    Показ карточки заявки.
    """
    payload = callback.data.split(":", maxsplit=1)[1]
    try:
        request_id = int(payload)
    except ValueError:
        await callback.answer("Некорректный идентификатор заявки.")
        return

    request = await _load_request_detail(request_id)
    if not request:
        await callback.message.edit_text(
            "Не удалось загрузить заявку. Возможно, она была удалена.",
            reply_markup=_build_request_detail_kb(request_id),
        )
        await callback.answer()
        return

    status = _status_to_text(request.get("status"))
    desc = request.get("description") or "—"
    category = request.get("service_category") or "—"
    radius = request.get("radius_km")
    radius_text = f"{radius} км" if radius else "—"

    car_info = "—"
    car = request.get("car")
    if isinstance(car, dict):
        brand = car.get("brand") or ""
        model = car.get("model") or ""
        year = car.get("year")
        parts = [brand, model]
        title = " ".join(p for p in parts if p).strip()
        if year:
            car_info = f"{title}, {year}"
        else:
            car_info = title or "—"

    location_text = "—"
    addr = request.get("address_text")
    lat = request.get("latitude")
    lon = request.get("longitude")
    if addr:
        location_text = addr
    elif lat is not None and lon is not None:
        try:
            location_text = f"Координаты: {float(lat):.5f}, {float(lon):.5f}"
        except Exception:
            location_text = f"Координаты: {lat}, {lon}"

    hide_phone = request.get("hide_phone", True)
    hide_phone_text = "Скрыт" if hide_phone else "Показывается СТО"

    text_lines: List[str] = [
        f"<b>Заявка №{_format_request_number(request_id)}</b>",
        "",
        f"<b>Статус:</b> {status}",
        f"<b>Категория:</b> {category}",
        f"<b>Радиус поиска:</b> {radius_text}",
        "",
        f"<b>Машина:</b> {car_info}",
        f"<b>Локация:</b> {location_text}",
        "",
        "<b>Описание проблемы:</b>",
        desc,
        "",
        f"<b>Телефон:</b> {hide_phone_text}",
        "",
        "Ниже можно посмотреть отклики СТО по этой заявке.",
    ]

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=_build_request_detail_kb(request_id),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Отклики по заявке (клиентская часть)
# ---------------------------------------------------------------------------


async def _load_offers_with_sc(
    request_id: int,
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """
    Загружаем все отклики по заявке и справочник СТО по id.
    Возвращаем:
      - список offers,
      - dict service_center_id -> service_center_dict
    """
    try:
        offers = await api_client.list_offers_by_request(request_id)
    except Exception:
        return [], {}

    if not offers:
        return [], {}

    sc_ids = {off.get("service_center_id") for off in offers if off.get("service_center_id")}
    sc_map: Dict[int, Dict[str, Any]] = {}

    for sc_id in sc_ids:
        try:
            sc_data = await api_client.get_service_center(sc_id)  # type: ignore[arg-type]
        except Exception:
            sc_data = None
        if isinstance(sc_data, dict):
            sc_map[sc_id] = sc_data

    return offers, sc_map


@router.callback_query(F.data.startswith("req_offers:list:"))
async def request_offers_list(callback: CallbackQuery):
    """
    Показ списка откликов по конкретной заявке.
    """
    try:
        _, _, raw_id = callback.data.split(":", maxsplit=2)
        request_id = int(raw_id)
    except Exception:
        await callback.answer("Некорректный идентификатор заявки.")
        return

    offers, sc_map = await _load_offers_with_sc(request_id)

    if not offers:
        await callback.message.edit_text(
            "<b>📨 Отклики по заявке</b>\n\n"
            "Пока по этой заявке нет откликов.\n"
            "Как только сервисы ответят — вы увидите их здесь.",
            reply_markup=_build_offers_list_kb(request_id, []),
        )
        await callback.answer()
        return

    lines: List[str] = [
        f"<b>📨 Отклики по заявке №{request_id}</b>",
        "",
    ]

    for off in offers:
        offer_id = off.get("id")
        status = _offer_status_to_text(off.get("status"))
        price = off.get("price")
        eta = off.get("eta_hours")
        comment = (off.get("comment") or "").strip()

        sc_id = off.get("service_center_id")
        sc = sc_map.get(sc_id or -1)
        sc_name = sc.get("name") if isinstance(sc, dict) else None
        sc_name = sc_name or f"СТО #{sc_id}"

        price_text = f"{price:.0f} ₽" if isinstance(price, (int, float)) else "по договорённости"
        if isinstance(eta, int):
            if eta < 24:
                eta_text = f"{eta} ч"
            else:
                days = eta // 24
                eta_text = f"{days} дн."
        else:
            eta_text = "не указан"

        lines.append(f"<b>Отклик #{offer_id}</b> — {status}")
        lines.append(f"Сервис: {sc_name}")
        lines.append(f"Цена: {price_text}")
        lines.append(f"Срок: {eta_text}")
        if comment:
            if len(comment) > 80:
                comment_short = comment[:77] + "..."
            else:
                comment_short = comment
            lines.append(f"Комментарий: {comment_short}")
        lines.append("")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_build_offers_list_kb(request_id, offers),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("req_offer:view:"))
async def request_offer_detail(callback: CallbackQuery):
    """
    Детальный просмотр одного отклика + кнопка «Выбрать этот сервис».
    callback_data: req_offer:view:{request_id}:{offer_id}
    """
    try:
        _, _, raw_req_id, raw_offer_id = callback.data.split(":", maxsplit=3)
        request_id = int(raw_req_id)
        offer_id = int(raw_offer_id)
    except Exception:
        await callback.answer("Некорректные данные отклика.")
        return

    offers, sc_map = await _load_offers_with_sc(request_id)
    offer: Optional[Dict[str, Any]] = next(
        (o for o in offers if o.get("id") == offer_id),
        None,
    )

    if not offer:
        await callback.message.edit_text(
            "Не удалось найти этот отклик. Возможно, он был удалён.",
            reply_markup=_build_offers_list_kb(request_id, offers),
        )
        await callback.answer()
        return

    sc_id = offer.get("service_center_id")
    sc = sc_map.get(sc_id or -1)
    sc_name = sc.get("name") if isinstance(sc, dict) else None
    sc_name = sc_name or f"СТО #{sc_id}"

    status = _offer_status_to_text(offer.get("status"))
    price = offer.get("price")
    eta = offer.get("eta_hours")
    comment = (offer.get("comment") or "").strip()

    price_text = f"{price:.0f} ₽" if isinstance(price, (int, float)) else "по договорённости"
    if isinstance(eta, int):
        if eta < 24:
            eta_text = f"{eta} ч"
        else:
            days = eta // 24
            eta_text = f"{days} дн."
    else:
        eta_text = "не указан"

    text_lines: List[str] = [
        f"<b>Отклик #{offer_id}</b>",
        "",
        f"<b>Сервис:</b> {sc_name}",
        f"<b>Статус:</b> {status}",
        "",
        f"<b>Цена:</b> {price_text}",
        f"<b>Срок:</b> {eta_text}",
        "",
        "<b>Комментарий сервиса:</b>",
        comment or "—",
        "",
        "Если вас всё устраивает — нажмите «✅ Выбрать этот сервис».",
    ]

    kb = _build_offer_detail_kb(
        request_id=request_id,
        offer_id=offer_id,
        service_center_id=sc_id,
    )

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("req_offer:decline:"))
async def request_offer_decline(callback: CallbackQuery):
    """
    Клиент явно отклоняет конкретный отклик.
    callback_data: req_offer:decline:{request_id}:{offer_id}
    """
    try:
        _, _, raw_req_id, raw_offer_id = callback.data.split(":", maxsplit=3)
        request_id = int(raw_req_id)
        offer_id = int(raw_offer_id)
    except Exception:
        await callback.answer("Некорректные данные отклика.")
        return

    # Обновляем статус отклика
    try:
        await api_client.update_offer(
            offer_id,
            {"status": "rejected"},
        )
    except Exception:
        await callback.message.answer(
            "Не удалось отклонить это предложение. Попробуйте позже."
        )
        await callback.answer()
        return

    # Пытаемся уведомить СТО, чьё предложение отклонено
    try:
        offers, sc_map = await _load_offers_with_sc(request_id)
        offer = next((o for o in offers if o.get("id") == offer_id), None)
        if offer:
            sc_id = offer.get("service_center_id")
            sc = sc_map.get(sc_id or -1)
            owner_id = None
            if isinstance(sc, dict):
                owner_id = sc.get("owner_id") or sc.get("user_id")

            if owner_id:
                manager = await api_client.get_user(int(owner_id))
                if isinstance(manager, dict):
                    manager_tg = manager.get("telegram_id")
                    if manager_tg:
                        await callback.bot.send_message(
                            chat_id=manager_tg,
                            text=(
                                f"❌ Клиент отклонил ваше предложение "
                                f"по заявке №{request_id}."
                            ),
                        )
    except Exception:
        # Не мешаем клиентскому UX, если уведомление не удалось
        pass

    # Обновляем сообщение клиенту
    await callback.message.edit_text(
        "❌ Вы отклонили это предложение.\n\n"
        "Вы можете выбрать другой отклик из списка или дождаться новых.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📨 Отклики по заявке",
                        callback_data=f"req_offers:list:{request_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ В меню",
                        callback_data="main:menu",
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("req_offer:choose:"))
async def request_offer_choose(callback: CallbackQuery):
    """
    Клиент выбирает конкретный отклик (выбирает СТО).
    callback_data: req_offer:choose:{request_id}:{offer_id}:{service_center_id}
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    import logging

    try:
        _, _, raw_req_id, raw_offer_id, raw_sc_id = callback.data.split(":", maxsplit=4)
        request_id = int(raw_req_id)
        offer_id = int(raw_offer_id)
        service_center_id = int(raw_sc_id)
    except Exception:
        await callback.answer("Некорректные данные отклика.")
        return

    # 0) Загружаем все отклики по заявке и карту СТО
    try:
        offers = await api_client.list_offers_by_request(request_id)
    except Exception:
        offers = []

    if not isinstance(offers, list):
        offers = []

    # карта: offer_id -> offer
    offers_map: Dict[int, Dict[str, Any]] = {}
    for o in offers:
        try:
            oid = int(o.get("id"))
            offers_map[oid] = o
        except Exception:
            continue

    this_offer = offers_map.get(offer_id)

    # если этот отклик уже принят раньше — просто говорим клиенту
    if this_offer:
        st_raw = str(this_offer.get("status") or "").lower()
        if st_raw == "accepted":
            await callback.message.edit_text(
                "✅ Этот сервис уже выбран по данной заявке.\n\n"
                "При необходимости свяжитесь с сервисом для уточнения деталей.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⬅️ К заявке",
                                callback_data=f"req_view:{request_id}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="⬅️ В меню",
                                callback_data="main:menu",
                            )
                        ],
                    ]
                ),
            )
            await callback.answer()
            return

    # проверяем, нет ли уже другого принятого отклика
    existing_other_accepted = None
    for o in offers:
        try:
            oid = int(o.get("id"))
        except Exception:
            continue

        status_raw = str(o.get("status") or "").lower()
        if oid != offer_id and status_raw == "accepted":
            existing_other_accepted = o
            break

    if existing_other_accepted:
        await callback.message.edit_text(
            "По этой заявке уже выбран другой автосервис.\n\n"
            "Вы не можете принять несколько предложений одновременно.\n"
            "Если нужно изменить выбор, свяжитесь с менеджером проекта.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ К заявке",
                            callback_data=f"req_view:{request_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ В меню",
                            callback_data="main:menu",
                        )
                    ],
                ]
            ),
        )
        await callback.answer()
        return

    # 1) Обновляем выбранный отклик — помечаем как принятый клиентом
    try:
        await api_client.update_offer(
            offer_id,
            {
                "status": "accepted",
            },
        )
    except Exception:
        await callback.message.answer(
            "Не удалось сохранить выбор сервиса. Попробуйте позже."
        )
        await callback.answer()
        return

    # 2) Обновляем заявку — привязываем выбранный сервис и переводим статус
    try:
        await api_client.update_request(
            request_id,
            {
                "service_center_id": service_center_id,
                "status": "accepted_by_service",
            },
        )
    except Exception:
        await callback.message.answer(
            "Сервис выбран, но не удалось обновить статус заявки.\n"
            "Если что-то пойдёт не так — напишите менеджеру.",
        )

    # 3) Уведомляем выбранный сервис и отклоняем остальных
    # 3.1. Находим владельца выбранного сервиса
    manager_tg_id: Optional[int] = None
    try:
        sc = await api_client.get_service_center(service_center_id)
        if isinstance(sc, dict):
            owner_id = sc.get("user_id") or sc.get("owner_id")
            if owner_id:
                manager = await api_client.get_user(int(owner_id))
                if isinstance(manager, dict):
                    manager_tg_id = manager.get("telegram_id")
    except Exception:
        logging.exception("Не удалось получить данные выбранного сервиса / менеджера")

    # 3.2. Загрузим саму заявку, чтобы показать её целиком СТО
    request_data: Dict[str, Any] = {}
    try:
        req = await api_client.get_request(request_id)
        if isinstance(req, dict):
            request_data = req
    except Exception:
        request_data = {}

    desc = (request_data.get("description") or "").strip() or "Описание не указано"
    addr = (request_data.get("address_text") or "").strip() or "Адрес не указан"
    category = (request_data.get("service_category") or "").strip() or "Без категории"

    # конструируем текст для СТО
    sc_text_lines = [
        f"✅ Клиент выбрал ваше предложение по заявке №{request_id:04d}.",
        "",
        f"<b>Категория:</b> {category}",
        f"<b>Адрес/место:</b> {addr}",
        "",
        "<b>Описание проблемы:</b>",
        desc,
        "",
        "Обновляйте статус заявки по мере работы:",
        "— «В работе» когда начали выполнять;",
        "— «Завершить» когда всё сделано;",
        "— «Отменить» если работа не будет выполняться.",
    ]
    sc_text = "\n".join(sc_text_lines)

    sc_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛠 В работе",
                    callback_data=f"sto:req_status:in_work:{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Завершить",
                    callback_data=f"sto:req_status:done:{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"sto:req_status:cancelled:{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📥 Все заявки клиентов",
                    callback_data="sto:req_list",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="main:menu",
                )
            ],
        ]
    )

    if manager_tg_id:
        try:
            await callback.bot.send_message(
                chat_id=manager_tg_id,
                text=sc_text,
                reply_markup=sc_kb,
            )
        except Exception:
            logging.exception("Не удалось отправить СТО карточку заявки с кнопками статуса")

    # 3.3. Отказ всем остальным СТО по этой заявке
    for off in offers:
        other_offer_id = off.get("id")
        if not other_offer_id or int(other_offer_id) == offer_id:
            continue

        other_sc_id = off.get("service_center_id")

        # Ставим статус REJECTED в backend
        try:
            await api_client.update_offer(
                int(other_offer_id),
                {"status": "rejected"},
            )
        except Exception:
            pass

        # Уведомляем этот сервис, что клиент выбрал другого
        try:
            sc_other = await api_client.get_service_center(int(other_sc_id))
            if isinstance(sc_other, dict):
                owner_id = sc_other.get("user_id") or sc_other.get("owner_id")
                if owner_id:
                    manager = await api_client.get_user(int(owner_id))
                    if isinstance(manager, dict):
                        manager_tg = manager.get("telegram_id")
                        if manager_tg:
                            await callback.bot.send_message(
                                chat_id=manager_tg,
                                text=(
                                    f"❌ Клиент выбрал другой сервис по заявке №{request_id:04d}.\n"
                                    "Ваше предложение отмечено как отклонённое."
                                ),
                            )
        except Exception:
            pass

    # 4) Сообщаем клиенту об успехе
    await callback.message.edit_text(
        "✅ Вы выбрали сервис по этой заявке.\n\n"
        "Мы уведомили выбранный сервис и отклонили остальные предложения.\n"
        "Сервис сможет отмечать статус заявки (в работе / завершена / отменена).",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ К заявке",
                        callback_data=f"req_view:{request_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ В меню",
                        callback_data="main:menu",
                    )
                ],
            ]
        ),
    )
    await callback.answer()

    # ------------------------------------------------------------------
    # 0) Загружаем все отклики по заявке и СТО, чтобы понять,
    #    не выбран ли уже какой-то сервис.
    # ------------------------------------------------------------------
    try:
        offers, sc_map = await _load_offers_with_sc(request_id)
    except Exception:
        offers, sc_map = [], {}

    this_offer = None
    for o in offers:
        if int(o.get("id", 0)) == offer_id:
            this_offer = o
            break

    # если этот отклик уже принят раньше — просто говорим клиенту
    if this_offer:
        st_raw = str(this_offer.get("status") or "").lower()
        if st_raw == OFFER_ACCEPT_STATUS:
            await callback.message.edit_text(
                "✅ Этот сервис уже выбран по данной заявке.\n\n"
                "При необходимости свяжитесь с сервисом для уточнения деталей.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⬅️ К заявке",
                                callback_data=f"req_view:{request_id}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="⬅️ В меню",
                                callback_data="main:menu",
                            )
                        ],
                    ]
                ),
            )
            await callback.answer()
            return

    # проверяем, нет ли уже другого принятого отклика
    existing_other_accepted = None
    for o in offers:
        oid = int(o.get("id", 0))
        status_raw = str(o.get("status") or "").lower()
        if oid != offer_id and status_raw == OFFER_ACCEPT_STATUS:
            existing_other_accepted = o
            break

    if existing_other_accepted:
        # уже есть другой выбранный сервис — не даём выбрать ещё один
        await callback.message.edit_text(
            "По этой заявке уже выбран другой автосервис.\n\n"
            "Вы не можете принять несколько предложений одновременно.\n"
            "Если нужно изменить выбор, свяжитесь с менеджером проекта.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ К заявке",
                            callback_data=f"req_view:{request_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ В меню",
                            callback_data="main:menu",
                        )
                    ],
                ]
            ),
        )
        await callback.answer()
        return

    # ------------------------------------------------------------------
    # 1) Обновляем выбранный отклик — помечаем как принятый клиентом
    # ------------------------------------------------------------------
    try:
        await api_client.update_offer(
            offer_id,
            {
                "status": OFFER_ACCEPT_STATUS,
            },
        )
    except Exception:
        await callback.message.answer(
            "Не удалось сохранить выбор сервиса. Попробуйте позже."
        )
        await callback.answer()
        return

    # ------------------------------------------------------------------
    # 2) Обновляем заявку — привязываем выбранный сервис и переводим статус
    # ------------------------------------------------------------------
    try:
        await api_client.update_request(
            request_id,
            {
                "service_center_id": service_center_id,
                "status": REQUEST_ACCEPT_STATUS,
            },
        )
    except Exception:
        # Считаем, что хотя бы выбор отклика сохранился.
        await callback.message.answer(
            "Сервис выбран, но не удалось обновить статус заявки.\n"
            "Если что-то пойдёт не так — напишите менеджеру.",
        )
        # продолжаем, чтобы хотя бы уведомить СТО
        # не делаем return

    # ------------------------------------------------------------------
    # 3) Уведомляем выбранный сервис и отклоняем остальных
    # ------------------------------------------------------------------

    # Уведомление выбранного сервиса
    try:
        chosen_sc = sc_map.get(service_center_id or -1)
        if isinstance(chosen_sc, dict):
            owner_id = chosen_sc.get("owner_id") or chosen_sc.get("user_id")
            if owner_id:
                manager = await api_client.get_user(int(owner_id))
                if isinstance(manager, dict):
                    manager_tg = manager.get("telegram_id")
                    if manager_tg:
                        await callback.bot.send_message(
                            chat_id=manager_tg,
                            text=(
                                f"✅ Клиент выбрал ваше предложение "
                                f"по заявке №{request_id}.\n\n"
                                "Свяжитесь с клиентом для уточнения деталей."
                            ),
                        )
    except Exception:
        # если не получилось уведомить сервис — не мешаем клиенту
        pass

    # Отказ всем остальным СТО по этой заявке
    for off in offers:
        other_offer_id = off.get("id")
        if not other_offer_id or int(other_offer_id) == offer_id:
            continue

        other_sc_id = off.get("service_center_id")

        # 3.1. Ставим статус REJECTED в backend
        try:
            await api_client.update_offer(
                int(other_offer_id),
                {"status": "rejected"},
            )
        except Exception:
            # не критично, идём дальше
            pass

        # 3.2. Отправляем уведомление этому сервису, что клиент выбрал другого
        try:
            sc = sc_map.get(other_sc_id or -1)
            if isinstance(sc, dict):
                owner_id = sc.get("owner_id") or sc.get("user_id")
                if owner_id:
                    manager = await api_client.get_user(int(owner_id))
                    if isinstance(manager, dict):
                        manager_tg = manager.get("telegram_id")
                        if manager_tg:
                            await callback.bot.send_message(
                                chat_id=manager_tg,
                                text=(
                                    f"❌ Клиент выбрал другой сервис по заявке №{request_id}.\n"
                                    "Ваше предложение отмечено как отклонённое."
                                ),
                            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 4) Сообщаем клиенту об успехе
    # ------------------------------------------------------------------
    await callback.message.edit_text(
        "✅ Вы выбрали сервис по этой заявке.\n\n"
        "Мы уведомили выбранный сервис и отклонили остальные предложения.\n"
        "В следующем шаге добавим полноценный чат по заявке.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ К заявке",
                        callback_data=f"req_view:{request_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ В меню",
                        callback_data="main:menu",
                    )
                ],
            ]
        ),
    )
    await callback.answer()
