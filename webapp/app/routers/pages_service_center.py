from typing import Any
import os

import asyncio
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status, Query
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
    Кабинет СТО: список сервисов, привязанных к пользователю
    + best-effort: баланс кошелька по каждой СТО
    + best-effort: статистика заявок по каждой СТО (для UI-плашек)
    """
    import asyncio
    from typing import Any

    user_id = get_current_user_id(request)

    service_centers: list[dict[str, Any]] = []
    error_message: str | None = None

    # 1) Список СТО пользователя
    try:
        resp = await client.get(f"/api/v1/service-centers/by-user/{user_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            service_centers = []
        else:
            resp.raise_for_status()
            data = resp.json()
            service_centers = data if isinstance(data, list) else []
    except Exception:
        error_message = "Не удалось загрузить список ваших СТО. Попробуйте позже."
        service_centers = []

    # 2) Баланс кошелька (best-effort)
    if service_centers:
        for sc in service_centers:
            sc["wallet_balance"] = None
            try:
                sc_id = sc.get("id")
                if not isinstance(sc_id, int):
                    continue

                w = await client.get(f"/api/v1/service-centers/{sc_id}/wallet")
                if w.status_code == 200:
                    w_data = w.json()
                    if isinstance(w_data, dict):
                        sc["wallet_balance"] = w_data.get("balance")
            except Exception:
                sc["wallet_balance"] = None

    # 3) Статистика заявок по каждой СТО (best-effort)
    sc_counters: dict[int, dict[str, int]] = {}

    async def _fetch_requests_for_sc(sc_id: int) -> list[dict[str, Any]]:
        try:
            r = await client.get(f"/api/v1/requests/for-service-center/{sc_id}")
            if r.status_code == status.HTTP_404_NOT_FOUND:
                return []
            if r.status_code != 200:
                return []
            data = r.json() or []
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def _has_my_offer(sc_id: int, request_id: int) -> bool:
        """
        True если по request_id есть оффер от данного sc_id.
        """
        try:
            r = await client.get(f"/api/v1/offers/by-request/{request_id}")
            if r.status_code != 200:
                return False
            offers = r.json() or []
            if not isinstance(offers, list):
                return False
            for o in offers:
                if isinstance(o, dict) and o.get("service_center_id") == sc_id:
                    return True
            return False
        except Exception:
            return False

    async def _build_counters(sc_id: int) -> dict[str, int]:
        reqs = await _fetch_requests_for_sc(sc_id)

        total = len(reqs)
        in_work = sum(1 for x in reqs if x.get("status") == "in_work")
        done = sum(1 for x in reqs if x.get("status") == "done")

        # "Без отклика": нет оффера от этого sc_id
        # Ограничим проверку первыми 50 заявками, чтобы не устроить N*requests нагрузку
        ids: list[int] = []
        for x in reqs:
            rid = x.get("id")
            if isinstance(rid, int):
                ids.append(rid)
            if len(ids) >= 50:
                break

        no_offer = 0
        if ids:
            tasks = [_has_my_offer(sc_id, rid) for rid in ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for ok in results:
                if isinstance(ok, Exception):
                    continue
                if ok is False:
                    no_offer += 1

        return {
            "total": int(total),
            "no_offer": int(no_offer),
            "in_work": int(in_work),
            "done": int(done),
        }

    if service_centers:
        sc_ids = [sc.get("id") for sc in service_centers if isinstance(sc.get("id"), int)]
        if sc_ids:
            results = await asyncio.gather(*[_build_counters(int(sc_id)) for sc_id in sc_ids], return_exceptions=True)
            for sc_id, res in zip(sc_ids, results):
                if isinstance(res, Exception):
                    sc_counters[int(sc_id)] = {"total": 0, "no_offer": 0, "in_work": 0, "done": 0}
                else:
                    sc_counters[int(sc_id)] = res

    return templates.TemplateResponse(
        "service_center/dashboard.html",
        {
            "request": request,
            "service_centers": service_centers,
            "error_message": error_message,
            "sc_counters": sc_counters,
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
    latitude: str = Form(""),
    longitude: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    org_type: str = Form("company"),
    specializations: list[str] = Form([]),
    is_mobile_service: bool = Form(False),
    has_tow_truck: bool = Form(False),
) -> HTMLResponse:
    user_id = get_current_user_id(request)
    address = (address or "").strip()

    if not address:
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
                "error_message": "Укажите адрес СТО (обязательное поле).",
                "specialization_options": specialization_options,
                "form_data": {
                    "name": name,
                    "address": "",
                    "latitude": latitude,
                    "longitude": longitude,
                    "phone": phone,
                    "website": website,
                    "org_type": org_type,
                    "is_mobile_service": bool(is_mobile_service),
                    "has_tow_truck": bool(has_tow_truck),
                    "specializations": specializations,
                },
            },
        )

    lat_value: float | None = None
    lon_value: float | None = None

    if (latitude or "").strip() and (longitude or "").strip():
        try:
            lat_value = float(latitude)
            lon_value = float(longitude)
        except ValueError:
            lat_value = None
            lon_value = None

    if lat_value is None or lon_value is None:
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
                "error_message": "Укажите геолокацию СТО (кнопка 📍) — без неё СТО не сможет участвовать в подборе.",
                "specialization_options": specialization_options,
                "form_data": {
                    "name": name,
                    "address": address,
                    "latitude": latitude,
                    "longitude": longitude,
                    "phone": phone,
                    "website": website,
                    "org_type": org_type,
                    "is_mobile_service": bool(is_mobile_service),
                    "has_tow_truck": bool(has_tow_truck),
                    "specializations": specializations,
                },
            },
        )

    specs_clean = [s for s in (specializations or []) if s]
    if not specs_clean:
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
                "form_data": {
                    "name": name,
                    "address": address,
                    "latitude": latitude,
                    "longitude": longitude,
                    "phone": phone,
                    "website": website,
                    "org_type": org_type,
                    "is_mobile_service": bool(is_mobile_service),
                    "has_tow_truck": bool(has_tow_truck),
                    "specializations": specializations,
                },
            },
        )

    payload: dict[str, Any] = {
        "user_id": user_id,  # ✅ ВАЖНО: backend ожидает user_id
        "name": name,
        "address": address or None,
        "latitude": lat_value,
        "longitude": lon_value,
        "phone": phone or None,
        "website": website or None,
        "org_type": org_type or None,
        "specializations": specs_clean,
        "is_mobile_service": bool(is_mobile_service),
        "has_tow_truck": bool(has_tow_truck),
        "is_active": False,  # новая СТО должна пройти модерацию
    }

    error_message: str | None = None
    success = False

    try:
        resp = await client.post("/api/v1/service-centers/", json=payload)
        resp.raise_for_status()
        success = True
    except Exception:
        error_message = "Не удалось отправить заявку на модерацию. Попробуйте позже."

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
            "success": success,
            "error_message": error_message,
            "specialization_options": specialization_options,
            "form_data": {
                "name": name,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "phone": phone,
                "website": website,
                "org_type": org_type,
                "is_mobile_service": bool(is_mobile_service),
                "has_tow_truck": bool(has_tow_truck),
                "specializations": specializations,
            },
        },
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
    latitude: str = Form(""),
    longitude: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    org_type: str = Form("company"),
    specializations: list[str] = Form([]),
    is_mobile_service: bool = Form(False),
    has_tow_truck: bool = Form(False),
    is_active: bool = Form(True),
) -> HTMLResponse:
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

    address = (address or "").strip()

    if not address:
        sc = await _load_sc_for_owner(request, client, sc_id)
        return templates.TemplateResponse(
            "service_center/edit.html",
            {
                "request": request,
                "service_center": sc,
                "error_message": "Укажите адрес СТО (обязательное поле).",
                "success": False,
                "specialization_options": specialization_options,
            },
        )

    lat_value: float | None = None
    lon_value: float | None = None

    if (latitude or "").strip() and (longitude or "").strip():
        try:
            lat_value = float(latitude)
            lon_value = float(longitude)
        except ValueError:
            lat_value = None
            lon_value = None

    if lat_value is None or lon_value is None:
        sc = await _load_sc_for_owner(request, client, sc_id)
        return templates.TemplateResponse(
            "service_center/edit.html",
            {
                "request": request,
                "service_center": sc,
                "error_message": "Укажите геолокацию СТО (кнопка 📍) — без неё СТО не сможет участвовать в подборе.",
                "success": False,
                "specialization_options": specialization_options,
            },
        )

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
        "latitude": lat_value,
        "longitude": lon_value,
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

    if sc is None:
        sc = await _load_sc_for_owner(request, client, sc_id)

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
    status_: str | None = Query(default=None, alias="status"),
    no_offer: int | None = Query(default=None),
) -> HTMLResponse:
    """
    Список заявок, которые были разосланы КОНКРЕТНОМУ СТО.
    + фильтры: ?status=in_work / ?status=done / ... , ?no_offer=1
    + best-effort подмешиваем мой отклик в каждую заявку (для UI "без отклика")
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

    async def _fetch_my_offer(req_id: int) -> dict[str, Any] | None:
        try:
            offers_resp = await client.get(f"/api/v1/offers/by-request/{req_id}")
            if offers_resp.status_code != 200:
                return None
            offers = offers_resp.json() or []
            for o in offers:
                if o.get("service_center_id") == sc_id:
                    return o
            return None
        except Exception:
            return None

    if requests_list:
        tasks = []
        ids = []
        for r in requests_list:
            rid = r.get("id")
            if isinstance(rid, int):
                ids.append(rid)
                tasks.append(_fetch_my_offer(rid))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            offers_by_id: dict[int, dict[str, Any] | None] = {}
            for rid, res in zip(ids, results):
                if isinstance(res, Exception):
                    offers_by_id[rid] = None
                else:
                    offers_by_id[rid] = res

            for r in requests_list:
                rid = r.get("id")
                if isinstance(rid, int):
                    r["my_offer"] = offers_by_id.get(rid)

    total = len(requests_list)
    cnt_no_offer = sum(1 for r in requests_list if not r.get("my_offer"))
    cnt_in_work = sum(1 for r in requests_list if (r.get("status") == "in_work"))
    cnt_done = sum(1 for r in requests_list if (r.get("status") == "done"))

    filtered = requests_list

    if status_:
        filtered = [r for r in filtered if r.get("status") == status_]

    if no_offer == 1:
        filtered = [r for r in filtered if not r.get("my_offer")]

    return templates.TemplateResponse(
        "service_center/requests.html",
        {
            "request": request,
            "service_center": sc,
            "requests_list": filtered,
            "error_message": error_message,
            "filter_status": status_,
            "filter_no_offer": 1 if no_offer == 1 else 0,
            "counters": {
                "total": total,
                "no_offer": cnt_no_offer,
                "in_work": cnt_in_work,
                "done": cnt_done,
            },
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

    # ✅ чтобы шаблон не падал
    offer_status_labels = {
        "new": "Новый",
        "accepted": "Принят",
        "rejected": "Отклонён",
    }

    error_message = None

    sc = await _load_sc_for_owner(request, client, sc_id)

    try:
        r = await client.get(f"/api/v1/requests/{request_id}")
        r.raise_for_status()
        request_data = r.json()
    except Exception:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

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

    offers: list[dict[str, Any]] = []
    try:
        offers_resp = await client.get(f"/api/v1/offers/by-request/{request_id}")
        if offers_resp.status_code == 200:
            offers = offers_resp.json() or []
    except Exception:
        offers = []

    my_offer: dict[str, Any] | None = None
    try:
        for o in offers:
            if o.get("service_center_id") == sc_id:
                my_offer = o
                break
    except Exception:
        my_offer = None

    offers_for_view: list[dict[str, Any]] = [my_offer] if my_offer else []

    return templates.TemplateResponse(
        "service_center/request_detail.html",
        {
            "request": request,
            "service_center": sc,
            "req": request_data,
            "offers": offers_for_view,
            "my_offer": my_offer,
            "error_message": error_message,
            "bot_username": BOT_USERNAME,
            "client_telegram_id": client_telegram_id,
            # ✅ добавили
            "offer_status_labels": offer_status_labels,
        },
    )


@router.post("/{sc_id}/requests/{request_id}/offer", response_class=HTMLResponse)
async def sc_offer_submit(
    sc_id: int,
    request_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    price_text: str = Form(...),
    eta_text: str = Form(...),
    comment: str = Form(""),
) -> HTMLResponse:
    sc = await _load_sc_for_owner(request, client, sc_id)

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
        pass

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

    def _try_parse_float(s: str) -> float | None:
        s = (s or "").strip().replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None

    def _try_parse_int(s: str) -> int | None:
        s = (s or "").strip()
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None
        try:
            return int(digits)
        except Exception:
            return None

    price_text_clean = (price_text or "").strip()
    eta_text_clean = (eta_text or "").strip()

    payload: dict[str, Any] = {
        "request_id": request_id,
        "service_center_id": sc_id,
        "price_text": price_text_clean or None,
        "eta_text": eta_text_clean or None,
        "comment": (comment or "").strip() or None,
    }

    p_num = _try_parse_float(price_text_clean)
    if p_num is not None:
        payload["price"] = p_num

    eta_num = _try_parse_int(eta_text_clean)
    if eta_num is not None:
        payload["eta_hours"] = eta_num

    templates = get_templates()
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
    final_price_text: str = Form(...),
) -> HTMLResponse:
    _ = await _load_sc_for_owner(request, client, sc_id)

    def _try_parse_float(s: str) -> float | None:
        s = (s or "").strip().replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None

    final_price_text_clean = (final_price_text or "").strip()
    payload: dict[str, Any] = {
        "service_center_id": sc_id,
        "final_price_text": final_price_text_clean or None,
    }

    p_num = _try_parse_float(final_price_text_clean)
    if p_num is not None:
        payload["final_price"] = p_num

    try:
        resp = await client.post(
            f"/api/v1/requests/{request_id}/set_done",
            json=payload,
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

    try:
        resp = await client.post(
            f"/api/v1/requests/{request_id}/send_chat_link",
            json={"service_center_id": sc_id, "recipient": "service_center"},
        )
        if resp.status_code >= 400:
            try:
                detail = (resp.json() or {}).get("detail")
            except Exception:
                detail = None

            return JSONResponse(
                {"ok": False, "error": detail or "Не удалось отправить ссылку в Telegram. Попробуйте позже."},
                status_code=resp.status_code,
            )
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "Не удалось отправить ссылку в Telegram. Попробуйте позже."},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    return JSONResponse({"ok": True})
