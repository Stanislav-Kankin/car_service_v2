from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.request import (
    RequestCreate,
    RequestRead,
    RequestUpdate,
)
from backend.app.schemas.request_distribution import RequestDistributeIn
from backend.app.services.requests_service import RequestsService
from backend.app.services.service_centers_service import ServiceCentersService

router = APIRouter(
    prefix="/requests",
    tags=["requests"],
)


# ---------------------------------------------------------------------------
# Создание заявки
# ---------------------------------------------------------------------------
@router.post(
    "/",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_request(
    request_in: RequestCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создать новую заявку.
    """
    request = await RequestsService.create_request(db, request_in)
    return request


# ---------------------------------------------------------------------------
# НОВОЕ: отправка заявки всем подходящим СТО
# ---------------------------------------------------------------------------
@router.post(
    "/{request_id}/send_to_all",
    response_model=RequestRead,
    status_code=status.HTTP_200_OK,
)
async def send_request_to_all_service_centers(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Отправка заявки всем подходящим СТО.

    1) Берём заявку по ID.
    2) Ищем подходящие СТО (по гео/радиусу/категории).
    3) Фиксируем распределение через RequestsService.distribute_request_to_service_centers.
    """
    request = await RequestsService.get_request_by_id(db, request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    # ВАЖНО: для service_category="sto" не фильтруем по специализациям —
    #       берём все активные СТО в радиусе (MVP-поведение).
    specializations = None
    if request.service_category and request.service_category not in ("sto",):
        specializations = [request.service_category]

    service_centers = await ServiceCentersService.search_service_centers(
        db,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_km=request.radius_km,
        specializations=specializations,
    )

    service_center_ids = [sc.id for sc in service_centers]

    if not service_center_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No service centers found for this request",
        )

    distributed_request = (
        await RequestsService.distribute_request_to_service_centers(
            db,
            request_id=request_id,
            service_center_ids=service_center_ids,
        )
    )
    return distributed_request


# ---------------------------------------------------------------------------
# НОВОЕ: отправка заявки выбранному СТО
# ---------------------------------------------------------------------------
@router.post(
    "/{request_id}/send_to_service_center",
    response_model=RequestRead,
    status_code=status.HTTP_200_OK,
)
async def send_request_to_service_center(
    request_id: int,
    payload: RequestDistributeIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Отправка заявки конкретному СТО (одному).

    Ожидает тело:
    {
        "service_center_ids": [<один ID>]
    }
    """
    if not payload.service_center_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="service_center_ids is required",
        )

    # Берём только первый ID (MVP: один сервис)
    service_center_id = payload.service_center_ids[0]

    distributed_request = (
        await RequestsService.distribute_request_to_service_centers(
            db,
            request_id=request_id,
            service_center_ids=[service_center_id],
        )
    )
    if not distributed_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return distributed_request

# ---------------------------------------------------------------------------
# (СТАРОЕ) Список заявок для СТО по специализациям
# Сейчас в боте не используется, но оставляем как запасной вариант.
# ---------------------------------------------------------------------------
@router.get(
    "/for-service-centers",
    response_model=List[RequestRead],
)
async def get_requests_for_service_centers(
    specializations: List[str] | None = Query(
        None,
        description="Коды специализаций СТО (tire, mechanic и т.п.)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Список заявок для просмотра СТО (старый режим, по специализациям).

    Если переданы specializations — вернём только заявки с такими категориями.
    """
    requests = await RequestsService.list_requests_for_service_centers_by_specializations(
        db,
        specializations=specializations,
    )
    return requests


# ---------------------------------------------------------------------------
# НОВОЕ: распределение заявки по конкретным СТО
# ---------------------------------------------------------------------------
@router.post(
    "/{request_id}/distribute",
    response_model=RequestRead,
    status_code=status.HTTP_200_OK,
)
async def distribute_request_to_service_centers(
    request_id: int,
    payload: RequestDistributeIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Зафиксировать, каким СТО была отправлена заявка.

    Ожидает тело:
    {
        "service_center_ids": [1, 2, 3]
    }
    """
    request = await RequestsService.distribute_request_to_service_centers(
        db,
        request_id=request_id,
        service_center_ids=payload.service_center_ids,
    )
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return request


# ---------------------------------------------------------------------------
# НОВОЕ: список заявок для конкретного СТО
# ---------------------------------------------------------------------------
@router.get(
    "/for-service-center/{service_center_id}",
    response_model=List[RequestRead],
)
async def get_requests_for_service_center(
    service_center_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Список заявок, которые были разосланы КОНКРЕТНОМУ СТО.

    Использует RequestDistribution, поэтому:
    - СТО видит только те заявки, которые реально ему отправили.
    """
    requests = await RequestsService.list_requests_for_service_center(
        db,
        service_center_id=service_center_id,
    )
    return requests


# ---------------------------------------------------------------------------
# Список заявок по пользователю
# ---------------------------------------------------------------------------
@router.get(
    "/by-user/{user_id}",
    response_model=List[RequestRead],
)
async def get_requests_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список заявок конкретного пользователя.
    """
    requests = await RequestsService.list_requests_by_user(db, user_id)
    return requests


# ---------------------------------------------------------------------------
# Получить заявку по ID
# ---------------------------------------------------------------------------
@router.get(
    "/{request_id}",
    response_model=RequestRead,
)
async def get_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить заявку по ID.
    """
    request = await RequestsService.get_request_by_id(db, request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return request


# ---------------------------------------------------------------------------
# Частичное обновление заявки
# ---------------------------------------------------------------------------
@router.patch(
    "/{request_id}",
    response_model=RequestRead,
)
async def update_request(
    request_id: int,
    request_in: RequestUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Частичное обновление заявки.
    """
    request = await RequestsService.update_request(db, request_id, request_in)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return request


@router.post("/{request_id}/send_to_all", response_model=RequestRead)
async def send_to_all(
    request_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Отправить заявку ВСЕМ подходящим СТО
    """
    request = await RequestsService.get_request_by_id(db, request_id)
    if not request:
        raise HTTPException(404, "Request not found")

    sc_list = await ServiceCentersService.search_service_centers(
        db,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_km=request.radius_km,
        specializations=[request.service_category] if request.service_category else None,
    )

    ids = [sc.id for sc in sc_list]

    updated_request = await RequestsService.distribute_request_to_service_centers(
        db,
        request_id=request_id,
        service_center_ids=ids
    )
    return updated_request


@router.post("/{request_id}/send_to_service_center", response_model=RequestRead)
async def send_to_one_service(
    request_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Отправить заявки одному выбранному СТО.
    Формат:
    { "service_center_id": 5 }
    """
    sc_id = data.get("service_center_id")
    if not sc_id:
        raise HTTPException(400, "service_center_id is required")

    updated_request = await RequestsService.distribute_request_to_service_centers(
        db,
        request_id=request_id,
        service_center_ids=[sc_id]
    )
    return updated_request
