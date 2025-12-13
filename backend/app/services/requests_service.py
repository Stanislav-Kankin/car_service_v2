from typing import List, Optional

import os
import logging

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.notifier import BotNotifier
from backend.app.models import (
    Request,
    RequestStatus,
    RequestDistribution,
    RequestDistributionStatus,
    User,
    ServiceCenter,
)
from backend.app.schemas.request import (
    RequestCreate,
    RequestRead,
    RequestUpdate,
)

logger = logging.getLogger(__name__)
WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").rstrip("/")
notifier = BotNotifier()


def _btn_webapp(text: str, url: str) -> dict[str, str]:
    return {"text": text, "type": "web_app", "url": url}


class RequestsService:
    """
    Сервисный слой для заявок.
    """

    # ------------------------------------------------------------------
    # Создание заявки
    # ------------------------------------------------------------------
    @staticmethod
    async def create_request(
        db: AsyncSession,
        data: RequestCreate,
    ) -> Request:
        request = Request(
            user_id=data.user_id,
            car_id=data.car_id,
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
        )
        db.add(request)
        await db.commit()
        await db.refresh(request)
        return request

    # ------------------------------------------------------------------
    # Получение заявки по ID
    # ------------------------------------------------------------------
    @staticmethod
    async def get_request_by_id(
        db: AsyncSession,
        request_id: int,
    ) -> Optional[Request]:
        stmt = select(Request).where(Request.id == request_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Обновление заявки
    # ------------------------------------------------------------------
    @staticmethod
    async def update_request(
        db: AsyncSession,
        request: Request,
        data: RequestUpdate,
    ) -> Request:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(request, field, value)

        await db.commit()
        await db.refresh(request)
        return request

    # ------------------------------------------------------------------
    # Рассылка заявки в СТО (фиксируем distribution + статус заявки = SENT)
    # ------------------------------------------------------------------
    @staticmethod
    async def distribute_request_to_service_centers(
        db: AsyncSession,
        request_id: int,
        service_center_ids: List[int],
    ) -> Optional[Request]:
        request = await RequestsService.get_request_by_id(db, request_id)
        if not request:
            return None

        # удаляем старые записи распределения (на всякий)
        await db.execute(
            delete(RequestDistribution).where(RequestDistribution.request_id == request_id)
        )

        # создаём новые записи
        for sc_id in service_center_ids:
            dist = RequestDistribution(
                request_id=request_id,
                service_center_id=sc_id,
                status=RequestDistributionStatus.SENT,
            )
            db.add(dist)

        # обновляем статус заявки
        request.status = RequestStatus.SENT

        await db.commit()
        await db.refresh(request)
        return request

    # ------------------------------------------------------------------
    # Статусы заявки со стороны СТО + уведомления клиенту
    # ------------------------------------------------------------------
    @staticmethod
    async def set_in_work(
        db: AsyncSession,
        request_id: int,
        service_center_id: int,
    ) -> Optional[Request]:
        request = await RequestsService.get_request_by_id(db, request_id)
        if not request:
            return None

        if request.service_center_id != service_center_id:
            raise PermissionError("Service center has no access to this request")

        if request.status not in (RequestStatus.ACCEPTED_BY_SERVICE,):
            raise ValueError("Invalid status transition")

        request.status = RequestStatus.IN_WORK
        await db.commit()
        await db.refresh(request)

        if notifier.is_enabled():
            try:
                res_u = await db.execute(select(User).where(User.id == request.user_id))
                user = res_u.scalar_one_or_none()
                if user and getattr(user, "telegram_id", None) and WEBAPP_PUBLIC_URL:
                    url = f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}"
                    await notifier.send_notification(
                        recipient_type="client",
                        telegram_id=user.telegram_id,
                        message=f"🚗 Сервис взял вашу заявку №{request_id} в работу.",
                        buttons=[_btn_webapp("Открыть заявку", url)],
                        extra={"request_id": request_id, "service_center_id": service_center_id},
                    )
            except Exception:
                logger.exception("Notify client failed (IN_WORK), request_id=%s", request_id)

        return request

    @staticmethod
    async def set_done(
        db: AsyncSession,
        request_id: int,
        service_center_id: int,
        final_price: float | None,
    ) -> Optional[Request]:
        request = await RequestsService.get_request_by_id(db, request_id)
        if not request:
            return None

        if request.service_center_id != service_center_id:
            raise PermissionError("Service center has no access to this request")

        if request.status not in (RequestStatus.IN_WORK,):
            raise ValueError("Invalid status transition")

        request.status = RequestStatus.DONE
        request.final_price = final_price
        await db.commit()
        await db.refresh(request)

        if notifier.is_enabled():
            try:
                res_u = await db.execute(select(User).where(User.id == request.user_id))
                user = res_u.scalar_one_or_none()
                if user and getattr(user, "telegram_id", None) and WEBAPP_PUBLIC_URL:
                    url = f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}"
                    price_txt = f" Итоговая цена: {final_price:g}." if final_price is not None else ""
                    await notifier.send_notification(
                        recipient_type="client",
                        telegram_id=user.telegram_id,
                        message=f"✅ Заявка №{request_id} завершена.{price_txt}",
                        buttons=[_btn_webapp("Открыть заявку", url)],
                        extra={"request_id": request_id, "service_center_id": service_center_id},
                    )
            except Exception:
                logger.exception("Notify client failed (DONE), request_id=%s", request_id)

        return request

    @staticmethod
    async def reject_by_service(
        db: AsyncSession,
        request_id: int,
        service_center_id: int,
        reason: str | None,
    ) -> Optional[Request]:
        request = await RequestsService.get_request_by_id(db, request_id)
        if not request:
            return None

        if request.service_center_id != service_center_id:
            raise PermissionError("Service center has no access to this request")

        if request.status not in (RequestStatus.ACCEPTED_BY_SERVICE, RequestStatus.IN_WORK):
            raise ValueError("Invalid status transition")

        request.status = RequestStatus.REJECTED_BY_SERVICE
        request.reject_reason = (reason or "").strip() or None
        await db.commit()
        await db.refresh(request)

        if notifier.is_enabled():
            try:
                res_u = await db.execute(select(User).where(User.id == request.user_id))
                user = res_u.scalar_one_or_none()
                if user and getattr(user, "telegram_id", None) and WEBAPP_PUBLIC_URL:
                    url = f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}"
                    reason_txt = f" Причина: {request.reject_reason}" if request.reject_reason else ""
                    await notifier.send_notification(
                        recipient_type="client",
                        telegram_id=user.telegram_id,
                        message=f"❌ Сервис отказался от заявки №{request_id}.{reason_txt}",
                        buttons=[_btn_webapp("Открыть заявку", url)],
                        extra={"request_id": request_id, "service_center_id": service_center_id},
                    )
            except Exception:
                logger.exception("Notify client failed (REJECTED), request_id=%s", request_id)

        return request

    # ------------------------------------------------------------------
    # НОВОЕ: список заявок для конкретного СТО (только "его" заявки)
    # ------------------------------------------------------------------
    @staticmethod
    async def list_requests_for_service_center(
        db: AsyncSession,
        service_center_id: int,
    ) -> List[Request]:
        """
        Возвращаем:
        - только те заявки, которые были отправлены этому service_center_id;
        - фильтруем по статусам (new, sent, in_work);
        - сортируем по дате создания (новые сверху).
        """
        active_statuses = [
            RequestStatus.NEW,
            RequestStatus.SENT,
            RequestStatus.IN_WORK,
        ]

        stmt = (
            select(Request)
            .join(
                RequestDistribution,
                RequestDistribution.request_id == Request.id,
            )
            .where(
                RequestDistribution.service_center_id == service_center_id,
                Request.status.in_(active_statuses),
            )
            .order_by(Request.created_at.desc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())
