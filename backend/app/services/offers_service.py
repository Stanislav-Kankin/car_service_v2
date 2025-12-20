from typing import List, Optional
import os
import re
import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.models.offer import Offer, OfferStatus
from backend.app.models.request import RequestStatus, Request
from backend.app.models.service_center import ServiceCenter
from backend.app.core.notifier import BotNotifier

WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").rstrip("/")
notifier = BotNotifier()

_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _normalize_num_text(s: str) -> str:
    return (
        s.replace("\u00a0", "")  # nbsp
        .replace(" ", "")
        .replace(",", ".")
        .strip()
    )


def _parse_price_to_float(price_text: str | None) -> float | None:
    if not price_text:
        return None
    t = _normalize_num_text(price_text.lower())
    nums = _NUM_RE.findall(t)
    if not nums:
        return None
    try:
        return float(nums[0])
    except Exception:
        return None


def _parse_eta_to_hours(eta_text: str | None) -> int | None:
    if not eta_text:
        return None
    t = eta_text.lower()

    # минут(ы)
    m = re.search(r"(\d+)\s*(?:мин|минута|минуты|минут|m)\b", t)
    if m:
        minutes = int(m.group(1))
        return max(1, int(math.ceil(minutes / 60)))

    # часов
    h = re.search(r"(\d+)\s*(?:час|часа|часов|ч|h)\b", t)
    if h:
        return max(1, int(h.group(1)))

    # дней
    d = re.search(r"(\d+)\s*(?:дн|день|дня|дней|day|days)\b", t)
    if d:
        days = int(d.group(1))
        return max(1, days * 24)

    # если просто число без единиц — трактуем как часы
    bare = re.search(r"\b(\d+)\b", t)
    if bare:
        return max(1, int(bare.group(1)))

    return None


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
        """
        BONUS_HIDDEN_MODE:
          - cashback_percent игнорируем (не сохраняем)
        Backward compat:
          - если можно распарсить price_text/eta_text — заполняем старые price/eta_hours
        """
        price_text = data.get("price_text")
        eta_text = data.get("eta_text")

        # старые поля (fallback / совместимость)
        price = data.get("price")
        eta_hours = data.get("eta_hours")

        if price is None and price_text:
            parsed_price = _parse_price_to_float(price_text)
            if parsed_price is not None:
                price = parsed_price

        if eta_hours is None and eta_text:
            parsed_eta = _parse_eta_to_hours(eta_text)
            if parsed_eta is not None:
                eta_hours = parsed_eta

        cashback_percent = data.get("cashback_percent")
        if settings.BONUS_HIDDEN_MODE:
            cashback_percent = None

        data_clean = {
            "request_id": data["request_id"],
            "service_center_id": data["service_center_id"],

            # новые поля
            "price_text": price_text,
            "eta_text": eta_text,

            # старые поля
            "price": price,
            "eta_hours": eta_hours,

            "comment": data.get("comment"),
            "cashback_percent": cashback_percent,
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
        from backend.app.core.config import settings

        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None

        # BONUS_HIDDEN_MODE: запрещаем менять cashback_percent (и любую бонусную историю)
        if settings.BONUS_HIDDEN_MODE and "cashback_percent" in data:
            data["cashback_percent"] = None

        changed: dict[str, tuple[object, object]] = {}

        for field, value in data.items():
            if value is None:
                continue
            if field == "status":
                continue

            old_val = getattr(offer, field, None)
            if old_val != value:
                changed[field] = (old_val, value)
                setattr(offer, field, value)

        # Если изменений нет — без коммита и без лишних уведомлений
        if not changed:
            return offer

        await db.commit()
        await db.refresh(offer)

        # --- Уведомление клиента об обновлении оффера ---
        try:
            offer_full = await OffersService.get_offer_by_id(db, offer.id)
            if offer_full and offer_full.request and offer_full.request.user:
                client = offer_full.request.user
                if notifier.is_enabled() and getattr(client, "telegram_id", None):
                    request_id = offer_full.request.id
                    url = f"{WEBAPP_PUBLIC_URL}/me/requests/{request_id}"

                    sc_name = None
                    if offer_full.service_center:
                        sc_name = getattr(offer_full.service_center, "name", None)

                    price_line = None
                    if getattr(offer_full, "price_text", None):
                        price_line = f"💰 Стоимость: {offer_full.price_text}"
                    elif getattr(offer_full, "price", None) is not None:
                        price_line = f"💰 Стоимость: {offer_full.price}"

                    eta_line = None
                    if getattr(offer_full, "eta_text", None):
                        eta_line = f"⏱ Срок: {offer_full.eta_text}"
                    elif getattr(offer_full, "eta_hours", None) is not None:
                        eta_line = f"⏱ Срок: ~{offer_full.eta_hours} ч."

                    comment = getattr(offer_full, "comment", None)
                    if comment:
                        comment = str(comment).strip()
                        if len(comment) > 220:
                            comment = comment[:220] + "…"

                    lines = [
                        f"✏️ Отклик по заявке №{request_id} обновлён.",
                    ]
                    if sc_name:
                        lines.append(f"🏁 Сервис: {sc_name}")
                    if price_line:
                        lines.append(price_line)
                    if eta_line:
                        lines.append(eta_line)
                    if comment:
                        lines.append(f"💬 Комментарий: {comment}")

                    await notifier.send_notification(
                        recipient_type="client",
                        telegram_id=int(client.telegram_id),
                        message="\n".join(lines),
                        buttons=[
                            {"text": "Открыть заявку", "type": "web_app", "url": url},
                        ],
                        extra={"request_id": request_id, "offer_id": offer.id, "event": "offer_updated"},
                    )
        except Exception:
            # уведомления не должны ломать основной сценарий
            pass

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
        5) Обновить RequestDistribution:
            - winner = WINNER
            - остальные = DECLINED
        6) Уведомить:
            - выбранному СТО: "ваше предложение выбрано"
            - остальным СТО: "клиент выбрал другой сервис"
            - клиенту: подтверждение
        """
        from backend.app.models.request_distribution import RequestDistribution, RequestDistributionStatus

        offer = await OffersService.get_offer_by_id(db, offer_id)
        if not offer:
            return None

        req = offer.request
        if not req:
            return None

        request_id = req.id
        winner_sc_id = int(offer.service_center_id)

        # --- проставим всем офферам статус ---
        stmt = select(Offer).where(Offer.request_id == request_id)
        res = await db.execute(stmt)
        offers = list(res.scalars().all())

        for o in offers:
            o.status = OfferStatus.REJECTED
        offer.status = OfferStatus.ACCEPTED

        # --- request -> выбранный сервис ---
        req.service_center_id = winner_sc_id
        req.status = RequestStatus.ACCEPTED_BY_SERVICE

        # --- обновим RequestDistribution (если записи есть) ---
        other_sc_ids: list[int] = []
        try:
            dist_stmt = select(RequestDistribution).where(RequestDistribution.request_id == request_id)
            dist_res = await db.execute(dist_stmt)
            dists = list(dist_res.scalars().all())

            for d in dists:
                if int(d.service_center_id) == winner_sc_id:
                    d.status = RequestDistributionStatus.WINNER
                else:
                    d.status = RequestDistributionStatus.DECLINED
                    other_sc_ids.append(int(d.service_center_id))
        except Exception:
            # distribution — вспомогательная часть, не должна ломать принятие оффера
            other_sc_ids = []

        await db.commit()
        await db.refresh(offer)

        # --- уведомления ---
        offer_full = await OffersService.get_offer_by_id(db, offer.id)
        if offer_full and notifier.is_enabled():
            # 1) победителю (как было)
            try:
                if (
                    offer_full.service_center
                    and offer_full.service_center.owner
                    and getattr(offer_full.service_center.owner, "telegram_id", None)
                ):
                    sc_owner_tg = int(offer_full.service_center.owner.telegram_id)
                    url_sc = f"{WEBAPP_PUBLIC_URL}/sc/{winner_sc_id}/requests/{request_id}"
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
                        extra={"request_id": request_id, "offer_id": offer_id, "event": "offer_accepted_winner"},
                    )
            except Exception:
                pass

            # 2) остальным СТО — отбивка
            # Берём СТО + владельцев пачкой, чтобы не делать N запросов
            try:
                if other_sc_ids:
                    sc_stmt = (
                        select(ServiceCenter)
                        .where(ServiceCenter.id.in_(other_sc_ids))
                        .options(selectinload(ServiceCenter.owner))
                    )
                    sc_res = await db.execute(sc_stmt)
                    other_scs = list(sc_res.scalars().all())

                    for sc in other_scs:
                        owner = getattr(sc, "owner", None)
                        owner_tg = getattr(owner, "telegram_id", None) if owner else None
                        if not owner_tg:
                            continue

                        url_sc = f"{WEBAPP_PUBLIC_URL}/sc/{int(sc.id)}/requests/{request_id}"
                        await notifier.send_notification(
                            recipient_type="service_center",
                            telegram_id=int(owner_tg),
                            message=(
                                f"ℹ️ Клиент выбрал другой сервис по заявке №{request_id}.\n"
                                f"Спасибо за отклик!"
                            ),
                            buttons=[
                                {"text": "Открыть заявку", "type": "web_app", "url": url_sc},
                            ],
                            extra={
                                "request_id": request_id,
                                "offer_id": offer_id,
                                "event": "offer_accepted_declined",
                                "winner_service_center_id": winner_sc_id,
                                "service_center_id": int(sc.id),
                            },
                        )
            except Exception:
                pass

            # 3) клиенту (как было)
            try:
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
                        extra={"request_id": request_id, "offer_id": offer_id, "event": "offer_accepted_client"},
                    )
            except Exception:
                pass

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
