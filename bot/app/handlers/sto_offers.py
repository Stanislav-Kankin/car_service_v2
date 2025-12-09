from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging

from ..api_client import api_client
from .general import get_main_menu

logger = logging.getLogger(__name__)

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


class STOOfferFSM(StatesGroup):
    waiting_text = State()

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
            text = f"#{req_id} — {status}"
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
        f"<b>Заявка №{request_id}</b>",
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


@router.callback_query(F.data.startswith("req_offer:choose:"))
async def request_offer_choose(callback: CallbackQuery):
    """
    Клиент выбирает конкретный отклик (выбирает СТО).
    callback_data: req_offer:choose:{request_id}:{offer_id}:{service_center_id}
    """
    try:
        _, _, raw_req_id, raw_offer_id, raw_sc_id = callback.data.split(":", maxsplit=4)
        request_id = int(raw_req_id)
        offer_id = int(raw_offer_id)
        service_center_id = int(raw_sc_id)
    except Exception:
        await callback.answer("Некорректные данные отклика.")
        return

    # 1) Обновляем отклик — помечаем как принятый клиентом
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

    # 2) Обновляем заявку — привязываем выбранный сервис и переводим статус
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
        await callback.answer()
        return

    await callback.message.edit_text(
        "✅ Вы выбрали сервис по этой заявке.\n\n"
        "Мы уведомим сервис о вашем выборе.\n"
        "В следующем шаге мы добавим полноценный чат по заявке.",
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

# ---------------------------------------------------------------------------
# БЛОК: Заявки клиентов для СТО
# ---------------------------------------------------------------------------


async def _get_service_center_for_owner(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Внутренний helper: по telegram_id владельца находим его СТО.
    Пока берём первый сервис из списка.
    """
    user = await api_client.get_user_by_telegram(telegram_id)
    if not isinstance(user, dict) or user.get("role") != "service_owner":
        return None

    user_id = user["id"]
    sc_list = await api_client.list_service_centers_by_user(user_id)

    if not isinstance(sc_list, list) or not sc_list:
        return None

    return sc_list[0]


@router.callback_query(F.data == "sto:req_list")
async def sto_requests_list(callback: CallbackQuery):
    """
    Список заявок клиентов для СТО.
    """
    telegram_id = callback.from_user.id

    sc = await _get_service_center_for_owner(telegram_id)
    if not sc:
        await callback.message.answer(
            "Похоже, у вас ещё нет зарегистрированного автосервиса "
            "или ваш профиль не является владельцем СТО.\n\n"
            "Зайдите в раздел «Регистрация СТО» в главном меню.",
        )
        await callback.answer()
        return

    specs = sc.get("specializations") or []
    if isinstance(specs, dict):
        specializations = [str(v) for v in specs.values()]
    elif isinstance(specs, list):
        specializations = [str(v) for v in specs]
    else:
        specializations = []

    try:
        requests = await api_client.list_requests_for_service_centers(
            specializations=specializations,
        )
    except Exception:
        await callback.message.answer(
            "Не удалось получить список заявок. Попробуйте позже.",
        )
        await callback.answer()
        return

    if not isinstance(requests, list) or not requests:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ В меню СТО",
                        callback_data="main:sto_menu",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ В главное меню",
                        callback_data="main:menu",
                    )
                ],
            ]
        )
        await callback.message.answer(
            "Сейчас нет активных заявок, подходящих под ваш автосервис.",
            reply_markup=kb,
        )
        await callback.answer()
        return

    lines: List[str] = [
        "<b>📥 Заявки клиентов</b>",
        "",
        "Выберите заявку, чтобы посмотреть детали и откликнуться:",
        "",
    ]

    buttons: List[List[InlineKeyboardButton]] = []

    for req in requests[:10]:  # пока ограничимся 10, потом можно сделать пагинацию
        req_id = req.get("id")
        category = req.get("service_category") or "Без категории"
        addr = req.get("address_text") or "Адрес не указан"
        status_raw = str(req.get("status") or "").lower()
        status_text = _status_to_text(status_raw)

        lines.append(f"• №{req_id}: {category} — {addr} ({status_text})")

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Заявка №{req_id}",
                    callback_data=f"sto:req_view:{req_id}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ В меню СТО",
                callback_data="main:sto_menu",
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ В главное меню",
                callback_data="main:menu",
            )
        ]
    )

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.answer("\n".join(lines), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sto:req_view:"))
async def sto_request_view(callback: CallbackQuery):
    """
    Карточка конкретной заявки для СТО.
    """
    try:
        _, _, req_id_str = callback.data.split(":", maxsplit=2)
        request_id = int(req_id_str)
    except (ValueError, AttributeError):
        await callback.answer()
        return

    try:
        request = await api_client.get_request(request_id)
    except Exception:
        request = None

    if not isinstance(request, dict):
        await callback.message.answer(
            "Не удалось получить данные по заявке. Попробуйте позже.",
        )
        await callback.answer()
        return

    status_raw = str(request.get("status") or "").lower()
    status_text = _status_to_text(status_raw)

    category = request.get("service_category") or "Без категории"
    addr = request.get("address_text") or "Адрес не указан"
    description = request.get("description") or "Без описания"

    text_lines = [
        f"<b>Заявка №{request_id}</b>",
        f"Статус: {status_text}",
        "",
        f"🛠 Категория: {category}",
        f"📍 Адрес / район: {addr}",
        "",
        "<b>Описание проблемы:</b>",
        description,
        "",
        "Если заявка вам подходит, вы можете отправить своё предложение.",
    ]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉️ Откликнуться",
                    callback_data=f"sto:offer_start:{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку заявок",
                    callback_data="sto:req_list",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню СТО",
                    callback_data="main:sto_menu",
                )
            ],
        ]
    )

    await callback.message.answer("\n".join(text_lines), reply_markup=kb)
    await callback.answer()


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@router.callback_query(F.data.startswith("sto:offer_start:"))
async def sto_offer_start(callback: CallbackQuery, state: FSMContext):
    """
    Старт отклика СТО: просим одним сообщением указать все условия.
    """
    try:
        _, _, raw_req_id = callback.data.split(":", maxsplit=2)
        request_id = int(raw_req_id)
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные заявки.")
        return

    await state.clear()
    await state.update_data(request_id=request_id)
    await state.set_state(STOOfferFSM.waiting_text)

    await callback.message.edit_text(
        f"Вы выбрали заявку №{request_id}.\n\n"
        "Отправьте <b>одним сообщением</b> условия для клиента: стоимость, "
        "сроки, когда можете принять автомобиль и т.п.\n\n"
        "Например:\n"
        "<i>Работа будет стоить 5000 ₽, сделаем за 2–3 часа, "
        "завтра в 11:30 свободно.</i>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отменить отклик",
                        callback_data=f"sto:offer_cancel:{request_id}",
                    )
                ]
            ]
        ),
    )
    await callback.answer()

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@router.callback_query(F.data.startswith("sto:offer_start:"))
async def sto_offer_start(callback: CallbackQuery, state: FSMContext):
    """
    Старт отклика СТО: просим одним сообщением указать все условия.
    """
    try:
        _, _, raw_req_id = callback.data.split(":", maxsplit=2)
        request_id = int(raw_req_id)
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные заявки.")
        return

    await state.clear()
    await state.update_data(request_id=request_id)
    await state.set_state(STOOfferFSM.waiting_text)

    await callback.message.edit_text(
        f"Вы выбрали заявку №{request_id}.\n\n"
        "Отправьте <b>одним сообщением</b> условия для клиента: стоимость, "
        "сроки, когда можете принять автомобиль и т.п.\n\n"
        "Например:\n"
        "<i>Работа будет стоить 5000 ₽, сделаем за 2–3 часа, "
        "завтра в 11:30 свободно.</i>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отменить отклик",
                        callback_data=f"sto:offer_cancel:{request_id}",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(STOOfferFSM.waiting_text)
async def sto_offer_text(message: Message, state: FSMContext):
    """
    Менеджер СТО отправляет одним сообщением условия для клиента.
    Мы создаём Offer с этим текстом в поле comment и уведомляем клиента.
    """
    text = (message.text or "").strip()
    if not text:
        await message.answer(
            "Сообщение пустое 😕\n"
            "Пожалуйста, напишите условия для клиента одним сообщением."
        )
        return

    data = await state.get_data()
    request_id = data.get("request_id")
    if not request_id:
        await state.clear()
        await message.answer(
            "Не удалось определить заявку.\n"
            "Откройте её заново через «📥 Заявки клиентов» и повторите отклик."
        )
        return

    # 1. Находим СТО по текущему менеджеру
    try:
        sc = await api_client.get_my_service_center(message.from_user.id)
    except Exception as e:
        logger.exception("Ошибка при получении СТО для отклика: %s", e)
        sc = None

    if not isinstance(sc, dict):
        await state.clear()
        await message.answer(
            "Не удалось определить, к какому автосервису вы привязаны.\n"
            "Проверьте, что вы завершили регистрацию СТО."
        )
        return

    service_center_id = sc.get("id")
    if not service_center_id:
        await state.clear()
        await message.answer(
            "Некорректные данные автосервиса. Попробуйте позже."
        )
        return

    payload = {
        "request_id": int(request_id),
        "service_center_id": int(service_center_id),
        # менеджер пишет условия в свободной форме
        "comment": text,
    }

    # 2. Создаём Offer в backend
    try:
        offer = await api_client.create_offer(payload)
    except Exception as e:
        logger.exception("Не удалось создать отклик СТО: %s", e)
        await state.clear()
        await message.answer(
            "Не получилось отправить отклик 😔\n"
            "Попробуйте ещё раз чуть позже."
        )
        return

    offer_id = offer.get("id")

    # 3. Уведомляем клиента о новом отклике
    try:
        # получаем заявку
        req = await api_client.get_request(int(request_id))
        user_id = None
        if isinstance(req, dict):
            user_id = req.get("user_id")

        client = None
        client_tg_id = None
        if user_id is not None:
            client = await api_client.get_user(int(user_id))
            if isinstance(client, dict):
                client_tg_id = client.get("telegram_id")

        sc_name = sc.get("name") or f"СТО #{service_center_id}"

        if client_tg_id:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Принять условия",
                            callback_data=(
                                f"req_offer:choose:{request_id}:{offer_id}:{service_center_id}"
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="❌ Отклонить предложение",
                            callback_data=(
                                f"req_offer:decline:{request_id}:{offer_id}"
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📄 Все предложения по заявке",
                            callback_data=f"req_offers:list:{request_id}",
                        )
                    ],
                ]
            )

            await message.bot.send_message(
                chat_id=client_tg_id,
                text=(
                    f"📩 <b>Новый отклик по вашей заявке №{request_id}</b>\n\n"
                    f"<b>Автосервис:</b> {sc_name}\n\n"
                    f"{text}\n\n"
                    "Вы можете сразу принять или отклонить это предложение, "
                    "либо посмотреть все отклики в разделе «📄 Мои заявки»."
                ),
                reply_markup=kb,
            )
    except Exception as e:
        # Не роняем поток, если уведомление не удалось — просто логируем
        logger.exception(
            "Не удалось отправить уведомление клиенту о новом отклике: %s", e
        )

    # 4. Завершаем FSM и отвечаем менеджеру
    await state.clear()
    await message.answer(
        "✅ Ваше предложение отправлено клиенту!\n\n"
        "Клиент увидит его в разделе «📄 Мои заявки» "
        "и в уведомлении в чате.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📥 Заявки клиентов",
                        callback_data="sto:req_list",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ В меню СТО",
                        callback_data="main:sto_menu",
                    )
                ],
            ]
        ),
    )
