from typing import Any
import os
import math

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    status,
    Query
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from httpx import AsyncClient

from ..api_client import get_backend_client
from ..dependencies import get_templates
from ..config import settings

router = APIRouter(
    prefix="/me",
    tags=["user"],
)

templates = get_templates()

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")

# --------------------------------------------------------------------
# Авторизация: ВСЕ маршруты /me/* требуют user_id в cookie
# --------------------------------------------------------------------


def get_current_user_id(request: Request) -> int:
    """
    Берём user_id из request.state.user_id, который кладёт UserIDMiddleware.
    Все маршруты /me/* требуют авторизации.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не авторизован",
        )
    return int(user_id)

def _coerce_int(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


async def _get_current_user_obj(request: Request, client: AsyncClient) -> dict[str, Any] | None:
    """
    Возвращает user из backend или None, если user_id нет / backend вернул 404.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return None

    try:
        resp = await client.get(f"/api/v1/users/{int(user_id)}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _is_profile_complete(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    full_name = (user.get("full_name") or "").strip()
    phone = (user.get("phone") or "").strip()
    return bool(full_name) and bool(phone)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Расстояние по прямой между двумя точками (км).
    Без внешних зависимостей. Подходит для сортировки/индикации.
    """
    r = 6371.0088  # средний радиус Земли в км
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _enrich_service_centers_with_distance_and_maps(
    *,
    request_lat: float | None,
    request_lon: float | None,
    service_centers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Добавляет в каждый sc:
      - distance_km: float | None
      - maps_url: str | None (Яндекс.Карты: маршрут или точка)
    Ничего не ломает, если координат нет.
    """
    out: list[dict[str, Any]] = []

    for sc in (service_centers or []):
        if not isinstance(sc, dict):
            continue

        sc_lat = sc.get("latitude")
        sc_lon = sc.get("longitude")

        distance_km: float | None = None
        maps_url: str | None = None

        try:
            if sc_lat is not None and sc_lon is not None:
                sc_lat_f = float(sc_lat)
                sc_lon_f = float(sc_lon)

                # Маршрут: если есть точка заявки
                if request_lat is not None and request_lon is not None:
                    req_lat_f = float(request_lat)
                    req_lon_f = float(request_lon)

                    distance_km = haversine_km(req_lat_f, req_lon_f, sc_lat_f, sc_lon_f)

                    # Яндекс ожидает lat,lon в rtext как "lat,lon~lat,lon"
                    maps_url = (
                        "https://yandex.ru/maps/?"
                        f"rtext={req_lat_f},{req_lon_f}~{sc_lat_f},{sc_lon_f}&rtt=auto"
                    )
                else:
                    # Просто точка СТО (Яндекс: pt=lon,lat)
                    maps_url = (
                        "https://yandex.ru/maps/?"
                        f"pt={sc_lon_f},{sc_lat_f}&z=14&l=map"
                    )
        except Exception:
            distance_km = None
            maps_url = maps_url  # оставим что было/None

        out.append(
            {
                **sc,
                "distance_km": distance_km,
                "maps_url": maps_url,
            }
        )

    return out


# --------------------------------------------------------------------
# Справочники для подписей категорий и статусов
# --------------------------------------------------------------------

SERVICE_CATEGORY_LABELS = {
    "sto": "СТО / общий ремонт",
    "wash": "Автомойка",
    "tire": "Шиномонтаж",
    "electric": "Автоэлектрик",
    "mechanic": "Слесарные работы",
    "paint": "Малярные / кузовные работы",
    "maint": "ТО / обслуживание",
    "agg_turbo": "Ремонт турбин",
    "agg_starter": "Ремонт стартеров",
    "agg_generator": "Ремонт генераторов",
    "agg_steering": "Рулевые рейки",
    "mech": "Слесарные работы",
    "elec": "Автоэлектрик",
    "body": "Кузовные работы",
    "diag": "Диагностика",
    "agg": "Ремонт агрегатов",
}

STATUS_LABELS = {
    "new": "Новая",
    "sent": "Отправлена СТО",
    "accepted_by_service": "Принята сервисом",
    "in_work": "В работе",
    "done": "Завершена",
    "cancelled": "Отменена",
    "rejected_by_service": "Отклонена СТО",
}

PRIMARY_SERVICE_CODES = [
    "sto",
    "maint",
    "mechanic",
    "electric",
    "diag",
    "body",
    "paint",
]

EXTRA_SERVICE_CODES = [
    "wash",
    "tire",
    "agg",
]


def _build_service_categories() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """
    Возвращает списки (code, label) для основных и дополнительных категорий.
    """
    primary = [
        (code, SERVICE_CATEGORY_LABELS[code])
        for code in PRIMARY_SERVICE_CODES
        if code in SERVICE_CATEGORY_LABELS
    ]
    extra = [
        (code, SERVICE_CATEGORY_LABELS[code])
        for code in EXTRA_SERVICE_CODES
        if code in SERVICE_CATEGORY_LABELS
    ]
    return primary, extra


# --------------------------------------------------------------------
# Вспомогательный загрузчик машины с проверкой владельца
# --------------------------------------------------------------------


async def _load_car_for_owner(
    request: Request,
    client: AsyncClient,
    car_id: int,
) -> dict[str, Any]:
    """
    Загружаем машину по ID и проверяем, что она принадлежит текущему пользователю.
    """
    current_user_id = get_current_user_id(request)

    try:
        resp = await client.get(f"/api/v1/cars/{car_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Автомобиль не найден")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Ошибка backend при загрузке автомобиля")

    car = resp.json()

    if car.get("user_id") != current_user_id:
        # Чужой автомобиль — доступ запрещён
        raise HTTPException(status_code=403, detail="Нет доступа к этому автомобилю")

    return car


# --------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------


@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    user_id = getattr(request.state, "user_id", None)

    # ✅ если cookie нет — идём в единую точку auth
    if not user_id:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    user_obj = getattr(request.state, "user_obj", None)
    if user_obj is None:
        user_obj = await _get_current_user_obj(request, client)

    return templates.TemplateResponse(
        "user/dashboard.html",
        {"request": request, "show_dashboard": True, "user": user_obj},
    )


@router.get("/register", response_class=HTMLResponse)
async def user_register_get(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    user_id = getattr(request.state, "user_id", None)

    # ✅ если cookie нет — идём в единую точку auth
    if not user_id:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    user_obj = await _get_current_user_obj(request, client)

    if _is_profile_complete(user_obj):
        return RedirectResponse(url="/me/dashboard", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        "user/register.html",
        {
            "request": request,
            "error_message": None,
            "form": {
                "full_name": (user_obj or {}).get("full_name") or "",
                "phone": (user_obj or {}).get("phone") or "",
                "city": (user_obj or {}).get("city") or "",
            },
        },
    )


@router.post("/register", response_class=HTMLResponse)
async def user_register_post(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    full_name: str = Form(""),
    phone: str = Form(""),
    city: str = Form(""),
) -> HTMLResponse:
    user_id = getattr(request.state, "user_id", None)

    # ✅ если cookie нет — идём в единую точку auth
    if not user_id:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    full_name = (full_name or "").strip()
    phone = (phone or "").strip()
    city = (city or "").strip()

    if not full_name or not phone:
        return templates.TemplateResponse(
            "user/register.html",
            {
                "request": request,
                "error_message": "ФИО и телефон обязательны.",
                "form": {"full_name": full_name, "phone": phone, "city": city},
            },
        )

    payload = {"full_name": full_name, "phone": phone, "city": city or None}

    try:
        resp = await client.patch(f"/api/v1/users/{int(user_id)}", json=payload)
        resp.raise_for_status()
    except Exception:
        return templates.TemplateResponse(
            "user/register.html",
            {
                "request": request,
                "error_message": "Не удалось сохранить регистрацию. Попробуйте ещё раз.",
                "form": {"full_name": full_name, "phone": phone, "city": city},
            },
        )

    next_url = request.query_params.get("next") or "/me/dashboard"
    return RedirectResponse(url=next_url, status_code=status.HTTP_303_SEE_OTHER)


# --------------------------------------------------------------------
# Гараж — список машин
# --------------------------------------------------------------------


@router.get("/garage", response_class=HTMLResponse)
async def user_garage(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    user_id = get_current_user_id(request)
    user_obj = await _get_current_user_obj(request, client)
    if not _is_profile_complete(user_obj):
        return RedirectResponse(url="/me/register?next=/me/garage", status_code=status.HTTP_302_FOUND)

    cars: list[dict[str, Any]] = []
    error_message: str | None = None

    bonus_hidden_mode: bool = bool(getattr(settings, "BONUS_HIDDEN_MODE", True))

    bonus_balance: int = 0
    bonus_transactions: list[dict[str, Any]] = []

    # 1) машины
    try:
        resp = await client.get(f"/api/v1/cars/by-user/{user_id}")
        if resp.status_code == 404:
            cars = []
        else:
            resp.raise_for_status()
            cars = resp.json()
    except Exception:
        error_message = "Не удалось загрузить список автомобилей. Попробуйте позже."
        cars = []

    # 2) бонусы — ВРЕМЕННО скрыты (BONUS_HIDDEN_MODE)
    tx_view: list[dict[str, Any]] = []

    if not bonus_hidden_mode:
        try:
            resp = await client.get(f"/api/v1/bonus/{user_id}/balance")
            if resp.status_code == 200:
                bonus_balance = int(resp.json() or 0)
        except Exception:
            bonus_balance = 0

        try:
            resp = await client.get(f"/api/v1/bonus/{user_id}/transactions")
            if resp.status_code == 200:
                raw = resp.json() or []
                if isinstance(raw, list):
                    bonus_transactions = raw
        except Exception:
            bonus_transactions = []

        bonus_reason_labels = {
            "registration": "Регистрация",
            "create_request": "Создание заявки",
            "complete_request": "Завершение заявки",
            "rate_service": "Оценка сервиса",
            "manual_adjust": "Ручная корректировка",
        }

        for tx in bonus_transactions:
            if not isinstance(tx, dict):
                continue
            reason = str(tx.get("reason") or "")
            tx_view.append({**tx, "reason_label": bonus_reason_labels.get(reason, reason or "—")})

        try:
            tx_view.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        except Exception:
            pass

    return templates.TemplateResponse(
        "user/garage.html",
        {
            "request": request,
            "cars": cars,
            "error_message": error_message,
            "bonus_hidden_mode": bonus_hidden_mode,
            "bonus_balance": bonus_balance,
            "bonus_transactions": tx_view,
        },
    )


# --------------------------------------------------------------------
# Создание автомобиля — форма
# --------------------------------------------------------------------


@router.get("/cars/create", response_class=HTMLResponse)
async def car_create_get(
    request: Request,
) -> HTMLResponse:
    """
    Показ формы создания нового автомобиля.
    """
    _ = get_current_user_id(request)

    return templates.TemplateResponse(
        "user/car_form.html",
        {
            "request": request,
            "mode": "create",
            "car": None,
            "error_message": None,
        },
    )


# --------------------------------------------------------------------
# Создание автомобиля — обработка формы
# --------------------------------------------------------------------


@router.post("/cars/create", response_class=HTMLResponse)
async def car_create_post(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    brand: str = Form(""),
    model: str = Form(""),
    year: str = Form(""),
    license_plate: str = Form(""),
    vin: str = Form(""),
    engine_type: str = Form(""),
    engine_volume_l: str = Form(""),
    engine_power_kw: str = Form(""),
) -> HTMLResponse:
    """
    Обработка формы создания автомобиля.
    """
    user_id = get_current_user_id(request)

    error_message: str | None = None

    # Парсим год
    year_value: int | None = None
    if year.strip():
        try:
            year_value = int(year.strip())
        except ValueError:
            error_message = "Год выпуска должен быть числом."

    # Двигатель
    engine_type_value: str | None = (engine_type or "").strip() or None

    engine_volume_value: float | None = None
    if engine_volume_l.strip():
        try:
            engine_volume_value = float(engine_volume_l.replace(",", ".").strip())
        except ValueError:
            error_message = "Объём двигателя должен быть числом (например 1.6)."

    engine_power_value: int | None = None
    if engine_power_kw.strip():
        try:
            engine_power_value = int(engine_power_kw.strip())
        except ValueError:
            error_message = "Мощность (кВт) должна быть числом."

    # Если электрический — объём не нужен
    if engine_type_value == "electric":
        engine_volume_value = None
    else:
        # Для не электрических мощность не обязательна — оставляем как есть
        pass

    # Если ошибка валидации на фронте — не ходим в backend
    if error_message:
        car_data = {
            "brand": brand,
            "model": model,
            "year": year,
            "license_plate": license_plate,
            "vin": vin,
            "engine_type": engine_type,
            "engine_volume_l": engine_volume_l,
            "engine_power_kw": engine_power_kw,
        }
        return templates.TemplateResponse(
            "user/car_form.html",
            {
                "request": request,
                "mode": "create",
                "car": car_data,
                "error": error_message,
            },
        )

    payload: dict[str, Any] = {
        "user_id": user_id,
        "brand": brand or None,
        "model": model or None,
        "year": year_value,
        "license_plate": license_plate or None,
        "vin": vin or None,
        "engine_type": engine_type_value,
        "engine_volume_l": engine_volume_value,
        "engine_power_kw": engine_power_value,
    }

    try:
        resp = await client.post("/api/v1/cars/", json=payload)
        resp.raise_for_status()
        car_created = resp.json()
    except Exception:
        error_message = "Не удалось создать автомобиль. Попробуйте позже."
        car_data = {
            "brand": brand,
            "model": model,
            "year": year,
            "license_plate": license_plate,
            "vin": vin,
            "engine_type": engine_type,
            "engine_volume_l": engine_volume_l,
            "engine_power_kw": engine_power_kw,
        }
        return templates.TemplateResponse(
            "user/car_form.html",
            {
                "request": request,
                "mode": "create",
                "car": car_data,
                "error": error_message,
            },
        )

    return RedirectResponse(url=f"/me/cars/{car_created['id']}", status_code=303)


# --------------------------------------------------------------------
# Редактирование автомобиля — форма
# --------------------------------------------------------------------


@router.get("/cars/{car_id}/edit", response_class=HTMLResponse)
async def car_edit_get(
    car_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Показ формы редактирования автомобиля.
    """
    car = await _load_car_for_owner(request, client, car_id)

    return templates.TemplateResponse(
        "user/car_form.html",
        {
            "request": request,
            "mode": "edit",
            "car": car,
            "error_message": None,
        },
    )


# --------------------------------------------------------------------
# Редактирование автомобиля — обработка формы
# --------------------------------------------------------------------


@router.post("/cars/{car_id}/edit", response_class=HTMLResponse)
async def car_edit_post(
    car_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    brand: str = Form(""),
    model: str = Form(""),
    year: str = Form(""),
    license_plate: str = Form(""),
    vin: str = Form(""),
    engine_type: str = Form(""),
    engine_volume_l: str = Form(""),
    engine_power_kw: str = Form(""),
) -> HTMLResponse:
    """
    Обработка формы редактирования автомобиля.
    """
    _ = get_current_user_id(request)

    error_message: str | None = None

    # Парсим год
    year_value: int | None = None
    if year.strip():
        try:
            year_value = int(year.strip())
        except ValueError:
            error_message = "Год выпуска должен быть числом."

    # Двигатель
    engine_type_value: str | None = (engine_type or "").strip() or None

    engine_volume_value: float | None = None
    if engine_volume_l.strip():
        try:
            engine_volume_value = float(engine_volume_l.replace(",", ".").strip())
        except ValueError:
            error_message = "Объём двигателя должен быть числом (например 1.6)."

    engine_power_value: int | None = None
    if engine_power_kw.strip():
        try:
            engine_power_value = int(engine_power_kw.strip())
        except ValueError:
            error_message = "Мощность (кВт) должна быть числом."

    # Если электрический — объём не нужен
    if engine_type_value == "electric":
        engine_volume_value = None

    car_data = {
        "id": car_id,
        "brand": brand,
        "model": model,
        "year": year,
        "license_plate": license_plate,
        "vin": vin,
        "engine_type": engine_type,
        "engine_volume_l": engine_volume_l,
        "engine_power_kw": engine_power_kw,
    }

    if error_message:
        return templates.TemplateResponse(
            "user/car_form.html",
            {
                "request": request,
                "mode": "edit",
                "car": car_data,
                "error": error_message,
            },
        )

    payload: dict[str, Any] = {
        "brand": brand or None,
        "model": model or None,
        "year": year_value,
        "license_plate": license_plate or None,
        "vin": vin or None,
        "engine_type": engine_type_value,
        "engine_volume_l": engine_volume_value,
        "engine_power_kw": engine_power_value,
    }

    try:
        resp = await client.patch(f"/api/v1/cars/{car_id}", json=payload)
        resp.raise_for_status()
    except Exception:
        error_message = "Не удалось сохранить изменения. Попробуйте позже."
        return templates.TemplateResponse(
            "user/car_form.html",
            {
                "request": request,
                "mode": "edit",
                "car": car_data,
                "error": error_message,
            },
        )

    return RedirectResponse(url=f"/me/cars/{car_id}", status_code=303)

# --------------------------------------------------------------------
# Удаление автомобиля
# --------------------------------------------------------------------


@router.post("/cars/{car_id}/delete", response_class=HTMLResponse)
async def car_delete_post(
    car_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Удаление автомобиля и редирект в гараж.
    """
    # Проверяем, что машина принадлежит пользователю
    _ = await _load_car_for_owner(request, client, car_id)

    try:
        resp = await client.delete(f"/api/v1/cars/{car_id}")
        # Если 404 — считаем, что уже удалена
        if resp.status_code not in (204, 404):
            resp.raise_for_status()
    except Exception:
        # Даже если удаление не удалось — вернёмся в гараж с мягкой деградацией
        return RedirectResponse(
            url="/me/garage",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url="/me/garage",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# --------------------------------------------------------------------
# Карточка машины
# --------------------------------------------------------------------


@router.get("/cars/{car_id}", response_class=HTMLResponse)
async def car_detail(
    car_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    car = await _load_car_for_owner(request, client, car_id)

    return templates.TemplateResponse(
        "user/car_detail.html",
        {"request": request, "car": car},
    )


# --------------------------------------------------------------------
# Список заявок
# --------------------------------------------------------------------


@router.get("/requests", response_class=HTMLResponse)
async def requests_list(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    user_id = get_current_user_id(request)

    requests_data: list[dict[str, Any]] = []
    error_message = None

    try:
        resp = await client.get(f"/api/v1/requests/by-user/{user_id}")
        if resp.status_code == 404:
            requests_data = []
        else:
            resp.raise_for_status()
            requests_data = resp.json()
    except Exception:
        error_message = "Не удалось загрузить список заявок."
        requests_data = []

    for r in requests_data:
        r["status_label"] = STATUS_LABELS.get(r.get("status"), r.get("status"))
        code = r.get("service_category") or ""
        r["service_category_label"] = SERVICE_CATEGORY_LABELS.get(code, code or "Услуга")

    return templates.TemplateResponse(
        "user/request_list.html",
        {"request": request, "requests": requests_data, "error_message": error_message},
    )


# --------------------------------------------------------------------
# Создание заявки — GET
# --------------------------------------------------------------------


@router.get("/requests/create", response_class=HTMLResponse)
async def request_create_get(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    car_id: int | None = None,
) -> HTMLResponse:
    """
    Показ формы создания заявки.
    Если передан car_id, подгружаем машину и показываем её в шапке.
    """
    user_id = get_current_user_id(request)

    # ✅ если авто не выбрано — показываем список авто прямо на странице (без тупика)
    cars: list[dict[str, Any]] = []
    if car_id is None:
        try:
            resp = await client.get(f"/api/v1/cars/by-user/{user_id}")
            if resp.status_code == 200:
                raw = resp.json() or []
                if isinstance(raw, list):
                    cars = raw
        except Exception:
            cars = []

    car: dict[str, Any] | None = None
    if car_id is not None:
        try:
            car = await _load_car_for_owner(request, client, car_id)
        except HTTPException:
            raise
        except Exception:
            car = None

    primary_categories, extra_categories = _build_service_categories()

    return templates.TemplateResponse(
        "user/request_create.html",
        {
            "request": request,
            "car_id": car_id,
            "car": car,
            "cars": cars,
            "car_missing": car is None,
            "created_request": None,
            "error_message": None,
            "primary_categories": primary_categories,
            "extra_categories": extra_categories,
            "form_data": {},
        },
    )

# --------------------------------------------------------------------
# Создание заявки — POST
# --------------------------------------------------------------------


@router.post("/requests/create", response_class=HTMLResponse)
async def request_create_post(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),

    car_id_raw: str = Form("", alias="car_id"),

    address_text: str = Form(""),
    is_car_movable: str = Form("movable"),
    radius_km: int = Form(5),
    service_category: str = Form("sto"),
    description: str = Form(...),
    hide_phone: bool = Form(False),

    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
) -> HTMLResponse:
    user_id = get_current_user_id(request)

    def _try_parse_coords_from_text(text: str) -> tuple[float, float] | None:
        """
        Поддержка ввода координат прямо в поле адреса:
        "55.7558, 37.6173" или "55.7558 37.6173"
        """
        import re

        if not text:
            return None

        t = text.strip()
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)", t)
        if not m:
            return None

        try:
            lat = float(m.group(1))
            lon = float(m.group(2))
        except Exception:
            return None

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None

        return (lat, lon)

    templates = get_templates()

    async def _render_form(
        *,
        car_id: int | None,
        car: dict[str, Any] | None,
        car_missing: bool,
        error_message: str | None,
        form_data: dict[str, Any],
    ) -> HTMLResponse:
        primary_categories, extra_categories = _build_service_categories()

        cars: list[dict[str, Any]] = []
        if car_id is None:
            try:
                resp = await client.get(f"/api/v1/cars/by-user/{user_id}")
                if resp.status_code == 200:
                    raw = resp.json() or []
                    if isinstance(raw, list):
                        cars = raw
            except Exception:
                cars = []

        return templates.TemplateResponse(
            "user/request_create.html",
            {
                "request": request,
                "car_id": car_id,
                "car": car,
                "cars": cars,
                "car_missing": car_missing,
                "created_request": None,
                "error_message": error_message,
                "primary_categories": primary_categories,
                "extra_categories": extra_categories,
                "form_data": form_data,
            },
        )

    car_id_raw = (car_id_raw or "").strip()
    if not car_id_raw:
        return await _render_form(
            car_id=None,
            car=None,
            car_missing=True,
            error_message=None,
            form_data={
                "address_text": address_text,
                "is_car_movable": is_car_movable,
                "radius_km": radius_km,
                "service_category": service_category,
                "description": description,
                "hide_phone": hide_phone,
                "latitude": latitude,
                "longitude": longitude,
            },
        )

    try:
        car_id = int(car_id_raw)
    except ValueError:
        return await _render_form(
            car_id=None,
            car=None,
            car_missing=True,
            error_message="Некорректный идентификатор автомобиля.",
            form_data={},
        )

    try:
        car_resp = await client.get(f"/api/v1/cars/{car_id}")
        car_resp.raise_for_status()
        car = car_resp.json()
    except Exception:
        car = None

    # --- гео должно быть задано (иначе /choose-service будет 400) ---
    lat = latitude
    lon = longitude

    if lat is None or lon is None:
        parsed = _try_parse_coords_from_text(address_text)
        if parsed:
            lat, lon = parsed

    if lat is None or lon is None:
        return await _render_form(
            car_id=car_id,
            car=car,
            car_missing=False,
            error_message=(
                "📍 Чтобы подобрать подходящие СТО, нужно указать геолокацию.\n"
                "Нажмите «Определить моё местоположение» или введите координаты в поле адреса\n"
                "например: 55.7558, 37.6173"
            ),
            form_data={
                "address_text": address_text,
                "is_car_movable": is_car_movable,
                "radius_km": radius_km,
                "service_category": service_category,
                "description": description,
                "hide_phone": hide_phone,
                "latitude": lat,
                "longitude": lon,
            },
        )

    movable = is_car_movable == "movable"

    # --- валидация описания (backend требует минимум 3 символа) ---
    desc = (description or "").strip()
    if len(desc) < 3:
        return await _render_form(
            car_id=car_id,
            car=car,
            car_missing=False,
            error_message="Опишите проблему (минимум 3 символа).",
            form_data={
                "address_text": address_text,
                "is_car_movable": is_car_movable,
                "radius_km": radius_km,
                "service_category": service_category,
                "description": description,
                "hide_phone": hide_phone,
                "latitude": lat,
                "longitude": lon,
            },
        )

    payload = {
        "user_id": user_id,
        "car_id": car_id,
        "latitude": lat,
        "longitude": lon,
        "address_text": address_text or None,
        "is_car_movable": movable,
        "need_tow_truck": not movable,
        "need_mobile_master": not movable,
        "radius_km": radius_km,
        "service_category": service_category,
        "description": desc,
        "photos": [],
        "hide_phone": hide_phone,
    }

    try:
        resp = await client.post("/api/v1/requests/", json=payload)
        if resp.status_code == 422:
            # backend вернул ошибку валидации (чаще всего — пустое описание или неверное гео)
            return await _render_form(
                car_id=car_id,
                car=car,
                car_missing=False,
                error_message="Проверьте поля заявки: описание должно быть минимум 3 символа, а геолокация задана.",
                form_data={
                    "address_text": address_text,
                    "is_car_movable": is_car_movable,
                    "radius_km": radius_km,
                    "service_category": service_category,
                    "description": description,
                    "hide_phone": hide_phone,
                    "latitude": lat,
                    "longitude": lon,
                },
            )

        resp.raise_for_status()
        created_request = resp.json()
        created_id = int(created_request.get("id"))
    except Exception:
        return await _render_form(
            car_id=car_id,
            car=car,
            car_missing=False,
            error_message="Не удалось создать заявку. Попробуйте позже.",
            form_data={
                "address_text": address_text,
                "is_car_movable": is_car_movable,
                "radius_km": radius_km,
                "service_category": service_category,
                "description": description,
                "hide_phone": hide_phone,
                "latitude": lat,
                "longitude": lon,
            },
        )

    return RedirectResponse(
        url=f"/me/requests/{created_id}/choose-service",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/requests/{request_id}/send-to-selected", response_class=HTMLResponse)
async def request_send_selected_post(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    service_center_ids: list[int] = Form([]),
) -> HTMLResponse:
    _ = get_current_user_id(request)
    templates = get_templates()

    selected = [int(x) for x in (service_center_ids or []) if x]
    selected = sorted(set(selected))

    if not selected:
        # перерисуем страницу выбора с ошибкой
        error_message = "Выберите хотя бы один сервис."
        service_centers: list[dict[str, Any]] = []

        # подтянем координаты заявки (для distance/maps)
        req_data: dict[str, Any] = {}
        try:
            r = await client.get(f"/api/v1/requests/{request_id}")
            if r.status_code == 200:
                req_data = r.json() or {}
        except Exception:
            req_data = {}

        request_lat = req_data.get("latitude") if isinstance(req_data, dict) else None
        request_lon = req_data.get("longitude") if isinstance(req_data, dict) else None

        try:
            sc_resp = await client.get(f"/api/v1/service-centers/for-request/{request_id}")
            sc_resp.raise_for_status()
            raw = sc_resp.json() or []
            if isinstance(raw, list):
                service_centers = raw
        except Exception:
            error_message = "Не удалось загрузить список подходящих СТО."
            service_centers = []

        service_centers = _enrich_service_centers_with_distance_and_maps(
            request_lat=request_lat,
            request_lon=request_lon,
            service_centers=service_centers,
        )

        return templates.TemplateResponse(
            "user/request_choose_service.html",
            {
                "request": request,
                "request_id": request_id,
                "service_centers": service_centers,
                "error_message": error_message,
                "bot_username": BOT_USERNAME,
            },
        )

    try:
        resp = await client.post(
            f"/api/v1/requests/{request_id}/send_to_selected",
            json={"service_center_ids": selected},
        )
        resp.raise_for_status()
    except Exception:
        return await request_detail(request_id, request, client, sent_all=False)

    return await request_detail(request_id, request, client, sent_all=True)


@router.get("/requests/{request_id}/view", response_class=HTMLResponse)
@router.get("/requests/{request_id}", response_class=HTMLResponse)
async def request_detail(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    sent_all: bool | None = None,
    chosen_service_id: int | None = None,
) -> HTMLResponse:

    _ = get_current_user_id(request)

    import os
    bot_username = os.getenv("BOT_USERNAME", "").strip().lstrip("@")

    try:
        resp = await client.get(f"/api/v1/requests/{request_id}")
        if resp.status_code == 404:
            raise HTTPException(404, "Заявка не найдена")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Ошибка при загрузке заявки")

    req_data = resp.json()

    code = req_data.get("status")
    req_data["status_label"] = STATUS_LABELS.get(code, code)
    cat = req_data.get("service_category")
    req_data["service_category_label"] = SERVICE_CATEGORY_LABELS.get(cat, cat)

    car = None
    car_id = req_data.get("car_id")
    if car_id:
        try:
            car_resp = await client.get(f"/api/v1/cars/{car_id}")
            if car_resp.status_code == 200:
                car = car_resp.json()
        except Exception:
            car = None

    can_distribute = req_data.get("status") in ("new", "sent")

    offers: list[dict[str, Any]] = []
    accepted_offer_id: int | None = None
    accepted_sc_id: int | None = None

    try:
        offers_resp = await client.get(f"/api/v1/offers/by-request/{request_id}")
        if offers_resp.status_code == 200:
            offers = offers_resp.json() or []
    except Exception:
        offers = []

    for o in offers:
        if o.get("status") == "accepted":
            accepted_offer_id = int(o.get("id"))
            accepted_sc_id = int(o.get("service_center_id"))
            break

    # Для отображения “Написать в Telegram” нам нужно знать telegram_id СТО по offer-ам
    offer_sc_telegram_ids: dict[int, int] = {}
    service_centers_by_id: dict[int, dict[str, Any]] = {}

    try:
        # Соберём уникальные ID СТО из офферов
        sc_ids = sorted(
            {int(o.get("service_center_id")) for o in offers if o.get("service_center_id") is not None}
        )
    except Exception:
        sc_ids = []

    if sc_ids:
        for sc_id in sc_ids:
            try:
                sc_resp = await client.get(f"/api/v1/service-centers/{sc_id}")
                if sc_resp.status_code == 200:
                    sc = sc_resp.json() or {}
                    service_centers_by_id[int(sc_id)] = sc

                    tg_id = sc.get("telegram_id")
                    if tg_id is not None:
                        offer_sc_telegram_ids[int(sc_id)] = int(tg_id)
            except Exception:
                continue

    templates = get_templates()
    return templates.TemplateResponse(
        "user/request_detail.html",
        {
            "request": request,
            "request_obj": req_data,
            "req": req_data,
            "car": car,
            "can_distribute": can_distribute,
            "sent_all": sent_all,
            "chosen_service_id": chosen_service_id,
            "offers": offers,
            "offer_sc_telegram_ids": offer_sc_telegram_ids,
            "service_centers_by_id": service_centers_by_id,
            "accepted_offer_id": accepted_offer_id,
            "accepted_sc_id": accepted_sc_id,
            "bot_username": bot_username,
        },
    )


# --------------------------------------------------------------------
# Страница заявки (детальная) /me/requests/{id}/view
# --------------------------------------------------------------------


@router.post("/requests/{request_id}/offers/{offer_id}/accept", response_class=HTMLResponse)
async def request_accept_offer(
    request_id: int,
    offer_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    _ = get_current_user_id(request)

    try:
        resp = await client.post(f"/api/v1/offers/{offer_id}/accept-by-client")
        resp.raise_for_status()
    except Exception:
        # ✅ не делаем silent-pass и не возвращаем “как ни в чём не бывало”
        # просто оставим на странице (можно потом красиво отрисовать баннер ошибки)
        return await request_detail(request_id, request, client)

    # ✅ Важно: редирект, чтобы не было повторной отправки формы при обновлении
    return RedirectResponse(
        url=f"/me/requests/{request_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# --------------------------------------------------------------------
# Отклонить предложение
# --------------------------------------------------------------------


@router.post("/requests/{request_id}/offers/{offer_id}/reject", response_class=HTMLResponse)
async def request_reject_offer(
    request_id: int,
    offer_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    _ = get_current_user_id(request)

    try:
        resp = await client.post(f"/api/v1/offers/{offer_id}/reject-by-client")
        resp.raise_for_status()
    except Exception:
        # reject не критичен — просто вернём страницу
        return await request_detail(request_id, request, client)

    return RedirectResponse(
        url=f"/me/requests/{request_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# --------------------------------------------------------------------
# Отправить всем подходящим СТО
# --------------------------------------------------------------------


@router.post("/requests/{request_id}/send-to-all", response_class=HTMLResponse)
@router.post("/requests/{request_id}/send-all", response_class=HTMLResponse)
async def request_send_all_post(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    _ = get_current_user_id(request)
    templates = get_templates()

    # 1) пробуем отправить всем
    error_message: str | None = None
    try:
        resp = await client.post(f"/api/v1/requests/{request_id}/send_to_all")
        if resp.status_code >= 400:
            # пытаемся вытащить detail из backend
            try:
                data = resp.json() or {}
                if isinstance(data, dict) and data.get("detail"):
                    error_message = str(data.get("detail"))
                else:
                    error_message = "Не удалось отправить заявку всем СТО. Проверьте геолокацию и радиус."
            except Exception:
                error_message = "Не удалось отправить заявку всем СТО. Проверьте геолокацию и радиус."
        else:
            # ок — покажем страницу заявки с sent_all=True
            return await request_detail(request_id, request, client, sent_all=True)
    except Exception:
        error_message = "Не удалось отправить заявку всем СТО. Попробуйте позже."

    # 2) ошибка — остаёмся на choose-service и показываем причину
    # Подтянем координаты заявки (для distance/maps)
    req_data: dict[str, Any] = {}
    try:
        r = await client.get(f"/api/v1/requests/{request_id}")
        if r.status_code == 200:
            req_data = r.json() or {}
    except Exception:
        req_data = {}

    request_lat = req_data.get("latitude") if isinstance(req_data, dict) else None
    request_lon = req_data.get("longitude") if isinstance(req_data, dict) else None

    service_centers: list[dict[str, Any]] = []
    try:
        sc_resp = await client.get(f"/api/v1/service-centers/for-request/{request_id}")
        if sc_resp.status_code == 200:
            raw = sc_resp.json() or []
            if isinstance(raw, list):
                service_centers = raw
    except Exception:
        service_centers = []

    service_centers = _enrich_service_centers_with_distance_and_maps(
        request_lat=request_lat,
        request_lon=request_lon,
        service_centers=service_centers,
    )

    return templates.TemplateResponse(
        "user/request_choose_service.html",
        {
            "request": request,
            "request_id": request_id,
            "service_centers": service_centers,
            "error_message": error_message,
            "bot_username": BOT_USERNAME,
        },
    )


# --------------------------------------------------------------------
# Страница выбора СТО
# --------------------------------------------------------------------


@router.get("/requests/{request_id}/choose-service", response_class=HTMLResponse)
async def choose_service_get(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    _ = get_current_user_id(request)
    templates = get_templates()

    error_message: str | None = None

    # Проверяем, что заявка существует + берём её координаты/радиус
    req_data: dict[str, Any] | None = None
    try:
        r = await client.get(f"/api/v1/requests/{request_id}")
        r.raise_for_status()
        req_data = r.json() or {}
    except Exception:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    request_lat = req_data.get("latitude") if isinstance(req_data, dict) else None
    request_lon = req_data.get("longitude") if isinstance(req_data, dict) else None
    radius_km = req_data.get("radius_km") if isinstance(req_data, dict) else None

    # ✅ Если гео/радиуса нет — не дергаем backend-ручку for-request, сразу показываем понятное сообщение
    if request_lat is None or request_lon is None:
        error_message = "📍 В заявке не указана геолокация. Вернитесь назад и нажмите «Определить моё местоположение»."
        service_centers: list[dict[str, Any]] = []
        return templates.TemplateResponse(
            "user/request_choose_service.html",
            {
                "request": request,
                "request_id": request_id,
                "service_centers": service_centers,
                "error_message": error_message,
                "bot_username": BOT_USERNAME,
            },
        )

    if radius_km is None or (isinstance(radius_km, (int, float)) and radius_km <= 0):
        error_message = "Нужно выбрать радиус поиска, чтобы показать подходящие СТО."
        service_centers = []
        return templates.TemplateResponse(
            "user/request_choose_service.html",
            {
                "request": request,
                "request_id": request_id,
                "service_centers": service_centers,
                "error_message": error_message,
                "bot_username": BOT_USERNAME,
            },
        )

    # ✅ Берём подходящие СТО по заявке
    service_centers: list[dict[str, Any]] = []
    try:
        sc_resp = await client.get(f"/api/v1/service-centers/for-request/{request_id}")

        if sc_resp.status_code == 400:
            # покажем detail с backend (например: нет гео/радиуса или нет СТО)
            try:
                detail = (sc_resp.json() or {}).get("detail")
            except Exception:
                detail = None
            error_message = detail or "Не удалось загрузить список подходящих СТО."
            service_centers = []
        else:
            sc_resp.raise_for_status()
            service_centers = sc_resp.json() or []
            if not isinstance(service_centers, list):
                service_centers = []

    except Exception:
        error_message = "Не удалось загрузить список подходящих СТО."
        service_centers = []

    # ✅ добавляем distance_km + maps_url
    service_centers = _enrich_service_centers_with_distance_and_maps(
        request_lat=request_lat,
        request_lon=request_lon,
        service_centers=service_centers,
    )

    # если список пустой, но ошибки нет — покажем полезное сообщение
    if not service_centers and not error_message:
        error_message = "В выбранном радиусе нет подходящих СТО. Попробуйте увеличить радиус или сменить категорию."

    return templates.TemplateResponse(
        "user/request_choose_service.html",
        {
            "request": request,
            "request_id": request_id,
            "service_centers": service_centers,
            "error_message": error_message,
            "bot_username": BOT_USERNAME,
        },
    )


# --------------------------------------------------------------------
# Отправить конкретному СТО
# --------------------------------------------------------------------


@router.post("/requests/{request_id}/send-to-service", response_class=HTMLResponse)
async def request_send_to_service_post(
    request_id: int,
    request: Request,
    service_center_id: int = Form(...),
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    _ = get_current_user_id(request)

    try:
        resp = await client.post(
            f"/api/v1/requests/{request_id}/send_to_service_center",
            json={"service_center_id": service_center_id},
        )
        resp.raise_for_status()
    except Exception:
        return await request_detail(
            request_id, request, client, chosen_service_id=None,
        )

    return await request_detail(
        request_id, request, client, chosen_service_id=service_center_id,
    )


@router.post("/requests/{request_id}/send-chat-link", response_class=JSONResponse)
async def user_send_chat_link(
    request_id: int,
    request: Request,
    service_center_id: int = Query(...),
    client: AsyncClient = Depends(get_backend_client),
) -> JSONResponse:
    _ = get_current_user_id(request)

    await client.post(
        f"/api/v1/requests/{request_id}/send_chat_link",
        json={"service_center_id": service_center_id, "recipient": "client"},
    )
    return JSONResponse({"ok": True})
