from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.core.catalogs.service_categories import SERVICE_CATEGORY_LABELS


def webapp_button(text: str, url: str) -> Dict[str, str]:
    """
    Унифицированная кнопка для Telegram Mini App.
    Бот интерпретирует type=web_app и открывает миниапп, а не браузер.
    """
    return {"text": text, "type": "web_app", "url": url}


def format_category(code: Optional[str]) -> str:
    if not code:
        return "—"
    return SERVICE_CATEGORY_LABELS.get(code, code)


def format_specializations(codes: Optional[Sequence[str]]) -> str:
    if not codes:
        return "—"
    labels = [SERVICE_CATEGORY_LABELS.get(c, c) for c in codes if c]
    return ", ".join(labels) if labels else "—"


def map_link(latitude: Optional[float], longitude: Optional[float]) -> Optional[str]:
    if latitude is None or longitude is None:
        return None
    # нейтральная ссылка (откроется на устройстве в картах)
    return f"https://maps.google.com/?q={latitude},{longitude}"


def format_car(car: Any) -> str:
    """
    car ожидается как ORM-модель Car (или объект с похожими атрибутами).
    Используем только то, что реально есть в модели: brand, model, year, license_plate.
    """
    if not car:
        return "—"

    brand = getattr(car, "brand", None)
    model = getattr(car, "model", None)
    year = getattr(car, "year", None)
    plate = getattr(car, "license_plate", None)

    parts: List[str] = []
    title = " ".join([p for p in [brand, model] if p])
    if title:
        parts.append(title)

    if year:
        parts.append(f"{year} г.")

    if plate:
        parts.append(f"🚘 {plate}")

    return " / ".join(parts) if parts else "—"


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
    """
    sc ожидается как ORM-модель ServiceCenter (или объект с похожими атрибутами).
    Используем: name, address, specializations.
    """
    if not sc:
        return "—"

    name = getattr(sc, "name", None)
    address = getattr(sc, "address", None)
    specs = getattr(sc, "specializations", None)

    lines: List[str] = []
    if name:
        lines.append(f"🏁 {name}")
    if address:
        lines.append(f"📍 {address}")

    spec_line = format_specializations(specs if isinstance(specs, list) else None)
    if spec_line != "—":
        lines.append(f"🧰 {spec_line}")

    return "\n".join(lines) if lines else "—"


# =========================
# Готовые шаблоны событий
# (возвращают: message, buttons, extra)
# =========================

def build_sc_new_request_message(
    request_obj: Any,
    service_center: Any,
    car: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)
    cat = format_category(getattr(request_obj, "service_category", None))
    desc = (getattr(request_obj, "description", "") or "").strip()
    loc = format_location(request_obj)

    msg_lines: List[str] = [
        "📩 Новая заявка",
        f"🧾 Категория: {cat}",
        f"🚗 Авто: {format_car(car)}",
    ]

    if desc:
        msg_lines.append(f"💬 Описание: {desc}")

    if loc != "—":
        msg_lines.append(loc)

    url = f"{webapp_public_url.rstrip('/')}/sc/{getattr(service_center, 'id', '')}/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
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
        "🛠 Заявка взята в работу",
        f"🚗 Авто: {format_car(car)}",
        format_service_center(service_center),
    ]

    url = f"{webapp_public_url.rstrip('/')}/me/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {"request_id": request_id, "status": "IN_WORK"}
    return "\n".join([x for x in msg_lines if x and x != "—"]), buttons, extra


def build_client_done_message(
    request_obj: Any,
    service_center: Any,
    car: Any,
    webapp_public_url: str,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    request_id = getattr(request_obj, "id", None)

    final_price_text = getattr(request_obj, "final_price_text", None)
    final_price = getattr(request_obj, "final_price", None)

    price_line = ""
    if final_price_text:
        price_line = f"💰 Итоговая цена: {final_price_text}"
    elif final_price is not None:
        try:
            price_line = f"💰 Итоговая цена: {float(final_price):.0f}"
        except Exception:
            price_line = f"💰 Итоговая цена: {final_price}"

    msg_lines: List[str] = [
        "✅ Заявка выполнена",
        f"🚗 Авто: {format_car(car)}",
        format_service_center(service_center),
        price_line,
    ]

    url = f"{webapp_public_url.rstrip('/')}/me/requests/{request_id}"
    buttons = [webapp_button("Открыть заявку", url)]
    extra = {"request_id": request_id, "status": "DONE"}
    return "\n".join([x for x in msg_lines if x]), buttons, extra


def build_client_rejected_message(
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
