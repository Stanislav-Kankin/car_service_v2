from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Offer, OfferStatus
from backend.app.schemas.offer import OfferCreate, OfferUpdate


class OffersService:
    @staticmethod
    async def create_offer(
        db: AsyncSession,
        data_in: OfferCreate,
    ) -> Offer:
        offer = Offer(
            request_id=data_in.request_id,
            service_center_id=data_in.service_center_id,
            price=data_in.price,
            eta_hours=data_in.eta_hours,
            comment=data_in.comment,
            status=OfferStatus.NEW,
        )
        db.add(offer)
        await db.commit()
        await db.refresh(offer)
        return offer

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        offer_id: int,
    ) -> Optional[Offer]:
        result = await db.execute(
            select(Offer).where(Offer.id == offer_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_request(
        db: AsyncSession,
        request_id: int,
    ) -> List[Offer]:
        result = await db.execute(
            select(Offer).where(Offer.request_id == request_id)
        )
        return result.scalars().all()

    @staticmethod
    async def update_offer(
        db: AsyncSession,
        offer: Offer,
        data_in: OfferUpdate,
    ) -> Offer:
        data = data_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            if field == "status" and isinstance(value, OfferStatus):
                value = value.value
            setattr(offer, field, value)
        await db.commit()
        await db.refresh(offer)
        return offer
