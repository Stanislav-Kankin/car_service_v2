from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.service_center import (
    ServiceCenterCreate,
    ServiceCenterRead,
    ServiceCenterUpdate,
)
from backend.app.services.service_centers_service import ServiceCentersService
from backend.app.services.requests_service import RequestsService

router = APIRouter(
    prefix="/service-centers",
    tags=["service_centers"],
)


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
    """
    Подобрать подходящие СТО под конкретную заявку.

    Используем данные заявки (гео, радиус, категория услуги).
    """
    request = await RequestsService.get_request_by_id(db, request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    # Для базового кейса "СТО" НЕ режем по специализациям.
    specializations = None
    if request.service_category and request.service_category not in ("sto",):
        specializations = [request.service_category]

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
