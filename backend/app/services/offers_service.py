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
    async def get_offer_by_id(db: AsyncSession, offer_id: int) -> Optional[Offer]:
        stmt = (
            select(Offer)
            .where(Offer.id == offer_id)
            .options(
                selectinload(Offer.request).selectinload(Request.user),
                selectinload(Offer.service_center).selectinload(ServiceCenter.owner),
            )
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def create_offer(db: AsyncSession, data: dict) -> Offer:
        data_clean = {
            "request_id": data["request_id"],
            "service_center_id": data["service_center_id"],

            # новые поля
            "price_text": data.get("price_text"),
            "eta_text": data.get("eta_text"),

            # старые поля (fallback)
            "price": data.get("price"),
            "eta_hours": data.get("eta_hours"),

            "comment": data.get("comment"),
            "cashback_percent": data.get("cashback_percent"),
            "status": OfferStatus.NEW,
        }

        offer = Offer(**data_clean)
        db.add(offer)
        await db.commit()
        await db.refresh(offer)

        # --- Уведомление клиента о новом оффере ---
        offer_full = await OffersService.get_offer_by_id(db, offer.id)
        if offer_full and offer_full.request and offer_full.request.user:
            client = offer_full.request.user
            if notifier.is_enabled() and getattr(client, "telegram_id", None):
                request_id = offer_full.request.id
                url = f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}"
                await notifier.send_notification(
                    recipient_type="client",
                    telegram_id=int(client.telegram_id),
                    message=f"📩 Новый отклик по заявке №{request_id}!",
                    buttons=[
                        {"text": "Открыть заявку", "type": "web_app", "url": url},
                    ],
                    extra={"request_id": request_id, "offer_id": offer.id},
                )

        return offer

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
    async def list_offers_by_request(db: AsyncSession, request_id: int) -> List[Offer]:
        stmt = select(Offer).where(Offer.request_id == request_id).order_by(Offer.created_at.desc())
        res = await db.execute(stmt)
        return list(res.scalars().all())

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

        req = offer.request
        if not req:
            return None

        # проставим всем офферам статус
        stmt = select(Offer).where(Offer.request_id == req.id)
        res = await db.execute(stmt)
        offers = list(res.scalars().all())

        for o in offers:
            o.status = OfferStatus.REJECTED
        offer.status = OfferStatus.ACCEPTED

        # request -> выбранный сервис
        req.service_center_id = offer.service_center_id
        req.status = RequestStatus.ACCEPTED_BY_SERVICE

        await db.commit()
        await db.refresh(offer)

        # уведомление сервису + клиенту (как у тебя было)
        offer_full = await OffersService.get_offer_by_id(db, offer.id)
        if offer_full and notifier.is_enabled():
            request_id = offer_full.request.id if offer_full.request else None

            # сервису
            if offer_full.service_center and offer_full.service_center.owner and getattr(offer_full.service_center.owner, "telegram_id", None):
                sc_owner_tg = int(offer_full.service_center.owner.telegram_id)
                url_sc = f"{WEBAPP_PUBLIC_URL}/sc/{offer_full.service_center_id}/requests/{request_id}"
                await notifier.send_notification(
                    recipient_type="service_center",
                    telegram_id=sc_owner_tg,
                    message=(
                        f"🎉 Ваше предложение по заявке №{request_id} выбрано клиентом!\n"
                        f"Откройте заявку и переведите её в работу."
                    ),
                    buttons=[
                        {"text": "Открыть заявку", "type": "web_app", "url": url_sc},
                    ],
                    extra={"request_id": request_id, "offer_id": offer_id},
                )

            # клиенту
            if offer_full.request and offer_full.request.user and getattr(offer_full.request.user, "telegram_id", None):
                client_tg = int(offer_full.request.user.telegram_id)
                url_me = f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}"
                await notifier.send_notification(
                    recipient_type="client",
                    telegram_id=client_tg,
                    message=f"✅ Вы выбрали сервис по заявке №{request_id}.",
                    buttons=[
                        {"text": "Открыть заявку", "type": "web_app", "url": url_me},
                    ],
                    extra={"request_id": request_id, "offer_id": offer_id},
                )

        return offer

    @staticmethod
    async def reject_offer_by_client(db: AsyncSession, offer_id: int) -> Optional[Offer]:
        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None
        offer.status = OfferStatus.REJECTED
        await db.commit()
        await db.refresh(offer)
        return offer
