from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.offer import Offer, OfferStatus
from backend.app.models.request import Request, RequestStatus
from backend.app.core.notifier import BotNotifier
from backend.app.services.requests_service import RequestsService

import os

WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").rstrip("/")
notifier = BotNotifier()


class OffersService:
    """
    Логика работы с откликами СТО.
    """

    # ----------------------------------------------------------------------
    # Создание оффера
    # ----------------------------------------------------------------------
    @staticmethod
    async def create_offer(db: AsyncSession, data: dict) -> Offer:
        offer = Offer(**data)
        db.add(offer)
        await db.commit()
        await db.refresh(offer)
        return offer

    # ----------------------------------------------------------------------
    # Обновление оффера
    # ----------------------------------------------------------------------
    @staticmethod
    async def update_offer(db: AsyncSession, offer_id: int, data: dict) -> Optional[Offer]:
        stmt = (
            update(Offer)
            .where(Offer.id == offer_id)
            .values(**data)
            .execution_options(synchronize_session="fetch")
        )
        await db.execute(stmt)
        await db.commit()

        return await OffersService.get_offer_by_id(db, offer_id)

    # ----------------------------------------------------------------------
    # Получить оффер по ID
    # ----------------------------------------------------------------------
    @staticmethod
    async def get_offer_by_id(db: AsyncSession, offer_id: int) -> Optional[Offer]:
        stmt = select(Offer).where(Offer.id == offer_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ----------------------------------------------------------------------
    # Список откликов по заявке
    # ----------------------------------------------------------------------
    @staticmethod
    async def get_offers_by_request(db: AsyncSession, request_id: int) -> List[Offer]:
        stmt = select(Offer).where(Offer.request_id == request_id)
        result = await db.execute(stmt)
        return result.scalars().all()

    # ----------------------------------------------------------------------
    # КЛЮЧЕВАЯ ОПЕРАЦИЯ
    # КЛИЕНТ ПРИНЯЛ ОФФЕР
    # ----------------------------------------------------------------------
    @staticmethod
    async def accept_offer_by_client(db: AsyncSession, offer_id: int) -> Offer:
        """
        1) Найти оффер
        2) Найти заявку
        3) Все остальные офферы → REJECTED
        4) Этот оффер → ACCEPTED
        5) Записать в заявку выбранный service_center_id
        6) Изменить статус заявки → ACCEPTED_BY_SERVICE (как обсуждали)
        7) Уведомить СТО
        """

        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None

        request = offer.request
        if not request:
            return None

        request_id = request.id
        sc_id = offer.service_center_id

        # 1. Все офферы по заявке
        all_offers = await OffersService.get_offers_by_request(db, request_id)

        # 2. Обновляем статусы
        for o in all_offers:
            if o.id == offer_id:
                o.status = OfferStatus.ACCEPTED
            else:
                o.status = OfferStatus.REJECTED

        # 3. Обновляем заявку
        request.service_center_id = sc_id
        request.status = RequestStatus.ACCEPTED_BY_SERVICE

        await db.commit()
        await db.refresh(offer)

        # 4. Уведомляем выбранный СТО
        sc_owner = offer.service_center.owner if offer.service_center else None
        if notifier.is_enabled() and sc_owner and getattr(sc_owner, "telegram_id", None):
            url = f"{WEBAPP_PUBLIC_URL}/sc/{sc_id}/requests/{request_id}"

            await notifier.send_notification(
                recipient_type="service_center",
                telegram_id=sc_owner.telegram_id,
                message=(
                    f"🎉 Ваше предложение по заявке №{request_id} выбрано клиентом!\n"
                    f"Перейдите в карточку заявки, чтобы продолжить работу."
                ),
                buttons=[{"text": "Открыть заявку", "url": url}],
                extra={"request_id": request_id, "service_center_id": sc_id},
            )

        return offer
