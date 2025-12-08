from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.request import (
    RequestCreate,
    RequestRead,
    RequestUpdate,
)
from backend.app.services.requests_service import RequestsService

router = APIRouter(
    prefix="/requests",
    tags=["requests"],
)


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
    Список заявок для просмотра СТО.

    Если переданы specializations — вернём только заявки с такими категориями.
    """
    requests = await RequestsService.list_requests_for_service_centers(
        db,
        specializations=specializations,
    )
    return requests


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
