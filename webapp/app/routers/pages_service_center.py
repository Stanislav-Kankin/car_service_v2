from typing import Any
import os

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from httpx import AsyncClient

from ..dependencies import get_templates
from ..api_client import get_backend_client

router = APIRouter(
    prefix="/sc",
    tags=["service_center"],
)

templates = get_templates()

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")


def get_current_user_id(request: Request) -> int:
    """
    Берём user_id из request.state.user_id, который кладёт middleware.
    Все маршруты кабинета СТО требуют авторизации.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не авторизован",
        )
    return int(user_id)


# ---------------------------------------------------------------------------
# DASHBOARD СТО
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def sc_dashboard(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Кабинет СТО: список сервисов, привязанных к пользователю.
    """
    user_id = get_current_user_id(request)

    service_centers: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get(f"/api/v1/service-centers/by-user/{user_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            service_centers = []
        else:
            resp.raise_for_status()
            service_centers = resp.json()
    except Exception:
        error_message = "Не удалось загрузить список ваших СТО. Попробуйте позже."
        service_centers = []

    # Подтягиваем баланс кошелька по каждой СТО (best-effort)
    if service_centers:
        for sc in service_centers:
            try:
                sc_id = sc.get("id")
                if not sc_id:
                    continue
                w = await client.get(f"/api/v1/service-centers/{sc_id}/wallet")
                if w.status_code == 200 and isinstance(w.json(), dict):
                    sc["wallet_balance"] = w.json().get("balance", 0)
                else:
                    sc["wallet_balance"] = None
            except Exception:
                sc["wallet_balance"] = None

    return templates.TemplateResponse(
        "service_center/dashboard.html",
        {
            "request": request,
            "service_centers": service_centers,
            "error_message": error_message,
        },
    )


# ---------------------------------------------------------------------------
# СОЗДАНИЕ НОВОГО СТО
# ---------------------------------------------------------------------------

@router.get("/create", response_class=HTMLResponse)
async def sc_create_get(
    request: Request,
) -> HTMLResponse:
    _ = get_current_user_id(request)

    specialization_options = [
        ("wash", "Автомойка"),
        ("tire", "Шиномонтаж"),
        ("electric", "Автоэлектрик"),
        ("mechanic", "Слесарные работы"),
        ("paint", "Кузовные/покраска"),
        ("maint", "ТО/обслуживание"),
        ("agg_turbo", "Турбины"),
        ("agg_starter", "Стартеры"),
        ("agg_generator", "Генераторы"),
        ("agg_steering", "Рулевые рейки"),
    ]

    return templates.TemplateResponse(
        "service_center/create.html",
        {
            "request": request,
            "error_message": None,
            "specialization_options": specialization_options,
        },
    )


@router.post("/create", response_class=HTMLResponse)
async def sc_create_post(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    name: str = Form(...),
    address: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    org_type: str = Form("company"),
    is_mobile_service: bool = Form(False),
    has_tow_truck: bool = Form(False),
    specializations: list[str] = Form(default_factory=list),
) -> HTMLResponse:
    user_id = get_current_user_id(request)

    specializations = [s.strip() for s in (specializations or []) if s and s.strip()]
    if not specializations:
        specialization_options = [
            ("wash", "Автомойка"),
            ("tire", "Шиномонтаж"),
            ("electric", "Автоэлектрик"),
            ("mechanic", "Слесарные работы"),
            ("paint", "Кузовные/покраска"),
            ("maint", "ТО/обслуживание"),
            ("agg_turbo", "Турбины"),
            ("agg_starter", "Стартеры"),
            ("agg_generator", "Генераторы"),
            ("agg_steering", "Рулевые рейки"),
        ]
        return templates.TemplateResponse(
            "service_center/create.html",
            {
                "request": request,
                "error_message": "Выберите минимум одну специализацию.",
                "specialization_options": specialization_options,
            },
        )

    payload = {
        "user_id": user_id,
        "name": name,
        "address": address or None,
        "phone": phone or None,
        "website": website or None,
        "org_type": org_type or None,
        "is_mobile_service": bool(is_mobile_service),
        "has_tow_truck": bool(has_tow_truck),
        "specializations": specializations,
    }

    try:
        resp = await client.post("/api/v1/service-centers/", json=payload, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        specialization_options = [
            ("wash", "Автомойка"),
            ("tire", "Шиномонтаж"),
            ("electric", "Автоэлектрик"),
            ("mechanic", "Слесарные работы"),
            ("paint", "Кузовные/покраска"),
            ("maint", "ТО/обслуживание"),
            ("agg_turbo", "Турбины"),
            ("agg_starter", "Стартеры"),
            ("agg_generator", "Генераторы"),
            ("agg_steering", "Рулевые рейки"),
        ]
        return templates.TemplateResponse(
            "service_center/create.html",
            {
                "request": request,
                "error_message": "Не удалось создать СТО. Проверьте данные и попробуйте ещё раз.",
                "specialization_options": specialization_options,
            },
        )

    return RedirectResponse(
        url="/sc/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНОЕ: загрузить СТО и проверить принадлежность
# ---------------------------------------------------------------------------

async def _load_sc_for_owner(
    request: Request,
    client: AsyncClient,
    sc_id: int,
) -> dict[str, Any]:
    """
    Загрузить СТО и проверить, что он принадлежит текущему пользователю.
    """
    user_id = get_current_user_id(request)

    try:
        resp = await client.get(f"/api/v1/service-centers/{sc_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Сервис не найден")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Ошибка backend при загрузке СТО")

    sc = resp.json()
    if sc.get("user_id") != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому сервису")

    return sc


# ---------------------------------------------------------------------------
# ПРОСМОТР / РЕДАКТИРОВАНИЕ ПРОФИЛЯ СТО
# ---------------------------------------------------------------------------

@router.get("/edit/{sc_id}", response_class=HTMLResponse)
async def sc_edit_get(
    sc_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Форма редактирования профиля СТО.
    """
    sc = await _load_sc_for_owner(request, client, sc_id)

    specialization_options = [
        ("wash", "Автомойка"),
        ("tire", "Шиномонтаж"),
        ("electric", "Автоэлектрик"),
        ("mechanic", "Слесарные работы"),
        ("paint", "Малярные / кузовные работы"),
        ("maint", "ТО / обслуживание"),
        ("agg_turbo", "Ремонт турбин"),
        ("agg_starter", "Ремонт стартеров"),
        ("agg_generator", "Ремонт генераторов"),
        ("agg_steering", "Рулевые рейки"),
    ]

    return templates.TemplateResponse(
        "service_center/edit.html",
        {
            "request": request,
            "service_center": sc,
            "error_message": None,
            "success": False,
            "specialization_options": specialization_options,
        },
    )


@router.post("/edit/{sc_id}", response_class=HTMLResponse)
async def sc_edit_post(
    sc_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    name: str = Form(...),
    address: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    org_type: str = Form("company"),
    specializations: list[str] = Form([]),
    is_mobile_service: bool = Form(False),
    has_tow_truck: bool = Form(False),
    is_active: bool = Form(True),
) -> HTMLResponse:
    """
    Обработка формы редактирования СТО.
    """
    _ = get_current_user_id(request)

    specialization_options = [
        ("wash", "Автомойка"),
        ("tire", "Шиномонтаж"),
        ("electric", "Автоэлектрик"),
        ("mechanic", "Слесарные работы"),
        ("paint", "Малярные / кузовные работы"),
        ("maint", "ТО / обслуживание"),
        ("agg_turbo", "Ремонт турбин"),
        ("agg_starter", "Ремонт стартеров"),
        ("agg_generator", "Ремонт генераторов"),
        ("agg_steering", "Рулевые рейки"),
    ]

    specs_clean = [s for s in (specializations or []) if s]
    if not specs_clean:
        sc = await _load_sc_for_owner(request, client, sc_id)
        return templates.TemplateResponse(
            "service_center/edit.html",
            {
                "request": request,
                "service_center": sc,
                "error_message": "Выберите минимум одну специализацию.",
                "success": False,
                "specialization_options": specialization_options,
            },
        )

    payload: dict[str, Any] = {
        "name": name,
        "address": address or None,
        "phone": phone or None,
        "website": website or None,
        "org_type": org_type or None,
        "specializations": specs_clean,
        "is_mobile_service": bool(is_mobile_service),
        "has_tow_truck": bool(has_tow_truck),
        "is_active": bool(is_active),
    }

    error_message: str | None = None
    sc: dict[str, Any] | None = None
    success = False

    try:
        resp = await client.patch(f"/api/v1/service-centers/{sc_id}", json=payload)
        resp.raise_for_status()
        sc = resp.json()
        success = True
    except Exception:
        error_message = "Не удалось сохранить изменения. Попробуйте позже."
        try:
            sc = await _load_sc_for_owner(request, client, sc_id)
        except HTTPException:
            raise

    return templates.TemplateResponse(
        "service_center/edit.html",
        {
            "request": request,
            "service_center": sc,
            "error_message": error_message,
            "success": success,
            "specialization_options": specialization_options,
        },
    )


# ---------------------------------------------------------------------------
# СПИСОК ЗАЯВОК ДЛЯ КОНКРЕТНОГО СТО
# ---------------------------------------------------------------------------

@router.get("/{sc_id}/requests", response_class=HTMLResponse)
async def sc_requests_list(
    sc_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Список заявок, которые были разосланы КОНКРЕТНОМУ СТО.
    """
    sc = await _load_sc_for_owner(request, client, sc_id)

    requests_list: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get(f"/api/v1/requests/for-service-center/{sc_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            requests_list = []
        else:
            resp.raise_for_status()
            requests_list = resp.json()
    except Exception:
        error_message = "Не удалось загрузить заявки для этого сервиса. Попробуйте позже."
        requests_list = []

    return templates.TemplateResponse(
        "service_center/requests.html",
        {
            "request": request,
            "service_center": sc,
            "requests_list": requests_list,
            "error_message": error_message,
        },
    )


# ---------------------------------------------------------------------------
# ДЕТАЛЬНАЯ ЗАЯВКА + ОТКЛИК СТО
# ---------------------------------------------------------------------------

@router.get("/{sc_id}/requests/{request_id}", response_class=HTMLResponse)
async def sc_request_detail(
    sc_id: int,
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    _ = get_current_user_id(request)
    templates = get_templates()

    error_message = None

    # service center (и ownership)
    sc = await _load_sc_for_owner(request, client, sc_id)

    # request
    try:
        r = await client.get(f"/api/v1/requests/{request_id}")
        r.raise_for_status()
        request_data = r.json()
    except Exception:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    # car (optional)
    try:
        car_id = request_data.get("car_id")
        if car_id:
            car_resp = await client.get(f"/api/v1/cars/{int(car_id)}")
            if car_resp.status_code == 200:
                request_data["car"] = car_resp.json()
            else:
                request_data["car"] = None
    except Exception:
        request_data["car"] = None

    # client telegram_id (owner of request) — нужно для "Написать в Telegram"
    client_telegram_id: int | None = None
    try:
        client_user_id = request_data.get("user_id")
        if client_user_id:
            u = await client.get(f"/api/v1/users/{int(client_user_id)}")
            if u.status_code == 200:
                user_data = u.json() or {}
                tg_id = user_data.get("telegram_id")
                if tg_id is not None:
                    client_telegram_id = int(tg_id)
    except Exception:
        client_telegram_id = None

    # offers for request (backend отдаёт все офферы — мы НЕ показываем их СТО)
    offers: list[dict[str, Any]] = []
    try:
        offers_resp = await client.get(f"/api/v1/offers/by-request/{request_id}")
        if offers_resp.status_code == 200:
            offers = offers_resp.json() or []
    except Exception:
        offers = []

    # my offer for this service
    my_offer: dict[str, Any] | None = None
    try:
        for o in offers:
            if o.get("service_center_id") == sc_id:
                my_offer = o
                break
    except Exception:
        my_offer = None

    # ✅ Критично: СТО не должно видеть чужие отклики
    offers_for_view: list[dict[str, Any]] = [my_offer] if my_offer else []

    return templates.TemplateResponse(
        "service_center/request_detail.html",
        {
            "request": request,
            "service_center": sc,
            "req": request_data,
            "offers": offers_for_view,  # <-- теперь только свой
            "my_offer": my_offer,
            "error_message": error_message,
            "bot_username": BOT_USERNAME,
            "client_telegram_id": client_telegram_id,
        },
    )


@router.post("/{sc_id}/requests/{request_id}/offer", response_class=HTMLResponse)
async def sc_offer_submit(
    sc_id: int,
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    price: float = Form(...),
    eta_hours: int = Form(...),
    comment: str = Form(""),
) -> HTMLResponse:
    sc = await _load_sc_for_owner(request, client, sc_id)

    # Запрет отклика, если заявка уже в работе/закрыта
    try:
        req_resp = await client.get(f"/api/v1/requests/{request_id}")
        if req_resp.status_code == 200:
            status_ = (req_resp.json() or {}).get("status")
            if status_ in ("in_work", "done", "cancelled"):
                return RedirectResponse(
                    url=f"/sc/{sc_id}/requests/{request_id}?err=offer_locked",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
    except Exception:
        # если не удалось проверить статус — не блокируем, просто пробуем сохранить как раньше
        pass

    # ищем существующий оффер (если есть) — чтобы обновлять, а не плодить
    my_offer: dict[str, Any] | None = None
    try:
        offers_resp = await client.get(f"/api/v1/offers/by-request/{request_id}")
        if offers_resp.status_code == 200:
            offers = offers_resp.json() or []
            for o in offers:
                if o.get("service_center_id") == sc_id:
                    my_offer = o
                    break
    except Exception:
        my_offer = None

    payload: dict[str, Any] = {
        "request_id": request_id,
        "service_center_id": sc_id,
        "price": price,
        "eta_hours": eta_hours,
        "comment": comment or None,
    }

    try:
        if my_offer:
            offer_id = my_offer["id"]
            resp = await client.patch(f"/api/v1/offers/{offer_id}", json=payload)
            resp.raise_for_status()
        else:
            resp = await client.post("/api/v1/offers/", json=payload)
            resp.raise_for_status()
    except Exception:
        return templates.TemplateResponse(
            "service_center/request_detail.html",
            {
                "request": request,
                "service_center": sc,
                "req": None,
                "offers": [],
                "my_offer": None,
                "error_message": "Не удалось сохранить отклик. Попробуйте позже.",
                "bot_username": BOT_USERNAME,
                "client_telegram_id": None,
            },
        )

    return RedirectResponse(
        url=f"/sc/{sc_id}/requests/{request_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{sc_id}/requests/{request_id}/set-in-work", response_class=HTMLResponse)
async def sc_set_in_work(
    sc_id: int,
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    _ = await _load_sc_for_owner(request, client, sc_id)

    try:
        resp = await client.post(
            f"/api/v1/requests/{request_id}/set_in_work",
            json={"service_center_id": sc_id},
        )
        resp.raise_for_status()
    except Exception:
        return RedirectResponse(
            url=f"/sc/{sc_id}/requests/{request_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/sc/{sc_id}/requests/{request_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{sc_id}/requests/{request_id}/set-done", response_class=HTMLResponse)
async def sc_set_done(
    sc_id: int,
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    final_price: float = Form(...),
) -> HTMLResponse:
    _ = await _load_sc_for_owner(request, client, sc_id)

    try:
        resp = await client.post(
            f"/api/v1/requests/{request_id}/set_done",
            json={"service_center_id": sc_id, "final_price": final_price},
        )
        resp.raise_for_status()
    except Exception:
        return RedirectResponse(
            url=f"/sc/{sc_id}/requests/{request_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/sc/{sc_id}/requests/{request_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{sc_id}/requests/{request_id}/reject", response_class=HTMLResponse)
async def sc_reject(
    sc_id: int,
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    reason: str = Form(""),
) -> HTMLResponse:
    _ = await _load_sc_for_owner(request, client, sc_id)

    try:
        resp = await client.post(
            f"/api/v1/requests/{request_id}/reject_by_service",
            json={"service_center_id": sc_id, "reason": reason or None},
        )
        resp.raise_for_status()
    except Exception:
        return RedirectResponse(
            url=f"/sc/{sc_id}/requests/{request_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/sc/{sc_id}/requests/{request_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{sc_id}/requests/{request_id}/send-chat-link", response_class=JSONResponse)
async def sc_send_chat_link(
    sc_id: int,
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> JSONResponse:
    _ = get_current_user_id(request)

    await client.post(
        f"/api/v1/requests/{request_id}/send_chat_link",
        json={"service_center_id": sc_id, "recipient": "service_center"},
    )
    return JSONResponse({"ok": True})
