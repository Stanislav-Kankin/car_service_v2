from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from httpx import AsyncClient

from ..api_client import get_backend_client
from ..dependencies import get_templates

router = APIRouter(
   prefix="/me",
   tags=["user"],
)

templates = get_templates()

FAKE_CURRENT_USER_ID = 1


# ---------------------------------------------------------------------------
# Личный кабинет
# ---------------------------------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "user/dashboard.html",
        {
            "request": request,
        },
    )


# ---------------------------------------------------------------------------
# Гараж
# ---------------------------------------------------------------------------
@router.get("/garage", response_class=HTMLResponse)
async def user_garage(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    user_id = FAKE_CURRENT_USER_ID

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
        {
            "request": request,
            "cars": cars,
            "error_message": error_message,
        },
    )


# ---------------------------------------------------------------------------
# Карточка машины
# ---------------------------------------------------------------------------
@router.get("/cars/{car_id}", response_class=HTMLResponse)
async def car_detail(
    car_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    try:
        resp = await client.get(f"/api/v1/cars/{car_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Автомобиль не найден",
            )
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ошибка при обращении к backend-сервису",
        ) from exc

    car = resp.json()

    return templates.TemplateResponse(
        "user/car_detail.html",
        {
            "request": request,
            "car": car,
        },
    )


# ---------------------------------------------------------------------------
# Мои заявки: список
# ---------------------------------------------------------------------------
@router.get("/requests", response_class=HTMLResponse)
async def requests_list(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    user_id = FAKE_CURRENT_USER_ID

    requests_data: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get(f"/api/v1/requests/by-user/{user_id}")
        if resp.status_code == 404:
            requests_data = []
        else:
            resp.raise_for_status()
            requests_data = resp.json()
    except Exception:
        error_message = "Не удалось загрузить список заявок. Попробуйте позже."
        requests_data = []

    status_labels = {
        "new": "Новая",
        "sent": "Отправлена СТО",
        "accepted_by_service": "Принята сервисом",
        "in_work": "В работе",
        "done": "Завершена",
        "cancelled": "Отменена",
        "rejected_by_service": "Отклонена СТО",
    }

    for r in requests_data:
        code = r.get("status")
        r["status_label"] = status_labels.get(code, code)
        cat = r.get("service_category") or ""
        if cat == "sto":
            r["service_category_label"] = "СТО"
        else:
            r["service_category_label"] = cat or "Услуга"

    return templates.TemplateResponse(
        "user/request_list.html",
        {
            "request": request,
            "requests": requests_data,
            "error_message": error_message,
        },
    )


# ---------------------------------------------------------------------------
# СОЗДАНИЕ ЗАЯВКИ (ВАЖНО: СТАВИМ ДО /requests/{request_id})
# ---------------------------------------------------------------------------
@router.get("/requests/create", response_class=HTMLResponse)
async def request_create_get(
    request: Request,
    car_id: int | None = None,
) -> HTMLResponse:
    """
    Форма создания новой заявки.
    """
    return templates.TemplateResponse(
        "user/request_create.html",
        {
            "request": request,
            "car_id": car_id,
            "created_request": None,
            "error_message": None,
        },
    )


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
    """
    Обработка формы создания заявки.
    """
    user_id = FAKE_CURRENT_USER_ID

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

    created_request: dict[str, Any] | None = None
    error_message: str | None = None

    try:
        resp = await client.post("/api/v1/requests/", json=payload)
        resp.raise_for_status()
        created_request = resp.json()
    except Exception:
        error_message = "Не удалось создать заявку. Попробуйте позже."

    return templates.TemplateResponse(
        "user/request_create.html",
        {
            "request": request,
            "car_id": car_id,
            "created_request": created_request,
            "error_message": error_message,
        },
    )


# ---------------------------------------------------------------------------
# Детали заявки
# ---------------------------------------------------------------------------
@router.get("/requests/{request_id}", response_class=HTMLResponse)
async def request_detail(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    sent_all: bool | None = None,
    chosen_service_id: int | None = None,
) -> HTMLResponse:
    """
    Детальная страница заявки + список откликов СТО.
    """
    # --- 1. Тянем саму заявку ---
    try:
        resp = await client.get(f"/api/v1/requests/{request_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Заявка не найдена",
            )
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ошибка при обращении к backend-сервису",
        ) from exc

    req_data = resp.json()

    # Читабельный статус
    status_labels = {
        "new": "Новая",
        "sent": "Отправлена СТО",
        "accepted_by_service": "Принята сервисом",
        "in_work": "В работе",
        "done": "Завершена",
        "cancelled": "Отменена",
        "rejected_by_service": "Отклонена СТО",
    }
    code = req_data.get("status")
    req_data["status_label"] = status_labels.get(code, code)

    # Читабельная категория
    cat = req_data.get("service_category") or ""
    if cat == "sto":
        req_data["service_category_label"] = "СТО"
    else:
        req_data["service_category_label"] = cat or "Услуга"

    can_distribute = req_data.get("status") == "new"

    # --- 2. Тянем отклики по заявке ---
    offers: list[dict[str, Any]] = []
    try:
        # ЕСЛИ путь другой — поменяешь тут:
        resp_offers = await client.get(
            f"/api/v1/offers/by-request/{request_id}"
        )
        if resp_offers.status_code == status.HTTP_200_OK:
            offers = resp_offers.json()
        elif resp_offers.status_code == status.HTTP_404_NOT_FOUND:
            offers = []
        else:
            # если что-то ещё — считаем, что нет откликов
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

