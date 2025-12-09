from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    Request,
    RequestStatus,
    RequestDistribution,
    RequestDistributionStatus,
)
from backend.app.schemas.request import (
    RequestCreate,
    RequestRead,
    RequestUpdate,
)


class RequestsService:
    """
    Сервисный слой для работы с заявками.
    """

    # ------------------------------------------------------------------
    # Создание заявки
    # ------------------------------------------------------------------
    @staticmethod
    async def create_request(
        db: AsyncSession,
        data: RequestCreate,
    ) -> Request:
        """
        Создать новую заявку.

        Ожидается, что RequestCreate содержит поля:
        - user_id: int
        - car_id: Optional[int]
        - latitude: Optional[float]
        - longitude: Optional[float]
        - address_text: Optional[str]
        - is_car_movable: bool
        - need_tow_truck: bool
        - need_mobile_master: bool
        - radius_km: Optional[int]
        - service_category: Optional[str]
        - description: str
        - photos: Optional[List[str]]
        - hide_phone: bool

        Статус заявки устанавливаем NEW (new) по умолчанию.
        """

        request = Request(
            user_id=data.user_id,
            car_id=data.car_id,
            # гео
            latitude=data.latitude,
            longitude=data.longitude,
            address_text=data.address_text,
            # состояние авто
            is_car_movable=data.is_car_movable,
            need_tow_truck=data.need_tow_truck,
            need_mobile_master=data.need_mobile_master,
            # радиус/район + категория услуги
            radius_km=data.radius_km,
            service_category=data.service_category,
            # описание и фото
            description=data.description,
            photos=data.photos,
            # скрытие телефона
            hide_phone=data.hide_phone,
            # статус
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
    # Список заявок по пользователю
    # ------------------------------------------------------------------
    @staticmethod
    async def list_requests_by_user(
        db: AsyncSession,
        user_id: int,
    ) -> List[Request]:
        stmt = (
            select(Request)
            .where(Request.user_id == user_id)
            .order_by(Request.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Обновление заявки
    # ------------------------------------------------------------------
    @staticmethod
    async def update_request(
        db: AsyncSession,
        request_id: int,
        data: RequestUpdate,
    ) -> Optional[Request]:
        """
        Частичное обновление заявки по RequestUpdate.
        Все поля в RequestUpdate должны быть опциональными,
        мы обновляем только те, которые реально передали.
        """
        request = await RequestsService.get_request_by_id(db, request_id)
        if not request:
            return None

        # Pydantic v1: dict(exclude_unset=True)
        update_data = data.dict(exclude_unset=True)

        for field, value in update_data.items():
            setattr(request, field, value)

        await db.commit()
        await db.refresh(request)
        return request

    # ------------------------------------------------------------------
    # Список всех заявок (опционально по статусу)
    # ------------------------------------------------------------------
    @staticmethod
    async def list_requests(
        db: AsyncSession,
        status: Optional[str] = None,
    ) -> List[Request]:
        stmt = select(Request)
        if status:
            # status ожидается как строка, например "new", "in_work"
            stmt = stmt.where(Request.status == RequestStatus(status))

        stmt = stmt.order_by(Request.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # СТАРЫЙ способ: список заявок для СТО по специализациям
    # (оставляем как запасной/для админки, но в боте использовать не будем)
    # ------------------------------------------------------------------
    @staticmethod
    async def list_requests_for_service_centers_by_specializations(
        db: AsyncSession,
        specializations: Optional[list[str]] = None,
    ) -> List[Request]:
        """
        Список активных заявок для отображения СТО (старый режим, по категориям).

        Если переданы specializations — фильтруем только по этим категориям.
        """
        active_statuses = [
            RequestStatus.NEW,
            RequestStatus.SENT,
            RequestStatus.IN_WORK,
        ]

        stmt = select(Request).where(Request.status.in_(active_statuses))

        if specializations:
            stmt = stmt.where(Request.service_category.in_(specializations))

        stmt = stmt.order_by(Request.created_at.desc())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # НОВОЕ: распределение заявки по конкретным СТО
    # ------------------------------------------------------------------
    @staticmethod
    async def distribute_request_to_service_centers(
        db: AsyncSession,
        request_id: int,
        service_center_ids: List[int],
    ) -> Optional[Request]:
        """
        Зафиксировать, каким СТО была отправлена заявка.

        1) Проверяем, что заявка существует.
        2) Удаляем старые записи распределения (если вдруг были).
        3) Создаём новые записи RequestDistribution со статусом SENT.
        4) Меняем статус заявки на SENT.
        """
        request = await RequestsService.get_request_by_id(db, request_id)
        if not request:
            return None

        # На всякий случай чистим старое распределение
        await db.execute(
            delete(RequestDistribution).where(
                RequestDistribution.request_id == request_id
            )
        )

        # Создаём новые записи
        for sc_id in service_center_ids:
            dist = RequestDistribution(
                request_id=request_id,
                service_center_id=sc_id,
                status=RequestDistributionStatus.SENT,
            )
            db.add(dist)

        # Обновляем статус заявки
        request.status = RequestStatus.SENT

        await db.commit()
        await db.refresh(request)
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
        Список активных заявок, которые были разосланы КОНКРЕТНОМУ СТО.

        Используется модель RequestDistribution:
        - берём только те заявки, которые были отправлены этому service_center_id;
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
