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
from backend.app.core.catalogs.service_categories import get_specializations_for_category

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
    """
    Отправка заявки всем подходящим СТО.

    1) Берём заявку по ID.
    2) Определяем спец-коды по категории заявки.
    3) Ищем подходящие СТО (по гео/радиусу/категориям).
    4) Фиксируем распределение через RequestsService.distribute_request_to_service_centers.
    5) Отправляем уведомления СТО (если настроен BOT_API_URL).
    """
    request = await RequestsService.get_request_by_id(db, request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    # Специализации по категории заявки (см. catalogs.service_categories)
    spec_codes = get_specializations_for_category(request.service_category)

    # Если категорию не знаем и это не 'sto' — пробуем 1:1
    if spec_codes is None and request.service_category and request.service_category not in ("sto",):
        spec_codes = [request.service_category]

    specializations = spec_codes or None

    # Ищем подходящие СТО
    service_centers: List[ServiceCenter] = await ServiceCentersService.search_service_centers(
        db,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_km=request.radius_km,
        specializations=specializations,
        is_active=True,
    )

    service_center_ids = [sc.id for sc in service_centers]

    if not service_center_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No service centers found for this request",
        )

    # Фиксируем распределение (создаём RequestDistribution и ставим статус SENT)
    distributed_request = await RequestsService.distribute_request_to_service_centers(
        db,
        request_id=request_id,
        service_center_ids=service_center_ids,
    )

    # Уведомляем все СТО о новой заявке
    if notifier.is_enabled() and WEBAPP_PUBLIC_URL:
        for sc in service_centers:
            owner = sc.owner  # User-модель владельца
            if not owner or not getattr(owner, "telegram_id", None):
                continue

            # Ссылка для СТО на деталку заявки в кабинете сервиса
            url = f"{WEBAPP_PUBLIC_URL}/sc/{sc.id}/requests/{request_id}"

            message = (
                f"🆕 У вас новая заявка №{request_id}\n"
                f"Категория: {request.service_category or 'не указана'}"
            )

            await notifier.send_notification(
                recipient_type="service_center",
                telegram_id=owner.telegram_id,
                message=message,
                buttons=[
                    {"text": "Открыть заявку в веб-приложении", "url": url},
                ],
                extra={
                    "request_id": request_id,
                    "service_center_id": sc.id,
                },
            )

    return distributed_request


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
    """
    Отправить заявку ОДНОМУ выбранному СТО.

    Ожидает тело:
    {
        "service_center_id": 5
    }

    Поведение:
    - фиксируем распределение только к одному СТО,
    - уведомляем этот сервис о новой заявке.
    """
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

    # Уведомляем СТО
    owner = service_center.owner
    if notifier.is_enabled() and WEBAPP_PUBLIC_URL and owner and getattr(owner, "telegram_id", None):
        url = f"{WEBAPP_PUBLIC_URL}/sc/{service_center.id}/requests/{request_id}"
        message = (
            f"📩 Вам отправлена заявка №{request_id}\n"
            f"Категория: {request.service_category or 'не указана'}"
        )

        await notifier.send_notification(
            recipient_type="service_center",
            telegram_id=owner.telegram_id,
            message=message,
            buttons=[
                {"text": "Открыть заявку в веб-приложении", "url": url},
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
        req = await RequestsService.set_done(db, request_id, payload.service_center_id, payload.final_price)
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
        req = await RequestsService.reject_by_service(db, request_id, payload.service_center_id, payload.reason)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        return req
    except PermissionError:
        raise HTTPException(status_code=403, detail="No access to this request")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status transition")