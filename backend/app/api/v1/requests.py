from typing import List, Optional
import os
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.notifier import BotNotifier
from backend.app.schemas.request import (
    RequestCreate,
    RequestRead,
    RequestUpdate,
)
from backend.app.schemas.request_distribution import RequestDistributeIn
from backend.app.services.requests_service import RequestsService
from backend.app.services.service_centers_service import ServiceCentersService
from backend.app.core.catalogs.service_categories import (
    get_specializations_for_category,
    SERVICE_CATEGORY_LABELS,
)
from backend.app.services.user_service import UsersService


from backend.app.models import ServiceCenter

router = APIRouter(
    prefix="/requests",
    tags=["requests"],
)

WEBAPP_PUBLIC_URL = os.getenv("WEBAPP_PUBLIC_URL", "").rstrip("/")
notifier = BotNotifier()


# ---------------------------------------------------------------------------
# Создание заявки
# ---------------------------------------------------------------------------
@router.post(
    "/",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_request(
    request_in: RequestCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создать новую заявку.

    Статус заявки по умолчанию: NEW.
    """
    request = await RequestsService.create_request(db, request_in)
    return request


# ---------------------------------------------------------------------------
# ОТПРАВКА ЗАЯВКИ ВСЕМ ПОДХОДЯЩИМ СТО
# ---------------------------------------------------------------------------
@router.post(
    "/{request_id}/send_to_all",
    response_model=RequestRead,
    status_code=status.HTTP_200_OK,
)
async def send_request_to_all_service_centers(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    request_obj = await RequestsService.get_request_by_id(db, request_id)
    if not request_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    # Жёстко: рассылка только при гео + радиус
    if request_obj.latitude is None or request_obj.longitude is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужно указать геолокацию заявки, чтобы разослать всем СТО.",
        )
    if request_obj.radius_km is None or request_obj.radius_km <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужно выбрать радиус поиска, чтобы разослать всем СТО.",
        )

    specializations = [request_obj.service_category] if request_obj.service_category else None

    service_centers = await ServiceCentersService.search_service_centers(
        db,
        latitude=request_obj.latitude,
        longitude=request_obj.longitude,
        radius_km=request_obj.radius_km,
        specializations=specializations,
        is_active=True,
        fallback_to_category=False,  # 👈 важно
    )

    if not service_centers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="В выбранном радиусе нет подходящих СТО. Увеличьте радиус или выберите СТО из списка.",
        )

    await RequestsService.send_request_to_all_service_centers(
        db, request_id=request_id, service_centers=service_centers
    )

    return await RequestsService.get_request_by_id(db, request_id)


# ---------------------------------------------------------------------------
# ОТПРАВКА ЗАЯВКИ ОДНОМУ ВЫБРАННОМУ СТО
# ---------------------------------------------------------------------------
@router.post(
    "/{request_id}/send_to_service_center",
    response_model=RequestRead,
    status_code=status.HTTP_200_OK,
)
async def send_to_one_service(
    request_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    sc_id = data.get("service_center_id")
    if not sc_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="service_center_id is required",
        )

    service_center = await ServiceCentersService.get_by_id(db, sc_id)
    if not service_center or not service_center.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service center not found or inactive",
        )

    request = await RequestsService.distribute_request_to_service_centers(
        db,
        request_id=request_id,
        service_center_ids=[sc_id],
    )
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    owner = service_center.owner
    if notifier.is_enabled() and WEBAPP_PUBLIC_URL and owner and getattr(owner, "telegram_id", None):
        cat_code = request.service_category or "—"
        cat_label = SERVICE_CATEGORY_LABELS.get(cat_code, cat_code)

        url = f"{WEBAPP_PUBLIC_URL}/sc/{service_center.id}/requests/{request_id}"
        message = (
            f"📩 Вам отправлена заявка №{request_id}\n"
            f"Категория: {cat_label}"
        )

        await notifier.send_notification(
            recipient_type="service_center",
            telegram_id=owner.telegram_id,
            message=message,
            buttons=[
                {"text": "Открыть заявку", "type": "web_app", "url": url},
            ],
            extra={
                "request_id": request_id,
                "service_center_id": service_center.id,
            },
        )

    return request


# ---------------------------------------------------------------------------
# (СТАРОЕ) Список заявок для СТО по специализациям
# Сейчас в боте почти не используется, оставляем для совместимости.
# ---------------------------------------------------------------------------
@router.get(
    "/for-service-centers",
    response_model=List[RequestRead],
)
async def get_requests_for_service_centers(
    specializations: List[str] | None = Query(
        None,
        description="Коды специализаций СТО (tire, mechanic и т.п.)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Список заявок для просмотра СТО (старый режим, по специализациям).

    Если переданы specializations — вернём только заявки с такими категориями.
    """
    requests = await RequestsService.list_requests_for_service_centers_by_specializations(
        db,
        specializations=specializations,
    )
    return requests


# ---------------------------------------------------------------------------
# ЯВНОЕ распределение заявки по конкретным СТО (список ID)
# ---------------------------------------------------------------------------
@router.post(
    "/{request_id}/distribute",
    response_model=RequestRead,
    status_code=status.HTTP_200_OK,
)
async def distribute_request_to_service_centers(
    request_id: int,
    payload: RequestDistributeIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Зафиксировать, каким СТО была отправлена заявка.

    Ожидает тело:
    {
        "service_center_ids": [1, 2, 3]
    }
    """
    request = await RequestsService.distribute_request_to_service_centers(
        db,
        request_id=request_id,
        service_center_ids=payload.service_center_ids,
    )
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return request


# ---------------------------------------------------------------------------
# НОВОЕ: список заявок для конкретного СТО (по RequestDistribution)
# ---------------------------------------------------------------------------
@router.get(
    "/for-service-center/{service_center_id}",
    response_model=List[RequestRead],
)
async def get_requests_for_service_center(
    service_center_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Список заявок, которые были разосланы КОНКРЕТНОМУ СТО.

    Использует RequestDistribution, поэтому:
    - СТО видит только те заявки, которые реально ему отправили.
    """
    requests = await RequestsService.list_requests_for_service_center(
        db,
        service_center_id=service_center_id,
    )
    return requests


# ---------------------------------------------------------------------------
# Список заявок по пользователю
# ---------------------------------------------------------------------------
@router.get(
    "/by-user/{user_id}",
    response_model=List[RequestRead],
)
async def get_requests_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список заявок конкретного пользователя.
    """
    requests = await RequestsService.list_requests_by_user(db, user_id)
    return requests


# ---------------------------------------------------------------------------
# Список ВСЕХ заявок (опционально по статусу)
# ---------------------------------------------------------------------------
@router.get(
    "/",
    response_model=List[RequestRead],
)
async def list_requests(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Фильтр по статусу заявки (new, sent, in_work, done и т.п.)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Список всех заявок, опционально по статусу.
    """
    requests = await RequestsService.list_requests(db, status=status_filter)
    return requests


# ---------------------------------------------------------------------------
# Получить заявку по ID
# ---------------------------------------------------------------------------
@router.get(
    "/{request_id}",
    response_model=RequestRead,
)
async def get_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить заявку по ID.
    """
    request = await RequestsService.get_request_by_id(db, request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return request


# ---------------------------------------------------------------------------
# Частичное обновление заявки
# ---------------------------------------------------------------------------
@router.patch(
    "/{request_id}",
    response_model=RequestRead,
)
async def update_request(
    request_id: int,
    request_in: RequestUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Частичное обновление заявки.

    ⚠️ Логику изменения статусов лучше делать
    через специализированные эндпоинты, а не здесь.
    """
    request = await RequestsService.update_request(db, request_id, request_in)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return request


class ScActionIn(BaseModel):
    service_center_id: int


class ScDoneIn(BaseModel):
    service_center_id: int
    final_price_text: str | None = None
    final_price: float | None = None


class ScRejectIn(BaseModel):
    service_center_id: int
    reason: str | None = None


@router.post("/{request_id}/set_in_work", response_model=RequestRead)
async def set_in_work(
    request_id: int,
    payload: ScActionIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        req = await RequestsService.set_in_work(db, request_id, payload.service_center_id)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        return req
    except PermissionError:
        raise HTTPException(status_code=403, detail="No access to this request")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status transition")


@router.post("/{request_id}/set_done", response_model=RequestRead)
async def set_done(
    request_id: int,
    payload: ScDoneIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        req = await RequestsService.set_done(
            db,
            request_id,
            payload.service_center_id,
            final_price=payload.final_price,            # keyword-arg
            final_price_text=payload.final_price_text,  # ✅ ВАЖНО: текст тоже сохраняем
        )
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        return req
    except PermissionError:
        raise HTTPException(status_code=403, detail="No access to this request")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status transition")


@router.post("/{request_id}/reject_by_service", response_model=RequestRead)
async def reject_by_service(
    request_id: int,
    payload: ScRejectIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        req = await RequestsService.reject_by_service(
            db,
            request_id,
            payload.service_center_id,
            reason=payload.reason,  # ВАЖНО: keyword-arg
        )
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        return req
    except PermissionError:
        raise HTTPException(status_code=403, detail="No access to this request")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status transition")


class SendChatLinkIn(BaseModel):
    service_center_id: int
    recipient: str  # "client" | "service_center"


@router.post("/{request_id}/send_chat_link")
async def send_chat_link(
    request_id: int,
    payload: SendChatLinkIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Отправляет пользователю сообщение в Telegram (через bot notify API) с кнопкой,
    которая открывает ПРЯМОЙ чат с другой стороной (tg://user?id=...).

    recipient:
      - "client"        -> сообщение уйдёт клиенту, кнопка откроет чат с владельцем СТО
      - "service_center"-> сообщение уйдёт владельцу СТО, кнопка откроет чат с клиентом
    """
    notifier = BotNotifier()
    if not notifier.is_enabled():
        return {"ok": False, "detail": "Notifier disabled (BOT_API_URL is not set)"}

    req = await RequestsService.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    sc = await ServiceCentersService.get_by_id(db, payload.service_center_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Service center not found")

    recipient = (payload.recipient or "").strip().lower()

    # target_tg = кому отправляем сообщение
    # peer_tg   = с кем открываем прямой чат
    target_tg: int
    peer_tg: int
    message: str

    if recipient == "client":
        # сообщение клиенту -> чат с владельцем СТО
        user = await UsersService.get_by_id(db, req.user_id)
        client_tg = getattr(user, "telegram_id", None) if user else None
        if not client_tg:
            raise HTTPException(status_code=400, detail="Client has no telegram_id")

        owner = await UsersService.get_by_id(db, sc.user_id)
        owner_tg = getattr(owner, "telegram_id", None) if owner else None
        if not owner_tg:
            raise HTTPException(status_code=400, detail="Service center owner has no telegram_id")

        target_tg = int(client_tg)
        peer_tg = int(owner_tg)
        message = f"💬 Нажмите кнопку ниже, чтобы открыть прямой чат с сервисом по заявке №{request_id}."

    elif recipient == "service_center":
        # сообщение владельцу СТО -> чат с клиентом
        owner = await UsersService.get_by_id(db, sc.user_id)
        owner_tg = getattr(owner, "telegram_id", None) if owner else None
        if not owner_tg:
            raise HTTPException(status_code=400, detail="Service center owner has no telegram_id")

        user = await UsersService.get_by_id(db, req.user_id)
        client_tg = getattr(user, "telegram_id", None) if user else None
        if not client_tg:
            raise HTTPException(status_code=400, detail="Client has no telegram_id")

        target_tg = int(owner_tg)
        peer_tg = int(client_tg)
        message = f"💬 Нажмите кнопку ниже, чтобы открыть прямой чат с клиентом по заявке №{request_id}."

    else:
        raise HTTPException(status_code=422, detail="recipient must be 'client' or 'service_center'")

    # ✅ прямой чат
    url = f"tg://user?id={peer_tg}"

    await notifier.send_notification(
        recipient_type=recipient,
        telegram_id=target_tg,
        message=message,
        buttons=[
            {"text": "💬 Открыть чат в Telegram", "type": "url", "url": url},
        ],
        extra={
            "request_id": request_id,
            "service_center_id": payload.service_center_id,
            "kind": "direct_chat_link",
            "peer_telegram_id": peer_tg,
        },
    )

    return {"ok": True, "url": url, "peer_telegram_id": peer_tg}
