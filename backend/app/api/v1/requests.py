from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.request import RequestCreate, RequestRead, RequestUpdate
from backend.app.services.requests_service import RequestsService

router = APIRouter()


@router.post(
    "/",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_request(
    data_in: RequestCreate,
    db: AsyncSession = Depends(get_db),
):
    req = await RequestsService.create_request(db, data_in)
    return req


@router.get(
    "/{request_id}",
    response_model=RequestRead,
)
async def get_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    req = await RequestsService.get_by_id(db, request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return req


@router.get(
    "/by-user/{user_id}",
    response_model=List[RequestRead],
)
async def list_requests_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    items = await RequestsService.list_by_user(db, user_id)
    return items


@router.patch(
    "/{request_id}",
    response_model=RequestRead,
)
async def update_request(
    request_id: int,
    data_in: RequestUpdate,
    db: AsyncSession = Depends(get_db),
):
    req = await RequestsService.get_by_id(db, request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    req = await RequestsService.update_request(db, req, data_in)
    return req