@router.post(
    "/requests/{request_id}/offers/{offer_id}/accept",
    response_class=HTMLResponse,
)
async def request_accept_offer(
    request_id: int,
    offer_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Клиент принимает предложение СТО.
    """
    try:
        # ЕСЛИ путь другой — поменяешь здесь:
        resp = await client.post(
            f"/api/v1/offers/{offer_id}/accept-by-client"
        )
        resp.raise_for_status()
    except Exception:
        # даже если упали, просто перерисуем страницу заявки
        return await request_detail(
            request_id=request_id,
            request=request,
            client=client,
        )

    # после принятия перерисовываем заявку (статусы/отклики обновятся)
    return await request_detail(
        request_id=request_id,
        request=request,
        client=client,
    )


@router.post(
    "/requests/{request_id}/offers/{offer_id}/reject",
    response_class=HTMLResponse,
)
async def request_reject_offer(
    request_id: int,
    offer_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Клиент отклоняет предложение СТО.
    """
    try:
        # ЕСЛИ путь другой — поменяешь здесь:
        resp = await client.post(
            f"/api/v1/offers/{offer_id}/reject-by-client"
        )
        resp.raise_for_status()
    except Exception:
        return await request_detail(
            request_id=request_id,
            request=request,
            client=client,
        )

    return await request_detail(
        request_id=request_id,
        request=request,
        client=client,
    )


# ---------------------------------------------------------------------------
# Отправить заявку всем подходящим СТО
# ---------------------------------------------------------------------------
@router.post("/requests/{request_id}/send-all", response_class=HTMLResponse)
async def request_send_all_post(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Отправка заявки всем подходящим СТО.
    """
    try:
        resp = await client.post(f"/api/v1/requests/{request_id}/send_to_all")
        resp.raise_for_status()
    except Exception:
        return await request_detail(
            request_id=request_id,
            request=request,
            client=client,
            sent_all=False,
        )

    return await request_detail(
        request_id=request_id,
        request=request,
        client=client,
        sent_all=True,
    )


# ---------------------------------------------------------------------------
# Выбор СТО из списка
# ---------------------------------------------------------------------------
@router.get("/requests/{request_id}/choose-service", response_class=HTMLResponse)
async def request_choose_service_get(
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Страница выбора конкретного СТО для заявки.
    """
    service_centers: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get(f"/api/v1/service-centers/for-request/{request_id}")
        resp.raise_for_status()
        service_centers = resp.json()
    except Exception:
        error_message = "Не удалось загрузить список подходящих СТО. Попробуйте позже."
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


@router.post("/requests/{request_id}/send-to-service", response_class=HTMLResponse)
async def request_send_to_service_post(
    request_id: int,
    request: Request,
    service_center_id: int = Form(...),
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Отправка заявки выбранному СТО.
    """
    try:
        resp = await client.post(
            f"/api/v1/requests/{request_id}/send_to_service_center",
            json={"service_center_id": service_center_id},
        )
        resp.raise_for_status()
    except Exception:
        return await request_detail(
           request_id=request_id,
           request=request,
           client=client,
           chosen_service_id=None,
        )

    return await request_detail(
        request_id=request_id,
        request=request,
        client=client,
        chosen_service_id=service_center_id,
    )
