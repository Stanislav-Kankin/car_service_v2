from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.offer import OfferCreate, OfferUpdate, OfferRead
from backend.app.services.offers_service import OffersService

router = APIRouter(
    prefix="/offers",
    tags=["offers"],
)


# ----------------------------------------------------------------------
# Создать оффер
# ----------------------------------------------------------------------
@router.post("/", response_model=OfferRead)
async def create_offer(
    payload: OfferCreate,
    db: AsyncSession = Depends(get_db),
):
    return await OffersService.create_offer(db, payload.dict())


# ----------------------------------------------------------------------
# Обновить оффер
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# Все офферы по заявке
# ----------------------------------------------------------------------
@router.get("/by-request/{request_id}", response_model=list[OfferRead])
async def offers_by_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await OffersService.get_offers_by_request(db, request_id)


# ----------------------------------------------------------------------
# КЛЮЧЕВОЙ ЭНДПОИНТ:
# КЛИЕНТ ПРИНИМАЕТ ОФФЕР
# ----------------------------------------------------------------------
@router.post("/{offer_id}/accept-by-client", response_model=OfferRead)
async def accept_by_client(
    offer_id: int,
    db: AsyncSession = Depends(get_db),
):
    offer = await OffersService.accept_offer_by_client(db, offer_id)
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    return offer


@router.post(
    "/{offer_id}/accept-by-client",
    response_model=OfferRead,
)
async def accept_offer_by_client(
    offer_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Клиент принимает оффер.

    Здесь просто дергаем сервис, который:
      - отмечает этот оффер как ACCEPTED,
      - остальные по заявке как REJECTED,
      - записывает выбранный service_center_id в заявку,
      - меняет статус заявки,
      - шлёт уведомление СТО (если включен BotNotifier).
    """
    offer = await OffersService.accept_offer_by_client(db, offer_id)
    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )
    return offer
