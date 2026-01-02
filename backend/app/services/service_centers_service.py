from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.models.service_center import ServiceCenter
from backend.app.schemas.service_center import ServiceCenterCreate, ServiceCenterUpdate


class ServiceCentersService:
    @staticmethod
    async def create_service_center(
        db: AsyncSession,
        data_in: ServiceCenterCreate,
    ) -> ServiceCenter:
        sc = ServiceCenter(
            user_id=data_in.user_id,
            name=data_in.name,
            address=data_in.address,
            latitude=data_in.latitude,
            longitude=data_in.longitude,
            phone=data_in.phone,
            website=data_in.website,
            social_links=data_in.social_links,
            specializations=data_in.specializations,
            org_type=data_in.org_type,
            segment=getattr(data_in, "segment", "unspecified"),
            is_mobile_service=data_in.is_mobile_service,
            has_tow_truck=data_in.has_tow_truck,
            is_active=False,  # модерация
        )
        db.add(sc)
        await db.commit()
        await db.refresh(sc)
        return sc

    @staticmethod
    async def get_service_center(db: AsyncSession, sc_id: int) -> ServiceCenter | None:
        stmt = select(ServiceCenter).where(ServiceCenter.id == sc_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_service_centers(db: AsyncSession, only_active: bool = False) -> list[ServiceCenter]:
        stmt = select(ServiceCenter)
        if only_active:
            stmt = stmt.where(ServiceCenter.is_active.is_(True))
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_service_center(
        db: AsyncSession,
        sc: ServiceCenter,
        data_in: ServiceCenterUpdate,
    ) -> ServiceCenter:
        data = data_in.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(sc, k, v)

        await db.commit()
        await db.refresh(sc)
        return sc

    @staticmethod
    async def delete_service_center(db: AsyncSession, sc: ServiceCenter) -> None:
        await db.delete(sc)
        await db.commit()
