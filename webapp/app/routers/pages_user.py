from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from httpx import AsyncClient

from ..api_client import get_backend_client
from ..dependencies import get_templates

router = APIRouter(
    prefix="/me",
    tags=["user"],
)

templates = get_templates()


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
    """ 
    /me/dashboard — единственная страница, которую мы допускаем БЕЗ cookie,
    чтобы Telegram Mini App мог загрузиться и выполнить JS auth.

    Важно: как только cookie есть, и профиль заполнен — показываем кабинет.
    Если cookie есть, но профиль НЕ заполнен — middleware уже редиректит на /me/register.
    """
    user_id = getattr(request.state, "user_id", None)

    # Без cookie: показываем только экран "Авторизация..." (без функциональных ссылок)
    if not user_id:
        return templates.TemplateResponse(
            "user/dashboard.html",
            {"request": request, "show_dashboard": False, "user": None},
        )

    # С cookie: user_obj мог быть загружен middleware, но на всякий случай подстрахуемся
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
    """
    Форма регистрации при первом входе.
    Требуем, чтобы уже был user_id cookie (его ставит Telegram WebApp auth JS).
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return RedirectResponse(url="/me/dashboard", status_code=status.HTTP_302_FOUND)

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
    if not user_id:
        return RedirectResponse(url="/me/dashboard", status_code=status.HTTP_302_FOUND)

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

    return templates.TemplateResponse(
        "user/garage.html",
        {"request": request, "cars": cars, "error_message": error_message},
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

    # Если ошибка валидации на фронте — не ходим в backend
    if error_message:
        car_data = {
            "brand": brand,
            "model": model,
            "year": year,
            "license_plate": license_plate,
            "vin": vin,
        }
        return templates.TemplateResponse(
            "user/car_form.html",
            {
                "request": request,
                "mode": "create",
                "car": car_data,
                "error_message": error_message,
            },
        )

    payload: dict[str, Any] = {
        "user_id": user_id,
        "brand": brand or None,
        "model": model or None,
        "year": year_value,
        "license_plate": license_plate or None,
        "vin": vin or None,
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
        }
        return templates.TemplateResponse(
            "user/car_form.html",
            {
                "request": request,
                "mode": "create",
                "car": car_data,
                "error_message": error_message,
            },
        )

    # Успешно — ведём в карточку машины
    return RedirectResponse(
        url=f"/me/cars/{car_created['id']}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


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

    car_data = {
        "id": car_id,
        "brand": brand,
        "model": model,
        "year": year,
        "license_plate": license_plate,
        "vin": vin,
    }

    if error_message:
        return templates.TemplateResponse(
            "user/car_form.html",
            {
                "request": request,
                "mode": "edit",
                "car": car_data,
                "error_message": error_message,
            },
        )

    payload: dict[str, Any] = {
        "brand": brand or None,
        "model": model or None,
        "year": year_value,
        "license_plate": license_plate or None,
        "vin": vin or None,
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
                "error_message": error_message,
            },
        )

    return RedirectResponse(
        url=f"/me/cars/{car_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


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
    _ = get_current_user_id(request)

    car: dict[str, Any] | None = None
    if car_id is not None:
        try:
            car = await _load_car_for_owner(request, client, car_id)
        except HTTPException:
            # если нет доступа/не найдена — пробрасываем дальше
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


# ------------------------------------------------------------------------------
# Создание заявки — POST (ИСПРАВЛЕННАЯ ВЕРСИЯ)
# ------------------------------------------------------------------------------

@router.post("/requests/create", response_class=HTMLResponse)
async def request_create_post(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),

    # — ключевое исправление — читаем car_id из формы —
    car_id_raw: str = Form("", alias="car_id"),

    address_text: str = Form(""),
    is_car_movable: str = Form("movable"),
    radius_km: int = Form(5),
    service_category: str = Form("sto"),
    description: str = Form(...),
    hide_phone: bool = Form(False),
) -> HTMLResponse:

    user_id = get_current_user_id(request)

    # -----------------------------------
    #  car_id: корректная валидация
    # -----------------------------------
    car_id_raw = (car_id_raw or "").strip()
    if not car_id_raw:
        return templates.TemplateResponse(
            "user/request_create.html",
            {
                "request": request,
                "car_id": None,
                "car": None,
                "created_request": None,
                "error_message": "Сначала выберите автомобиль в гараже, а потом создавайте заявку.",
                "primary_categories": _build_service_categories()[0],
                "extra_categories": _build_service_categories()[1],
                "form_data": {
                    "address_text": address_text,
                    "is_car_movable": is_car_movable,
                    "radius_km": radius_km,
                    "service_category": service_category,
                    "description": description,
                    "hide_phone": hide_phone,
                },
            },
        )

    try:
        car_id = int(car_id_raw)
    except ValueError:
        return templates.TemplateResponse(
            "user/request_create.html",
            {
                "request": request,
                "car_id": None,
                "car": None,
                "created_request": None,
                "error_message": "Некорректный идентификатор автомобиля.",
                "primary_categories": _build_service_categories()[0],
                "extra_categories": _build_service_categories()[1],
                "form_data": {},
            },
        )

    # -----------------------------------
    #   Подгружаем авто
    # -----------------------------------
    try:
        car_resp = await client.get(f"/api/v1/cars/{car_id}")
        car_resp.raise_for_status()
        car = car_resp.json()
    except Exception:
        car = None

    movable = is_car_movable == "movable"

    payload = {
        "user_id": user_id,
        "car_id": car_id,
        "latitude": None,
        "longitude": None,
        "address_text": address_text or None,
        "is_car_movable": movable,
        "need_tow_truck": not movable,
        "need_mobile_master": not movable,
        "radius_km": radius_km,
        "service_category": service_category,
        "description": description,
        "photos": [],
        "hide_phone": hide_phone,
    }

    # -----------------------------------
    #   Создание заявки
    # -----------------------------------
    form_data = {
        "address_text": address_text,
        "is_car_movable": is_car_movable,
        "radius_km": radius_km,
        "service_category": service_category,
        "description": description,
        "hide_phone": hide_phone,
    }

    try:
        resp = await client.post("/api/v1/requests/", json=payload)
        resp.raise_for_status()
        created_request = resp.json()
        error_message = None
    except Exception:
        created_request = None
        error_message = "Не удалось создать заявку. Попробуйте позже."

    primary_categories, extra_categories = _build_service_categories()

    return templates.TemplateResponse(
        "user/request_create.html",
        {
            "request": request,
            "car_id": car_id,
            "car": car,
            "created_request": created_request,
            "error_message": error_message,
            "primary_categories": primary_categories,
            "extra_categories": extra_categories,
            "form_data": form_data,
        },
    )


# --------------------------------------------------------------------
# Страница заявки (детальная) /me/requests/{id}/view
# --------------------------------------------------------------------


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
    req_data["service_category_label"] = SERVICE_CATEGORY_LABELS.get(cat, cat or "Услуга")

    can_distribute = req_data.get("status") == "new"

    # Загружаем авто для красивого блока в шапке
    car: dict[str, Any] | None = None
    car_id = req_data.get("car_id")
    if car_id:
        try:
            car = await _load_car_for_owner(request, client, car_id)
        except Exception:
            car = None

    # Загрузка откликов
    offers: list[dict[str, Any]] = []
    try:
        resp2 = await client.get(f"/api/v1/offers/by-request/{request_id}")
        if resp2.status_code == 200:
            offers = resp2.json()
        else:
            offers = []
    except Exception:
        offers = []

    # ✅ Новое: вычисляем выбранный оффер (если есть)
    accepted_offer_id: int | None = None
    accepted_sc_id: int | None = None
    for o in offers:
        if o.get("status") == "accepted":
            accepted_offer_id = o.get("id")
            accepted_sc_id = o.get("service_center_id")
            break

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
            "accepted_offer_id": accepted_offer_id,
            "accepted_sc_id": accepted_sc_id,
        },
    )


# --------------------------------------------------------------------
# Принять предложение
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


@router.post("/requests/{request_id}/send-all", response_class=HTMLResponse)
async def request_send_all_post(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    _ = get_current_user_id(request)

    try:
        resp = await client.post(f"/api/v1/requests/{request_id}/send_to_all")
        resp.raise_for_status()
    except Exception:
        return await request_detail(request_id, request, client, sent_all=False)

    return await request_detail(request_id, request, client, sent_all=True)


# --------------------------------------------------------------------
# Страница выбора СТО
# --------------------------------------------------------------------


@router.get("/requests/{request_id}/choose-service", response_class=HTMLResponse)
async def request_choose_service_get(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    _ = get_current_user_id(request)

    service_centers = []
    error_message = None

    try:
        resp = await client.get(f"/api/v1/service-centers/for-request/{request_id}")
        resp.raise_for_status()
        service_centers = resp.json()
    except Exception:
        error_message = "Не удалось загрузить список подходящих СТО."
        service_centers = []

    return templates.TemplateResponse(
        "user/request_choose_service.html",
        {
            "request": request,
            "request_id": request_id,
            "service_centers": service_centers,
            "error_message": error_message,
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
