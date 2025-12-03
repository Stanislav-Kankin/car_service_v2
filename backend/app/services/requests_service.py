from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.request import Request, RequestStatus
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
    # Заготовка под выборку заявок для СТО
    # ------------------------------------------------------------------
    @staticmethod
    async def list_requests_for_service_centers(
        db: AsyncSession,
        specializations: Optional[list[str]] = None,
    ) -> List[Request]:
        """
        Заготовка под выборку «подходящих заявок для СТО».

        Пока просто возвращаем все активные заявки (NEW / SENT / IN_WORK).
        Потом сюда добавим фильтрацию по гео и специализациям.
        """
        active_statuses = [
            RequestStatus.NEW,
            RequestStatus.SENT,
            RequestStatus.IN_WORK,
        ]

        stmt = (
            select(Request)
            .where(Request.status.in_(active_statuses))
            .order_by(Request.created_at.desc())
        )

        # TODO: в будущем добавить фильтр по specializations и гео

        result = await db.execute(stmt)
        return list(result.scalars().all())
