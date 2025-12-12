from typing import List, Optional
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.offer import Offer, OfferStatus
from backend.app.models.request import RequestStatus
from backend.app.core.notifier import BotNotifier

WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").rstrip("/")
notifier = BotNotifier()


class OffersService:
    """
    Логика работы с откликами СТО.
    """

    # ----------------------------------------------------------------------
    # СОЗДАНИЕ ОФФЕРА
    # ----------------------------------------------------------------------
    @staticmethod
    async def create_offer(db: AsyncSession, data: dict) -> Offer:
        """
        Создаем новый оффер. Статус ВСЕГДА должен быть NEW.
        Даже если client/webapp прислал status=None.
        """
        # Жёстко ставим NEW, игнорируя входящее.
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
        return offer

    # ----------------------------------------------------------------------
    # ПОЛУЧЕНИЕ ОФФЕРА
    # ----------------------------------------------------------------------
    @staticmethod
    async def get_offer_by_id(db: AsyncSession, offer_id: int) -> Optional[Offer]:
        stmt = select(Offer).where(Offer.id == offer_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ----------------------------------------------------------------------
    # СПИСОК ОФФЕРОВ ПО ЗАЯВКЕ
    # ----------------------------------------------------------------------
    @staticmethod
    async def get_offers_by_request(db: AsyncSession, request_id: int) -> List[Offer]:
        stmt = select(Offer).where(Offer.request_id == request_id)
        result = await db.execute(stmt)
        return result.scalars().all()

    # ----------------------------------------------------------------------
    # ОБНОВЛЕНИЕ ОФФЕРА
    # ----------------------------------------------------------------------
    @staticmethod
    async def update_offer(db: AsyncSession, offer_id: int, data: dict) -> Optional[Offer]:
        """
        PATCH для оффера. Нельзя допускать, чтобы в БД улетал status=None.
        """

        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None

        # Чистим входные данные:
        # - поля None не обновляем
        # - статус не даём менять вручную
        new_data = {}

        for field, value in data.items():
            if value is None:
                continue
            if field == "status":
                # статус меняется ТОЛЬКО через accept_offer_by_client()
                continue
            new_data[field] = value

        # Обновляем поля модели
        for field, value in new_data.items():
            setattr(offer, field, value)

        await db.commit()
        await db.refresh(offer)
        return offer

    # ----------------------------------------------------------------------
    # ВЫБОР ОФФЕРА КЛИЕНТОМ
    # ----------------------------------------------------------------------
    @staticmethod
    async def accept_offer_by_client(db: AsyncSession, offer_id: int) -> Optional[Offer]:
        """
        Клиент выбрал этот оффер.
        1) Все офферы заявки = REJECTED
        2) Этот = ACCEPTED
        3) request.service_center_id = offer.service_center_id
        4) request.status = ACCEPTED_BY_SERVICE
        5) Уведомить СТО
        """

        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None

        request = offer.request
        if not request:
            return None

        request_id = request.id
        sc_id = offer.service_center_id

        # Все офферы этой заявки
        stmt = select(Offer).where(Offer.request_id == request_id)
        result = await db.execute(stmt)
        all_offers: List[Offer] = result.scalars().all()

        # Обновляем статусы офферов
        for o in all_offers:
            if o.id == offer_id:
                o.status = OfferStatus.ACCEPTED
            else:
                o.status = OfferStatus.REJECTED

        # Обновляем заявку
        request.service_center_id = sc_id
        request.status = RequestStatus.ACCEPTED_BY_SERVICE

        await db.commit()
        await db.refresh(offer)

        # Уведомляем СТО-победителя
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
