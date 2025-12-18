from __future__ import annotations

import logging
import os
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.services.user_service import UsersService
from backend.app.services.bonus_service import BonusService

from backend.app.core.notifier import BotNotifier
from backend.app.models import (
    Request,
    RequestDistribution,
    RequestDistributionStatus,
    RequestStatus,
    ServiceCenter,
    User,
    Offer,
    OfferStatus,
    BonusTransaction,
    BonusReason,
)
from backend.app.schemas.request import RequestCreate, RequestUpdate

logger = logging.getLogger(__name__)

WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").rstrip("/")
notifier = BotNotifier()


def _btn_webapp(text: str, url: str) -> dict[str, str]:
    return {"text": text, "type": "web_app", "url": url}


class RequestsService:
    """
    Сервисный слой для заявок.
    """

    @staticmethod
    async def create_request(db: AsyncSession, data: RequestCreate) -> Request:
        req = Request(
            user_id=data.user_id,
            car_id=data.car_id,
            service_center_id=None,
            latitude=data.latitude,
            longitude=data.longitude,
            address_text=data.address_text,
            is_car_movable=data.is_car_movable,
            need_tow_truck=data.need_tow_truck,
            need_mobile_master=data.need_mobile_master,
            radius_km=data.radius_km,
            service_category=data.service_category,
            description=data.description,
            photos=data.photos,
            hide_phone=data.hide_phone,
            status=RequestStatus.NEW,
            final_price=None,
            reject_reason=None,
        )
        db.add(req)
        await db.commit()
        await db.refresh(req)
        return req

    @staticmethod
    async def get_request_by_id(db: AsyncSession, request_id: int) -> Optional[Request]:
        stmt = select(Request).where(Request.id == request_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_requests_by_user(db: AsyncSession, user_id: int) -> List[Request]:
        stmt = (
            select(Request)
            .where(Request.user_id == user_id)
            .order_by(Request.created_at.desc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def list_requests(db: AsyncSession, status: str | None = None) -> List[Request]:
        stmt = select(Request).order_by(Request.created_at.desc())
        if status:
            stmt = stmt.where(Request.status == status)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def list_requests_for_service_center(
        db: AsyncSession,
        service_center_id: int,
    ) -> List[Request]:
        stmt = (
            select(Request)
            .join(RequestDistribution, RequestDistribution.request_id == Request.id)
            .where(RequestDistribution.service_center_id == service_center_id)
            .order_by(Request.created_at.desc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_request(
        db: AsyncSession,
        request_id: int,
        data: RequestUpdate,
    ) -> Optional[Request]:
        req = await RequestsService.get_request_by_id(db, request_id)
        if not req:
            return None

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(req, field, value)

        await db.commit()
        await db.refresh(req)
        return req

    @staticmethod
    async def distribute_request_to_service_centers(
        db: AsyncSession,
        request_id: int,
        service_center_ids: List[int],
    ) -> Optional[Request]:
        req = await RequestsService.get_request_by_id(db, request_id)
        if not req:
            return None

        await db.execute(
            delete(RequestDistribution).where(RequestDistribution.request_id == request_id)
        )

        for sc_id in service_center_ids:
            db.add(
                RequestDistribution(
                    request_id=request_id,
                    service_center_id=sc_id,
                    status=RequestDistributionStatus.SENT,
                )
            )

        req.status = RequestStatus.SENT

        await db.commit()
        await db.refresh(req)
        return req

    @staticmethod
    async def set_in_work(
        db: AsyncSession,
        request_id: int,
        service_center_id: int,
        *,
        notify_client_telegram_id: int | None = None,
    ) -> Optional[Request]:
        req = await RequestsService.get_request_by_id(db, request_id)
        if not req:
            return None

        if req.service_center_id != service_center_id:
            logger.warning(
                "set_in_work: sc_id mismatch (req=%s sc=%s)",
                req.service_center_id, service_center_id
            )
            return req

        req.status = RequestStatus.IN_WORK
        await db.commit()
        await db.refresh(req)

        tg_id = notify_client_telegram_id
        if tg_id is None:
            client = await UsersService.get_by_id(db, req.user_id)
            tg_id = getattr(client, "telegram_id", None) if client else None

        if notifier.is_enabled() and WEBAPP_PUBLIC_URL and tg_id:
            await notifier.send_notification(
                recipient_type="client",
                telegram_id=int(tg_id),
                message=f"🛠 Заявка №{request_id} взята в работу сервисом.",
                buttons=[_btn_webapp("Открыть заявку", f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}")],
                extra={"request_id": request_id, "status": "IN_WORK"},
            )

        return req

    @staticmethod
    async def _award_cashback_if_needed(db: AsyncSession, req: Request) -> None:
        """
        Начисляем кэшбек клиенту, если:
        - есть final_price
        - есть ACCEPTED-оффер с cashback_percent > 0
        - ещё не начисляли по (request_id, offer_id, reason=COMPLETE_REQUEST)
        """
        if req.final_price is None:
            return

        res = await db.execute(
            select(Offer).where(
                Offer.request_id == req.id,
                Offer.status == OfferStatus.ACCEPTED,
            )
        )
        offer = res.scalar_one_or_none()
        if not offer:
            return

        if offer.cashback_percent is None:
            return

        try:
            pct = float(offer.cashback_percent)
        except Exception:
            return

        if pct <= 0:
            return

        amount = int(round(float(req.final_price) * pct / 100.0))
        if amount <= 0:
            return

        # защита от повторного начисления
        exists_res = await db.execute(
            select(BonusTransaction.id).where(
                BonusTransaction.user_id == req.user_id,
                BonusTransaction.request_id == req.id,
                BonusTransaction.offer_id == offer.id,
                BonusTransaction.reason == BonusReason.COMPLETE_REQUEST,
            )
        )
        if exists_res.scalar_one_or_none() is not None:
            return

        await BonusService.add_bonus(
            db=db,
            user_id=req.user_id,
            amount=amount,
            reason=BonusReason.COMPLETE_REQUEST,
            request_id=req.id,
            offer_id=offer.id,
            description=f"Кэшбек {pct:.0f}% по заявке №{req.id}",
        )

    @staticmethod
    async def set_done(
        db: AsyncSession,
        request_id: int,
        service_center_id: int,
        *,
        final_price: float | None = None,
        notify_client_telegram_id: int | None = None,
    ) -> Optional[Request]:
        req = await RequestsService.get_request_by_id(db, request_id)
        if not req:
            return None

        if req.service_center_id != service_center_id:
            logger.warning(
                "set_done: sc_id mismatch (req=%s sc=%s)",
                req.service_center_id, service_center_id
            )
            return req

        req.status = RequestStatus.DONE
        if final_price is not None:
            req.final_price = float(final_price)

        await db.commit()
        await db.refresh(req)

        # ✅ начисляем кэшбек (не зависит от Telegram)
        try:
            await RequestsService._award_cashback_if_needed(db, req)
        except Exception:
            logger.exception("cashback award failed for request_id=%s", request_id)

        tg_id = notify_client_telegram_id
        if tg_id is None:
            client = await UsersService.get_by_id(db, req.user_id)
            tg_id = getattr(client, "telegram_id", None) if client else None

        if notifier.is_enabled() and WEBAPP_PUBLIC_URL and tg_id:
            text_price = f"\n💰 Итоговая цена: {req.final_price:.0f}" if req.final_price is not None else ""
            await notifier.send_notification(
                recipient_type="client",
                telegram_id=int(tg_id),
                message=f"✅ Заявка №{request_id} завершена сервисом.{text_price}",
                buttons=[_btn_webapp("Открыть заявку", f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}")],
                extra={"request_id": request_id, "status": "DONE"},
            )

        return req

    @staticmethod
    async def reject_by_service(
        db: AsyncSession,
        request_id: int,
        service_center_id: int,
        *,
        reason: str | None = None,
        notify_client_telegram_id: int | None = None,
    ) -> Optional[Request]:
        req = await RequestsService.get_request_by_id(db, request_id)
        if not req:
            return None

        if req.service_center_id != service_center_id:
            logger.warning(
                "reject_by_service: sc_id mismatch (req=%s sc=%s)",
                req.service_center_id, service_center_id
            )
            return req

        req.status = RequestStatus.REJECTED_BY_SERVICE
        req.reject_reason = reason

        await db.commit()
        await db.refresh(req)

        tg_id = notify_client_telegram_id
        if tg_id is None:
            client = await UsersService.get_by_id(db, req.user_id)
            tg_id = getattr(client, "telegram_id", None) if client else None

        if notifier.is_enabled() and WEBAPP_PUBLIC_URL and tg_id:
            suffix = f"\nПричина: {reason}" if reason else ""
            await notifier.send_notification(
                recipient_type="client",
                telegram_id=int(tg_id),
                message=f"❌ Сервис отказался от заявки №{request_id}.{suffix}",
                buttons=[_btn_webapp("Открыть заявку", f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}")],
                extra={"request_id": request_id, "status": "REJECTED_BY_SERVICE"},
            )

        return req
