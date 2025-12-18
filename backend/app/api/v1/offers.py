from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.offer import OfferCreate, OfferUpdate, OfferRead
from backend.app.services.offers_service import OffersService

router = APIRouter(
    prefix="/offers",
    tags=["offers"],
)


@router.post("/", response_model=OfferRead)
async def create_offer(
    payload: OfferCreate,
    db: AsyncSession = Depends(get_db),
):
    return await OffersService.create_offer(db, payload.dict())


@router.patch("/{offer_id}", response_model=OfferRead)
async def update_offer(
    offer_id: int,
    payload: OfferUpdate,
    db: AsyncSession = Depends(get_db),
):
    offer = await OffersService.update_offer(db, offer_id, payload.dict())
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    return offer


@router.get("/by-request/{request_id}", response_model=list[OfferRead])
async def offers_by_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    # ✅ FIX: в сервисе метод называется list_offers_by_request
    return await OffersService.list_offers_by_request(db, request_id)


# ----------------------------
# КЛИЕНТ ПРИНИМАЕТ ОФФЕР
# ----------------------------
@router.post("/{offer_id}/accept-by-client", response_model=OfferRead)
async def accept_offer_by_client(
    offer_id: int,
    db: AsyncSession = Depends(get_db),
):
    offer = await OffersService.accept_offer_by_client(db, offer_id)
    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )
    return offer


# ----------------------------
# КЛИЕНТ ОТКЛОНЯЕТ ОФФЕР
# (нужно, потому что webapp уже вызывает этот роут)
# ----------------------------
@router.post("/{offer_id}/reject-by-client", response_model=OfferRead)
async def reject_offer_by_client(
    offer_id: int,
    db: AsyncSession = Depends(get_db),
):
    offer = await OffersService.reject_offer_by_client(db, offer_id)
    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )
    return offer
