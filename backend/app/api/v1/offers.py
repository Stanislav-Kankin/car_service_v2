from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.offer import OfferCreate, OfferRead, OfferUpdate
from backend.app.services.offers_service import OffersService

router = APIRouter(
    prefix="/offers",
    tags=["offers"],
)


@router.post(
    "/",
    response_model=OfferRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_offer(
    offer_in: OfferCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создать новый отклик СТО на заявку.
    """
    offer = await OffersService.create_offer(db, offer_in)
    return offer


@router.get(
    "/by-request/{request_id}",
    response_model=List[OfferRead],
)
async def list_offers_by_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Список откликов по конкретной заявке.
    """
    offers = await OffersService.list_by_request(db, request_id)
    return offers


@router.get(
    "/{offer_id}",
    response_model=OfferRead,
)
async def get_offer(
    offer_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить отклик по ID.
    """
    offer = await OffersService.get_by_id(db, offer_id)
    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )
    return offer


@router.patch(
    "/{offer_id}",
    response_model=OfferRead,
)
async def update_offer(
    offer_id: int,
    data_in: OfferUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Частичное обновление отклика (статус и т.п.).
    """
    offer = await OffersService.get_by_id(db, offer_id)
    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )

    offer = await OffersService.update_offer(db, offer, data_in)
    return offer
