from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import ServiceCenter
from backend.app.schemas.service_center import (
    ServiceCenterCreate,
    ServiceCenterRead,
    ServiceCenterUpdate,
)


class ServiceCentersService:
    @staticmethod
    async def create_service_center(
        db: AsyncSession,
        data_in: ServiceCenterCreate,
    ) -> ServiceCenter:
        sc = ServiceCenter(
            owner_user_id=data_in.owner_user_id,
            name=data_in.name,
            address=data_in.address,
            latitude=data_in.latitude,
            longitude=data_in.longitude,
            phone=data_in.phone,
            website=data_in.website,
            social_links=data_in.social_links,
            specializations=data_in.specializations,
            is_mobile_service=data_in.is_mobile_service,
            has_tow_truck=data_in.has_tow_truck,
            is_active=data_in.is_active,
        )
        db.add(sc)
        await db.commit()
        await db.refresh(sc)
        return sc

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        sc_id: int,
    ) -> Optional[ServiceCenter]:
        result = await db.execute(
            select(ServiceCenter).where(ServiceCenter.id == sc_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_service_centers(
        db: AsyncSession,
        specialization: Optional[str] = None,
        is_active: Optional[bool] = True,
        has_tow_truck: Optional[bool] = None,
        is_mobile_service: Optional[bool] = None,
    ) -> List[ServiceCenter]:
        stmt = select(ServiceCenter)

        if is_active is not None:
            stmt = stmt.where(ServiceCenter.is_active == is_active)

        if has_tow_truck is not None:
            stmt = stmt.where(ServiceCenter.has_tow_truck == has_tow_truck)

        if is_mobile_service is not None:
            stmt = stmt.where(ServiceCenter.is_mobile_service == is_mobile_service)

        if specialization:
            # specializations хранится как JSON-массив строк
            # для SQLite/JSON проще пока фильтровать "на стороне Python"
            result = await db.execute(stmt)
            all_items = result.scalars().all()
            return [
                sc
                for sc in all_items
                if sc.specializations and specialization in sc.specializations
            ]

        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def update_service_center(
        db: AsyncSession,
        sc: ServiceCenter,
        data_in: ServiceCenterUpdate,
    ) -> ServiceCenter:
        data = data_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(sc, field, value)
        await db.commit()
        await db.refresh(sc)
        return sc
