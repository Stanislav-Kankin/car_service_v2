from typing import List, Optional
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.offer import Offer, OfferStatus
from backend.app.models.request import RequestStatus, Request
from backend.app.models.service_center import ServiceCenter
from backend.app.core.notifier import BotNotifier

WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").rstrip("/")
notifier = BotNotifier()


class OffersService:
    """
    Логика работы с откликами СТО.
    """

    @staticmethod
    async def create_offer(db: AsyncSession, data: dict) -> Offer:
        data_clean = {
            "request_id": data["request_id"],
            "service_center_id": data["service_center_id"],
            "price": data["price"],
            "eta_hours": data["eta_hours"],
            "comment": data.get("comment"),
            "status": OfferStatus.NEW,
        }

        offer = Offer(**data_clean)
        db.add(offer)
        await db.commit()
        await db.refresh(offer)

        # --- Уведомление клиента о новом оффере ---
        # Берём оффер уже с подтянутыми связями (request.user, service_center.owner)
        offer_full = await OffersService.get_offer_by_id(db, offer.id)
        if offer_full and offer_full.request and offer_full.request.user:
            client = offer_full.request.user
            if notifier.is_enabled() and getattr(client, "telegram_id", None):
                request_id = offer_full.request.id
                url = f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}"
                await notifier.send_notification(
                    recipient_type="client",
                    telegram_id=client.telegram_id,
                    message=(
                        f"📩 По вашей заявке №{request_id} пришёл новый отклик!\n"
                        f"Откройте заявку и выберите предложение."
                    ),
                    buttons=[{"text": "Открыть заявку", "type": "web_app", "url": url}],
                    extra={"request_id": request_id},
                )

        return offer

    @staticmethod
    async def get_offer_by_id(db: AsyncSession, offer_id: int) -> Optional[Offer]:
        stmt = (
            select(Offer)
            .where(Offer.id == offer_id)
            .options(
                selectinload(Offer.request).selectinload(Request.user),
                selectinload(Offer.service_center).selectinload(ServiceCenter.owner),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_offers_by_request(db: AsyncSession, request_id: int) -> List[Offer]:
        stmt = select(Offer).where(Offer.request_id == request_id)
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def update_offer(db: AsyncSession, offer_id: int, data: dict) -> Optional[Offer]:
        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None

        new_data = {}
        for field, value in data.items():
            if value is None:
                continue
            if field == "status":
                continue
            new_data[field] = value

        for field, value in new_data.items():
            setattr(offer, field, value)

        await db.commit()
        await db.refresh(offer)
        return offer

    @staticmethod
    async def reject_offer_by_client(db: AsyncSession, offer_id: int) -> Optional[Offer]:
        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None

        # просто помечаем конкретный оффер как rejected
        # заявку не трогаем (она может продолжать собирать офферы)
        offer.status = OfferStatus.REJECTED

        await db.commit()
        await db.refresh(offer)
        return offer

    @staticmethod
    async def accept_offer_by_client(db: AsyncSession, offer_id: int) -> Optional[Offer]:
        """
        Клиент выбрал оффер.
        1) Этот = ACCEPTED
        2) Остальные по заявке = REJECTED
        3) request.service_center_id = offer.service_center_id
        4) request.status = ACCEPTED_BY_SERVICE (временно)
        5) Уведомить СТО + клиента
        """

        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None

        request = offer.request
        if not request:
            return None

        request_id = request.id
        sc_id = offer.service_center_id

        # если заявка уже закреплена за другим СТО — не перетираем
        if request.service_center_id and request.service_center_id != sc_id:
            return offer

        # Все офферы этой заявки
        stmt = select(Offer).where(Offer.request_id == request_id)
        result = await db.execute(stmt)
        all_offers: List[Offer] = result.scalars().all()

        for o in all_offers:
            o.status = OfferStatus.ACCEPTED if o.id == offer_id else OfferStatus.REJECTED

        request.service_center_id = sc_id
        request.status = RequestStatus.ACCEPTED_BY_SERVICE

        await db.commit()
        await db.refresh(offer)

        # --- уведомление СТО ---
        sc_owner = offer.service_center.owner if offer.service_center else None
        if notifier.is_enabled() and sc_owner and getattr(sc_owner, "telegram_id", None):
            url = f"{WEBAPP_PUBLIC_URL}/sc/{sc_id}/requests/{request_id}"
            await notifier.send_notification(
                recipient_type="service_center",
                telegram_id=sc_owner.telegram_id,
                message=(
                    f"🎉 Ваше предложение по заявке №{request_id} выбрано клиентом!\n"
                    f"Откройте заявку и переведите её в работу."
                ),
                buttons=[{"text": "Открыть заявку", "type": "web_app", "url": url}],
                extra={"request_id": request_id, "service_center_id": sc_id},
            )

            # --- уведомление клиента ---
        client_user = request.user
        if notifier.is_enabled() and client_user and getattr(client_user, "telegram_id", None):
            url = f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}"
            await notifier.send_notification(
                recipient_type="client",
                telegram_id=client_user.telegram_id,
                message=(
                    f"✅ Вы выбрали сервис по заявке №{request_id}.\n"
                    f"Ожидайте, когда сервис возьмёт заявку в работу."
                ),
                buttons=[{"text": "Открыть заявку", "type": "web_app", "url": url}],
                extra={"request_id": request_id, "service_center_id": sc_id},
            )

        return offer
