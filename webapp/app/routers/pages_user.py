from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import HTMLResponse
from httpx import AsyncClient

from ..api_client import get_backend_client
from ..dependencies import get_templates

router = APIRouter(
    prefix="/me",
    tags=["user"],
)

templates = get_templates()


# ------------------------------------------------------------------------------
# Авторизация: ВСЕ маршруты /me/* требуют user_id в cookie
# ------------------------------------------------------------------------------

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


# ------------------------------------------------------------------------------
# Словарь категорий
# ------------------------------------------------------------------------------

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


# ------------------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request) -> HTMLResponse:
    _ = get_current_user_id(request)
    return templates.TemplateResponse(
        "user/dashboard.html",
        {"request": request},
    )


# ------------------------------------------------------------------------------
# Гараж
# ------------------------------------------------------------------------------

@router.get("/garage", response_class=HTMLResponse)
async def user_garage(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    user_id = get_current_user_id(request)

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


# ------------------------------------------------------------------------------
# Карточка машины
# ------------------------------------------------------------------------------

@router.get("/cars/{car_id}", response_class=HTMLResponse)
async def car_detail(
    car_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:

    _ = get_current_user_id(request)

    try:
        resp = await client.get(f"/api/v1/cars/{car_id}")
        if resp.status_code == 404:
            raise HTTPException(404, "Автомобиль не найден")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Ошибка backend при загрузке автомобиля")

    car = resp.json()

    return templates.TemplateResponse(
        "user/car_detail.html",
        {"request": request, "car": car},
    )


# ------------------------------------------------------------------------------
# Список заявок
# ------------------------------------------------------------------------------

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


# ------------------------------------------------------------------------------
# Создание заявки — GET
# ------------------------------------------------------------------------------

@router.get("/requests/create", response_class=HTMLResponse)
async def request_create_get(
    request: Request,
    car_id: int | None = None,
) -> HTMLResponse:

    _ = get_current_user_id(request)

    return templates.TemplateResponse(
        "user/request_create.html",
        {
            "request": request,
            "car_id": car_id,
            "created_request": None,
            "error_message": None,
        },
    )


# ------------------------------------------------------------------------------
# Создание заявки — POST
# ------------------------------------------------------------------------------

@router.post("/requests/create", response_class=HTMLResponse)
async def request_create_post(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    car_id: int = Form(...),
    address_text: str = Form(""),
    is_car_movable: str = Form("movable"),
    radius_km: int = Form(5),
    description: str = Form(...),
    hide_phone: bool = Form(False),
) -> HTMLResponse:

    user_id = get_current_user_id(request)

    movable = is_car_movable == "movable"
    need_tow_truck = not movable
    need_mobile_master = not movable

    payload = {
        "user_id": user_id,
        "car_id": car_id,
        "latitude": None,
        "longitude": None,
        "address_text": address_text or None,
        "is_car_movable": movable,
        "need_tow_truck": need_tow_truck,
        "need_mobile_master": need_mobile_master,
        "radius_km": radius_km,
        "service_category": "sto",
        "description": description,
        "photos": [],
        "hide_phone": hide_phone,
    }

    created_request = None
    error_message = None

    try:
        resp = await client.post("/api/v1/requests/", json=payload)
        resp.raise_for_status()
        created_request = resp.json()
    except Exception:
        error_message = "Не удалось создать заявку."

    return templates.TemplateResponse(
        "user/request_create.html",
        {
            "request": request,
            "car_id": car_id,
            "created_request": created_request,
            "error_message": error_message,
        },
    )


# ------------------------------------------------------------------------------
# Страница заявки
# ------------------------------------------------------------------------------

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

    # загрузка откликов
    offers = []
    try:
        resp2 = await client.get(f"/api/v1/offers/by-request/{request_id}")
        if resp2.status_code == 200:
            offers = resp2.json()
        else:
            offers = []
    except Exception:
        offers = []

    return templates.TemplateResponse(
        "user/request_detail.html",
        {
            "request": request,
            "request_obj": req_data,
            "can_distribute": can_distribute,
            "sent_all": sent_all,
            "chosen_service_id": chosen_service_id,
            "offers": offers,
        },
    )


# ------------------------------------------------------------------------------
# Принять предложение
# ------------------------------------------------------------------------------

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
        pass

    return await request_detail(request_id, request, client)


# ------------------------------------------------------------------------------
# Отклонить предложение
# ------------------------------------------------------------------------------

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
        pass

    return await request_detail(request_id, request, client)


# ------------------------------------------------------------------------------
# Отправить всем подходящим СТО
# ------------------------------------------------------------------------------

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


# ------------------------------------------------------------------------------
# Страница выбора СТО
# ------------------------------------------------------------------------------

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


# ------------------------------------------------------------------------------
# Отправить конкретному СТО
# ------------------------------------------------------------------------------

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
