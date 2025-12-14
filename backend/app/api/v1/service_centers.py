from typing import List, Optional
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from backend.app.core.db import get_db
from backend.app.schemas.service_center import (
    ServiceCenterCreate,
    ServiceCenterRead,
    ServiceCenterUpdate,
)
from backend.app.services.service_centers_service import ServiceCentersService
from backend.app.services.requests_service import RequestsService
from backend.app.core.catalogs.service_categories import get_specializations_for_category

router = APIRouter(
    prefix="/service-centers",
    tags=["service_centers"],
)


# ----------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНОЕ: уведомление админам о новой СТО на модерации
# ----------------------------------------------------------------------

def _parse_admin_ids_from_env() -> list[int]:
    raw = (os.getenv("TELEGRAM_ADMIN_IDS") or "").strip()
    if not raw:
        return []
    parts = raw.replace(";", ",").split(",")
    ids: list[int] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        try:
            ids.append(int(p))
        except ValueError:
            continue
    return ids


def _admin_moderation_webapp_url() -> str:
    base = (os.getenv("WEBAPP_PUBLIC_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/admin/service-centers"


async def _notify_admins_new_service_center(sc: ServiceCenterRead) -> None:
    """
    Best-effort уведомление админов в Telegram через bot notify API.
    Контракт 1:1 как в bot/app/notify_api.py:
      POST {BOT_API_URL}/api/v1/notify
      payload: recipient_type, telegram_id, message, buttons[{text,type,url}]
      auth: Authorization: Bearer BOT_API_TOKEN
    """
    admin_ids = _parse_admin_ids_from_env()
    bot_api_url = (os.getenv("BOT_API_URL") or "").strip().rstrip("/")
    bot_api_token = (os.getenv("BOT_API_TOKEN") or "").strip()

    if not admin_ids:
        print("WARN notify_admins_new_sc: TELEGRAM_ADMIN_IDS is empty in BACKEND env")
        return
    if not bot_api_url:
        print("WARN notify_admins_new_sc: BOT_API_URL is empty in BACKEND env")
        return

    url = _admin_moderation_webapp_url()

    specs = sc.specializations or []
    if isinstance(specs, list) and specs:
        specs_text = ", ".join(str(x) for x in specs)
    else:
        specs_text = "—"

    msg = (
        "🛂 <b>Новая СТО на модерации</b>\n\n"
        f"ID: <b>{sc.id}</b>\n"
        f"Название: <b>{sc.name}</b>\n"
        f"Тип: <b>{sc.org_type or '—'}</b>\n"
        f"Телефон: <b>{sc.phone or '—'}</b>\n"
        f"Адрес: <b>{sc.address or '—'}</b>\n"
        f"Специализации: <b>{specs_text}</b>\n\n"
        "Откройте админку и активируйте СТО, если всё ок."
    )

    buttons = []
    if url:
        buttons = [
            {
                "text": "🛂 Открыть модерацию",
                "type": "web_app",
                "url": url,
            }
        ]

    headers = {}
    if bot_api_token:
        headers["Authorization"] = f"Bearer {bot_api_token}"

    endpoint = f"{bot_api_url}/api/v1/notify"

    async with httpx.AsyncClient(timeout=5.0) as client:
        for admin_id in admin_ids:
            try:
                r = await client.post(
                    endpoint,
                    json={
                        "recipient_type": "admin",
                        "telegram_id": int(admin_id),
                        "message": msg,
                        "buttons": buttons,
                    },
                    headers=headers,
                )
                if r.status_code >= 400:
                    print(
                        "WARN notify_admins_new_sc: notify failed",
                        r.status_code,
                        r.text[:300],
                    )
            except Exception as e:
                print("WARN notify_admins_new_sc: exception", repr(e))
                continue


# ----------------------------------------------------------------------
# Создание
# ----------------------------------------------------------------------
@router.post(
    "/",
    response_model=ServiceCenterRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_center(
    data_in: ServiceCenterCreate,
    db: AsyncSession = Depends(get_db),
):
    sc = await ServiceCentersService.create_service_center(db, data_in)

    # ✅ если СТО создаётся НЕактивной — это модерация -> уведомляем админов
    try:
        if getattr(sc, "is_active", True) is False:
            await _notify_admins_new_service_center(sc)  # best-effort
    except Exception as e:
        print("WARN create_service_center: notify exception", repr(e))

    return sc


# ----------------------------------------------------------------------
# Получение по id
# ----------------------------------------------------------------------
@router.get(
    "/{sc_id}",
    response_model=ServiceCenterRead,
)
async def get_service_center(
    sc_id: int,
    db: AsyncSession = Depends(get_db),
):
    sc = await ServiceCentersService.get_by_id(db, sc_id)
    if not sc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service center not found",
        )
    return sc


# ----------------------------------------------------------------------
# Список / поиск СТО
# ----------------------------------------------------------------------
@router.get(
    "/",
    response_model=List[ServiceCenterRead],
)
async def list_service_centers(
    db: AsyncSession = Depends(get_db),
    is_active: Optional[bool] = Query(
        True,
        description="Показывать только активные СТО (по умолчанию True).",
    ),
    latitude: Optional[float] = Query(
        None,
        description="Широта для гео-поиска.",
    ),
    longitude: Optional[float] = Query(
        None,
        description="Долгота для гео-поиска.",
    ),
    radius_km: Optional[int] = Query(
        None,
        ge=0,
        description="Радиус поиска в км.",
    ),
    specializations: Optional[str] = Query(
        None,
        description="Список специализаций через запятую.",
    ),
    has_tow_truck: Optional[bool] = Query(
        None,
        description="Только СТО с эвакуатором.",
    ),
    is_mobile_service: Optional[bool] = Query(
        None,
        description="Только выездные мастера / мобильный сервис.",
    ),
):
    specs_list: Optional[List[str]] = None
    if specializations:
        specs_list = [
            item.strip()
            for item in specializations.split(",")
            if item.strip()
        ]

    sc_list = await ServiceCentersService.search_service_centers(
        db,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        specializations=specs_list,
        is_active=is_active,
        # has_tow_truck и is_mobile_service уже есть в сигнатуре search_service_centers,
        # но ты их пока туда не передавал — не трогаю логику без необходимости.
    )
    return sc_list


# ----------------------------------------------------------------------
# СТО конкретного владельца (по user_id)
# ----------------------------------------------------------------------
@router.get(
    "/by-user/{user_id}",
    response_model=List[ServiceCenterRead],
)
async def list_service_centers_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    sc_list = await ServiceCentersService.list_by_user(db, user_id)
    return sc_list


# ----------------------------------------------------------------------
# Список всех СТО (для админки)
# ----------------------------------------------------------------------
@router.get(
    "/all",
    response_model=List[ServiceCenterRead],
)
async def list_all_service_centers(
    db: AsyncSession = Depends(get_db),
    is_active: Optional[bool] = Query(
        None,
        description="Фильтр по активности: true/false или"
    ),
):
    sc_list = await ServiceCentersService.list_all(db, is_active=is_active)
    return sc_list


# ----------------------------------------------------------------------
# Обновление профиля СТО
# ----------------------------------------------------------------------
@router.patch(
    "/{sc_id}",
    response_model=ServiceCenterRead,
)
async def update_service_center(
    sc_id: int,
    data_in: ServiceCenterUpdate,
    db: AsyncSession = Depends(get_db),
):
    sc = await ServiceCentersService.get_by_id(db, sc_id)
    if not sc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service center not found",
        )
    sc = await ServiceCentersService.update_service_center(db, sc, data_in)
    return sc


@router.get(
    "/for-request/{request_id}",
    response_model=List[ServiceCenterRead],
)
async def get_service_centers_for_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    request = await RequestsService.get_request_by_id(db, request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    spec_codes = get_specializations_for_category(request.service_category)
    if spec_codes is None and request.service_category and request.service_category not in ("sto",):
        spec_codes = [request.service_category]

    specializations = spec_codes or None

    has_tow_truck = request.need_tow_truck or None
    is_mobile_service = request.need_mobile_master or None

    service_centers = await ServiceCentersService.search_service_centers(
        db,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_km=request.radius_km,
        specializations=specializations,
        is_active=True,
        has_tow_truck=has_tow_truck,
        is_mobile_service=is_mobile_service,
    )
    return service_centers
