from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Request, RequestStatus
from backend.app.schemas.request import RequestCreate, RequestUpdate


class RequestsService:
    @staticmethod
    async def create_request(
        db: AsyncSession,
        data_in: RequestCreate,
    ) -> Request:
        req = Request(
            user_id=data_in.user_id,
            car_id=data_in.car_id,
            latitude=data_in.latitude,
            longitude=data_in.longitude,
            address_text=data_in.address_text,
            is_car_movable=data_in.is_car_movable,
            need_tow_truck=data_in.need_tow_truck,
            need_mobile_master=data_in.need_mobile_master,
            radius_km=data_in.radius_km,
            service_category=data_in.service_category,
            description=data_in.description,
            photos=data_in.photos,
            hide_phone=data_in.hide_phone,
            status=RequestStatus.NEW,
        )
        db.add(req)
        await db.commit()
        await db.refresh(req)
        return req

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        request_id: int,
    ) -> Optional[Request]:
        result = await db.execute(
            select(Request).where(Request.id == request_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(
        db: AsyncSession,
        user_id: int,
    ) -> List[Request]:
        result = await db.execute(
            select(Request).where(Request.user_id == user_id)
        )
        return result.scalars().all()

    @staticmethod
    async def update_request(
        db: AsyncSession,
        req: Request,
        data_in: RequestUpdate,
    ) -> Request:
        data = data_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            if field == "status" and isinstance(value, RequestStatus):
                value = value.value
            setattr(req, field, value)
        await db.commit()
        await db.refresh(req)
        return req
