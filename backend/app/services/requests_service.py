from __future__ import annotations

import logging
import os
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.app.services.user_service import UsersService
from backend.app.services.bonus_service import BonusService

from backend.app.models.offer import Offer, OfferStatus
from backend.app.models.bonus import BonusTransaction, BonusReason

from backend.app.core.notifier import BotNotifier
from backend.app.models import (
    Request,
    RequestDistribution,
    RequestDistributionStatus,
    RequestStatus,
    ServiceCenter,
    User,
)
from backend.app.schemas.request import RequestCreate, RequestUpdate

logger = logging.getLogger(__name__)

WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").rstrip("/")
notifier = BotNotifier()


def _btn_webapp(text: str, url: str) -> dict[str, str]:
    # бот умеет интерпретировать type=web_app и открывать миниапп, а не браузер
    return {"text": text, "type": "web_app", "url": url}


class RequestsService:
    """
    Сервисный слой для заявок.

    ВАЖНО: сигнатуры методов сделаны совместимыми с backend/app/api/v1/requests.py
    """

    # ------------------------------------------------------------------
    # Создание
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Получение по ID
    # ------------------------------------------------------------------
    @staticmethod
    async def get_request_by_id(db: AsyncSession, request_id: int) -> Optional[Request]:
        stmt = select(Request).where(Request.id == request_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Списки
    # ------------------------------------------------------------------
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
    async def list_requests(
        db: AsyncSession,
        status: str | None = None,
    ) -> List[Request]:
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

    # ------------------------------------------------------------------
    # Обновление
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Рассылка по СТО
    # ------------------------------------------------------------------
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
    async def send_request_to_all_service_centers(
        db: AsyncSession,
        *,
        request_id: int,
        service_centers: List[ServiceCenter],
    ) -> Optional[Request]:
        """
        "Отправить всем" =
        1) фиксируем RequestDistribution для всех найденных СТО
        2) ставим статус заявки SENT
        3) отправляем уведомления владельцам СТО через bot notify API (если включён)

        ВАЖНО:
        - строгий отбор по радиусу/гео делается ДО вызова (в роутере)
        - здесь не делаем fallback логики
        """

        # Грузим заявку вместе с авто (без lazy-load)
        stmt = select(Request).options(selectinload(Request.car)).where(Request.id == request_id)
        res = await db.execute(stmt)
        req = res.scalar_one_or_none()
        if not req:
            return None

        final_ids: list[int] = [int(sc.id) for sc in (service_centers or []) if sc and getattr(sc, "id", None)]
        final_ids = sorted(set(final_ids))
        if not final_ids:
            # ничего не делаем — пусть роутер сам решает, что показать пользователю
            return req

        distributed = await RequestsService.distribute_request_to_service_centers(
            db,
            request_id=request_id,
            service_center_ids=final_ids,
        )

        if notifier.is_enabled() and WEBAPP_PUBLIC_URL:
            # 🔒 ВАЖНО: НИКАКИХ sc.owner (relationship) — иначе MissingGreenlet
            user_ids: list[int] = []
            for sc in (service_centers or []):
                uid = getattr(sc, "user_id", None)
                if uid:
                    user_ids.append(int(uid))
            user_ids = sorted(set(user_ids))

            tg_map: dict[int, int] = {}
            if user_ids:
                users_res = await db.execute(select(User.id, User.telegram_id).where(User.id.in_(user_ids)))
                for uid, tg_id in users_res.all():
                    if tg_id:
                        tg_map[int(uid)] = int(tg_id)

            # formatter подключаем безопасно
            try:
                from backend.app.core.notify_formatters import build_sc_new_request_message
            except Exception:
                build_sc_new_request_message = None  # type: ignore

            for sc in service_centers:
                if not sc:
                    continue

                uid = getattr(sc, "user_id", None)
                owner_tg = tg_map.get(int(uid)) if uid else None
                if not owner_tg:
                    continue

                url = f"{WEBAPP_PUBLIC_URL}/sc/{sc.id}/requests/{request_id}"

                # fallback (старый стиль) — чтобы ничего не ломать при ошибках форматтера
                message = f"📩 Вам отправлена заявка №{request_id}"
                buttons = [_btn_webapp("Открыть заявку", url)]
                extra = {
                    "request_id": request_id,
                    "service_center_id": int(sc.id),
                    "kind": "send_to_all",
                }

                # новый “человеческий” формат
                if build_sc_new_request_message:
                    try:
                        fmt_message, fmt_buttons, fmt_extra = build_sc_new_request_message(
                            request_obj=req,
                            service_center=sc,
                            car=getattr(req, "car", None),
                            webapp_public_url=WEBAPP_PUBLIC_URL,
                        )
                        if fmt_message:
                            message = fmt_message
                        if fmt_buttons:
                            buttons = fmt_buttons
                        if fmt_extra:
                            extra.update(fmt_extra)
                        extra["kind"] = "send_to_all"
                    except Exception:
                        logger.exception(
                            "notify formatter failed (request_id=%s, service_center_id=%s)",
                            request_id,
                            getattr(sc, "id", None),
                        )

                try:
                    await notifier.send_notification(
                        recipient_type="service_center",
                        telegram_id=int(owner_tg),
                        message=message,
                        buttons=buttons,
                        extra=extra,
                    )
                except Exception:
                    logger.exception(
                        "send_to_all notify failed (request_id=%s, service_center_id=%s)",
                        request_id,
                        getattr(sc, "id", None),
                    )

        return distributed

    # ------------------------------------------------------------------
    # В работу
    # ------------------------------------------------------------------
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
        # BONUS HIDDEN MODE: полностью отключаем авто-начисления
        from backend.app.core.config import settings
        if settings.BONUS_HIDDEN_MODE:
            return

        if req.status != RequestStatus.DONE:
            return
        if req.final_price is None:
            return

        # ищем принятый оффер
        result = await db.execute(
            select(Offer).where(
                Offer.request_id == req.id,
                Offer.status == OfferStatus.accepted,
            )
        )
        offer: Offer | None = result.scalar_one_or_none()
        if not offer:
            return

        pct_raw = getattr(offer, "cashback_percent", None)
        if pct_raw is None:
            return
        try:
            pct = float(pct_raw)
        except Exception:
            return
        if pct <= 0:
            return

        # защита от дублей
        result = await db.execute(
            select(BonusTransaction.id).where(
                BonusTransaction.user_id == req.user_id,
                BonusTransaction.reason == BonusReason.COMPLETE_REQUEST,
                BonusTransaction.request_id == req.id,
                BonusTransaction.offer_id == offer.id,
            )
        )
        already_awarded = result.scalar_one_or_none() is not None
        if already_awarded:
            return

        bonus_spent_raw = getattr(req, "bonus_spent", 0) or 0
        try:
            bonus_spent = float(bonus_spent_raw)
        except Exception:
            bonus_spent = 0.0

        base = float(req.final_price) - bonus_spent
        if base <= 0:
            return

        amount = int(base * pct / 100.0)
        if amount <= 0:
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

    # ------------------------------------------------------------------
    # Завершить
    # ------------------------------------------------------------------
    @staticmethod
    async def set_done(
        db: AsyncSession,
        request_id: int,
        service_center_id: int,
        *,
        final_price: float | None = None,
        final_price_text: str | None = None,
        notify_client_telegram_id: int | None = None,
    ) -> Optional[Request]:
        import re

        def _parse_first_number(text: str | None) -> float | None:
            if not text:
                return None
            t = text.replace("\u00a0", "").replace(" ", "").replace(",", ".")
            m = re.search(r"(\d+(?:\.\d+)?)", t)
            if not m:
                return None
            try:
                return float(m.group(1))
            except Exception:
                return None

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

        if final_price_text is not None:
            req.final_price_text = final_price_text

        # backward compat: если число можно вытащить из текста — кладём в старое final_price
        if final_price is None and final_price_text:
            parsed = _parse_first_number(final_price_text)
            if parsed is not None:
                final_price = parsed

        if final_price is not None:
            req.final_price = float(final_price)

        await db.commit()
        await db.refresh(req)

        # ✅ начисляем кэшбек (внутри есть BONUS_HIDDEN_MODE guard)
        try:
            await RequestsService._award_cashback_if_needed(db, req)
        except Exception:
            logger.exception("cashback award failed for request_id=%s", request_id)

        # --- уведомление клиенту ---
        tg_id = notify_client_telegram_id
        if tg_id is None:
            client = await UsersService.get_by_id(db, req.user_id)
            tg_id = getattr(client, "telegram_id", None) if client else None

        if notifier.is_enabled() and WEBAPP_PUBLIC_URL and tg_id:
            text_price = ""
            if getattr(req, "final_price_text", None):
                text_price = f"\n💰 Итоговая цена: {req.final_price_text}"
            elif req.final_price is not None:
                text_price = f"\n💰 Итоговая цена: {req.final_price:.0f}"

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
    ) -> Optional[Request]:
        req = await RequestsService.get_request_by_id(db, request_id)
        if not req:
            return None

        # Закрывать может только назначенное СТО
        if req.service_center_id != service_center_id:
            raise PermissionError("No access to this request")

        # Нельзя закрывать, если уже закрыта
        if req.status in [RequestStatus.DONE, RequestStatus.CANCELLED, RequestStatus.REJECTED_BY_SERVICE]:
            raise ValueError("Invalid status transition")

        req.status = RequestStatus.REJECTED_BY_SERVICE
        clean_reason = (reason or "").strip()
        req.reject_reason = clean_reason or None

        await db.commit()
        await db.refresh(req)

        # уведомление клиенту (не должно ломать основной сценарий)
        try:
            client = await UsersService.get_by_id(db, req.user_id)
            tg_id = getattr(client, "telegram_id", None) if client else None
            if notifier.is_enabled() and WEBAPP_PUBLIC_URL and tg_id:
                msg = f"⛔ Сервис закрыл заявку №{request_id}."
                if req.reject_reason:
                    msg += f"\nПричина: {req.reject_reason}"
                await notifier.send_notification(
                    recipient_type="client",
                    telegram_id=int(tg_id),
                    message=msg,
                    buttons=[_btn_webapp("Открыть заявку", f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}")],
                    extra={"request_id": request_id, "status": "REJECTED_BY_SERVICE"},
                )
        except Exception:
            logger.exception("reject_by_service notify failed (request_id=%s)", request_id)

        return req
