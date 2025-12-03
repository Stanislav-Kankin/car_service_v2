from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.request import Request
from backend.app.schemas.request import (
    RequestCreate,
    RequestRead,
    RequestUpdate,
)


class RequestsService:
    """
    Сервисный слой для работы с заявками.
    Никакой телеграм-логики, только работа с БД.
    """

    # ---------- CREATE ----------

    @staticmethod
    async def create_request(
        db: AsyncSession,
        data: RequestCreate,
    ) -> Request:
        """
        Создать заявку.
        """
        request = Request(
            user_id=data.user_id,
            car_id=data.car_id,
            # гео
            latitude=data.latitude,
            longitude=data.longitude,
            address=data.address,
            # как передвигается авто
            move_type=data.move_type,
            # описание проблемы
            description=data.description,
            # желаемая дата/время
            desired_date=data.desired_date,
            desired_time_slot=data.desired_time_slot,
            # статус
            status=data.status,
            # путь к фото (если есть)
            photo_file_id=data.photo_file_id,
        )
        db.add(request)
        await db.commit()
        await db.refresh(request)
        return request

    # ---------- READ ----------

    @staticmethod
    async def get_request_by_id(
        db: AsyncSession,
        request_id: int,
    ) -> Optional[Request]:
        result = await db.execute(
            select(Request).where(Request.id == request_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_requests_by_user(
        db: AsyncSession,
        user_id: int,
    ) -> List[Request]:
        result = await db.execute(
            select(Request)
            .where(Request.user_id == user_id)
            .order_by(Request.created_at.desc())
        )
        return list(result.scalars().all())

    # ---------- UPDATE ----------

    @staticmethod
    async def update_request(
        db: AsyncSession,
        request_id: int,
        data: RequestUpdate,
    ) -> Optional[Request]:
        """
        Частичное обновление заявки.
        """
        request = await RequestsService.get_request_by_id(db, request_id)
        if not request:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(request, field, value)

        await db.commit()
        await db.refresh(request)
        return request

    # ---------- HELPERS для будущего ----------

    @staticmethod
    async def list_requests_for_service_centers(
        db: AsyncSession,
        specializations: Optional[list[str]] = None,
    ) -> List[Request]:
        """
        Заготовка под выборку «подходящих заявок для СТО».
        Пока просто возвращаем все активные заявки.
        """
        query = select(Request).where(Request.status.in_(["new", "in_progress"]))
        # TODO: сюда потом добавим фильтрацию по гео и специализации

        result = await db.execute(query.order_by(Request.created_at.desc()))
        return list(result.scalars().all())
