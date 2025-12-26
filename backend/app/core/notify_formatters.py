from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.core.catalogs.service_categories import SERVICE_CATEGORY_LABELS


def webapp_button(text: str, url: str) -> Dict[str, str]:
    """
    Унифицированная кнопка для Telegram Mini App.
    Бот интерпретирует type=web_app и открывает миниапп, а не браузер.
    """
    return {"text": text, "type": "web_app", "url": url}


def url_button(text: str, url: str) -> Dict[str, str]:
    """
    Унифицированная URL-кнопка (открывает ссылку в браузере/карте).
    Бот интерпретирует все кнопки, кроме type=web_app, как обычные URL.
    """
    return {"text": text, "type": "url", "url": url}


def format_category(code: Optional[str]) -> str:
    if not code:
        return "—"
    return SERVICE_CATEGORY_LABELS.get(code, code)


def format_car(car: Any) -> str:
    """
    car ожидается как ORM-модель Car (или объект с похожими атрибутами).
    Формат: Brand Model / Year / Plate (если есть)
    """
    if not car:
        return "—"

    brand = getattr(car, "brand", None) or ""
    model = getattr(car, "model", None) or ""
    year = getattr(car, "year", None)
    plate = getattr(car, "plate_number", None) or getattr(car, "plate", None) or ""

    parts: List[str] = []
    name = (f"{brand} {model}").strip()
    if name:
        parts.append(name)
    if year:
        parts.append(f"{year} г.")
    if plate:
        parts.append(f"🚘 {plate}")

    return " / ".join(parts) if parts else "—"


def map_link(lat: Any, lon: Any) -> Optional[str]:
    try:
        if lat is None or lon is None:
            return None
        return f"https://maps.google.com/?q={float(lat)},{float(lon)}"
    except Exception:
        return None


def format_location(req: Any) -> str:
    """
    req ожидается как ORM-модель Request (или объект с похожими атрибутами).
    Используем address_text + координаты.
    """
    if not req:
        return "—"

    address_text = getattr(req, "address_text", None)
    lat = getattr(req, "latitude", None)
    lon = getattr(req, "longitude", None)

    lines: List[str] = []
    if address_text:
        lines.append(f"📍 {address_text}")

    link = map_link(lat, lon)
    if link:
        lines.append(f"🗺 {link}")

    return "\n".join(lines) if lines else "—"


def format_service_center(sc: Any) -> str:
    if not sc:
        return "—"
    name = (getattr(sc, "name", None) or "").strip()
    address = (getattr(sc, "address", None) or getattr(sc, "address_text", None) or "").strip()
    parts = []
    if name:
        parts.append(f"🏁 СТО: {name}")
    if address:
        parts.append(f"📍 {address}")
    return "\n".join(parts) if parts else "—"


def build_sc_new_request_message(
    request_obj: Any,
    service_center: Any,
    car: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)

    # клиент (владелец авто)
    user = getattr(request_obj, "user", None)
    owner_name = (
        (getattr(user, "full_name", None) or getattr(user, "name", None) or "").strip()
        if user
        else ""
    )

    cat = format_category(getattr(request_obj, "service_category", None))
    desc = (getattr(request_obj, "description", "") or "").strip()

    address_text = getattr(request_obj, "address_text", None) or getattr(request_obj, "address", None)
    lat = getattr(request_obj, "latitude", None)
    lon = getattr(request_obj, "longitude", None)
    map_url = map_link(lat, lon)

    msg_lines: List[str] = [
        "📩 Новая заявка",
        f"🧾 Категория: {cat}",
    ]

    if owner_name:
        msg_lines.append(f"👤 Клиент: {owner_name}")

    msg_lines.append(f"🚗 Авто: {format_car(car)}")

    if desc:
        msg_lines.append(f"💬 Описание: {desc}")

    if address_text:
        msg_lines.append(f"📍 {address_text}")
    elif map_url:
        msg_lines.append("📍 Текущее местоположение")

    url = f"{webapp_public_url.rstrip('/')}/sc/{getattr(service_center, 'id', '')}/requests/{request_id}"

    buttons: List[Dict[str, str]] = [webapp_button("Открыть заявку", url)]
    if map_url:
        buttons.append(url_button("🗺 Показать на карте", map_url))

    extra = {"request_id": request_id, "service_center_id": getattr(service_center, "id", None)}
    return "\n".join([x for x in msg_lines if x]), buttons, extra


def build_client_in_work_message(
    request_obj: Any,
    service_center: Any,
    car: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)
    msg_lines: List[str] = [
        "🛠 Заявка переведена в работу",
        f"🚗 Авто: {format_car(car)}",
        format_service_center(service_center),
    ]
    url = f"{webapp_public_url.rstrip('/')}/me/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {"request_id": request_id, "status": "IN_WORK"}
    return "\n".join([x for x in msg_lines if x]), buttons, extra


def build_client_done_message(
    request_obj: Any,
    service_center: Any,
    car: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)

    price_text = (getattr(request_obj, "final_price_text", None) or "").strip()
    final_price = getattr(request_obj, "final_price", None)

    msg_lines: List[str] = [
        "✅ Заявка завершена",
        f"🚗 Авто: {format_car(car)}",
        format_service_center(service_center),
    ]

    if price_text:
        msg_lines.append(f"💰 Итог: {price_text}")
    elif final_price is not None:
        msg_lines.append(f"💰 Итог: {final_price} ₽")

    url = f"{webapp_public_url.rstrip('/')}/me/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {"request_id": request_id, "status": "DONE"}
    return "\n".join([x for x in msg_lines if x]), buttons, extra


