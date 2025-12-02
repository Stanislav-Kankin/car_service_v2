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

router = APIRouter()


@router.post(
    "/",
    response_model=ServiceCenterRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_center(
    data_in: ServiceCenterCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создать СТО / сервисный центр.

    В реальности это будет вызываться ботом/webapp при регистрации СТО.
    """
    sc = await ServiceCentersService.create_service_center(db, data_in)
    return sc


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


@router.get(
    "/",
    response_model=List[ServiceCenterRead],
)
async def list_service_centers(
    specialization: Optional[str] = Query(
        None,
        description="Фильтр по специализации (строка из списка specializations)",
    ),
    is_active: Optional[bool] = True,
    has_tow_truck: Optional[bool] = None,
    is_mobile_service: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Список СТО с простыми фильтрами.

    Позже сюда добавим гео-фильтры по радиусу/координатам.
    """
    items = await ServiceCentersService.list_service_centers(
        db=db,
        specialization=specialization,
        is_active=is_active,
        has_tow_truck=has_tow_truck,
        is_mobile_service=is_mobile_service,
    )
    return items


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