def build_sc_offer_selected_message(
    request_obj: Any,
    service_center: Any,
    car: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)

    # клиент
    user = getattr(request_obj, "user", None)
    client_name = (
        (getattr(user, "full_name", None) or getattr(user, "name", None) or "").strip()
        if user
        else ""
    )

    cat = format_category(getattr(request_obj, "service_category", None))
    desc = (getattr(request_obj, "description", "") or "").strip()

    address_text = getattr(request_obj, "address_text", None) or getattr(request_obj, "address", None)
    lat = getattr(request_obj, "latitude", None)
    lon = getattr(request_obj, "longitude", None)
    map_url = map_link(lat, lon)

    # коротко режем описание, чтобы не превращать уведомление в простыню
    if desc and len(desc) > 220:
        desc = desc[:217].rstrip() + "…"

    msg_lines: List[str] = [
        f"🎉 Ваш отклик по заявке №{request_id} выбран клиентом!" if request_id else "🎉 Ваш отклик выбран клиентом!",
        f"👤 Клиент: {client_name}" if client_name else "",
        f"🧾 Категория: {cat}" if cat else "",
        f"🚗 Авто: {format_car(car)}" if car else "",
        f"💬 Описание: {desc}" if desc else "",
    ]

    # адрес/карта
    if address_text:
        msg_lines.append(f"📍 {address_text}")
    elif map_url:
        msg_lines.append("📍 Местоположение: см. карту")
        msg_lines.append(f"🗺 {map_url}")

    msg_lines.append("Откройте заявку и переведите её в работу.")

    url = f"{webapp_public_url.rstrip('/')}/sc/{getattr(service_center, 'id', '')}/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {
        "request_id": request_id,
        "service_center_id": getattr(service_center, "id", None),
        "status": "SELECTED",
        "event": "offer_selected",
    }
    return "\n".join([x for x in msg_lines if x]), buttons, extra


def build_client_service_selected_message(
    request_obj: Any,
    service_center: Any,
    car: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)

    cat = format_category(getattr(request_obj, "service_category", None))
    address_text = getattr(request_obj, "address_text", None) or getattr(request_obj, "address", None)

    msg_lines: List[str] = [
        f"✅ Вы выбрали сервис по заявке №{request_id}." if request_id else "✅ Вы выбрали сервис по заявке.",
        f"🧾 Категория: {cat}" if cat else "",
        f"🚗 Авто: {format_car(car)}" if car else "",
        format_service_center(service_center),
        f"📍 {address_text}" if address_text else "",
    ]

    url = f"{webapp_public_url.rstrip('/')}/me/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {"request_id": request_id, "status": "ACCEPTED_BY_SERVICE", "event": "service_selected"}
    return "\n".join([x for x in msg_lines if x]), buttons, extra


def build_client_new_offer_message(
    offer_obj: Any,
    request_obj: Any,
    service_center: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)
    offer_id = getattr(offer_obj, "id", None)

    price_text = (getattr(offer_obj, "price_text", None) or "").strip()
    eta_text = (getattr(offer_obj, "eta_text", None) or "").strip()
    comment = (getattr(offer_obj, "comment", None) or "").strip()

    # fallback на старые поля, если текстовых нет
    price = getattr(offer_obj, "price", None)
    eta_hours = getattr(offer_obj, "eta_hours", None)

    if not price_text and price is not None:
        try:
            price_text = f"{float(price):g}"
        except Exception:
            price_text = str(price)

    if not eta_text and eta_hours is not None:
        try:
            eta_text = f"{int(eta_hours)} ч."
        except Exception:
            eta_text = str(eta_hours)

    msg_lines: List[str] = [
        f"📩 Новый отклик по заявке №{request_id}!" if request_id else "📩 Новый отклик по вашей заявке!",
        format_service_center(service_center),
        f"💰 Цена: {price_text}" if price_text else "",
        f"⏱ Срок: {eta_text}" if eta_text else "",
        f"💬 Комментарий: {comment}" if comment else "",
    ]

    url = f"{webapp_public_url.rstrip('/')}/me/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {"request_id": request_id, "offer_id": offer_id, "event": "offer_created"}
    return "\n".join([x for x in msg_lines if x]), buttons, extra


def build_client_request_cancelled_message(
    request_obj: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)

    msg_lines: List[str] = [
        "🚫 Заявка отменена",
        f"Заявка №{request_id}",
    ]

    url = f"{webapp_public_url.rstrip('/')}/me/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {"request_id": request_id, "status": "CANCELLED"}
    return "\n".join([x for x in msg_lines if x]), buttons, extra


def build_client_service_rejected_message(
    request_obj: Any,
    service_center: Any,
    car: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)
    reason = (getattr(request_obj, "reject_reason", "") or "").strip()

    msg_lines: List[str] = [
        "⛔ Сервис закрыл заявку",
        f"🚗 Авто: {format_car(car)}",
        format_service_center(service_center),
    ]
    if reason:
        msg_lines.append(f"📝 Причина: {reason}")

    url = f"{webapp_public_url.rstrip('/')}/me/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {"request_id": request_id, "status": "REJECTED_BY_SERVICE"}
    return "\n".join([x for x in msg_lines if x]), buttons, extra
