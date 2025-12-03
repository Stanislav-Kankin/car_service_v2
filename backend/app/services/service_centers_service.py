from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import ServiceCenter
from backend.app.schemas.service_center import (
    ServiceCenterCreate,
    ServiceCenterUpdate,
)


class ServiceCentersService:
    """
    Сервисный слой для работы с автосервисами (СТО).
    """

    # ------------------------------------------------------------------
    # Создание
    # ------------------------------------------------------------------
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
            is_mobile_service=data_in.is_mobile_service,
            has_tow_truck=data_in.has_tow_truck,
            is_active=data_in.is_active,
        )
        db.add(sc)
        await db.commit()
        await db.refresh(sc)
        return sc

    # ------------------------------------------------------------------
    # Получение
    # ------------------------------------------------------------------
    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        sc_id: int,
    ) -> Optional[ServiceCenter]:
        stmt = select(ServiceCenter).where(ServiceCenter.id == sc_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        is_active: Optional[bool] = None,
    ) -> List[ServiceCenter]:
        stmt = select(ServiceCenter)
        if is_active is not None:
            stmt = stmt.where(ServiceCenter.is_active == is_active)

        stmt = stmt.order_by(ServiceCenter.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_user(
        db: AsyncSession,
        user_id: int,
    ) -> List[ServiceCenter]:
        stmt = (
            select(ServiceCenter)
            .where(ServiceCenter.user_id == user_id)
            .order_by(ServiceCenter.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Поиск подходящих СТО (заготовка)
    # ------------------------------------------------------------------
    @staticmethod
    async def search_service_centers(
        db: AsyncSession,
        *,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[int] = None,
        specializations: Optional[List[str]] = None,
        is_active: Optional[bool] = True,
    ) -> List[ServiceCenter]:
        """
        Базовый поиск СТО.

        Сейчас:
        - фильтруем по is_active
        - опционально по наличию пересечения специализаций
        - гео пока не учитываем (добавим позже в пункте E чеклиста)
        """
        stmt = select(ServiceCenter)
        if is_active is not None:
            stmt = stmt.where(ServiceCenter.is_active == is_active)

        # Пока без SQL-фильтра по specializations — отфильтруем на Python.
        result = await db.execute(stmt)
        items: List[ServiceCenter] = list(result.scalars().all())

        if specializations:
            wanted = set(specializations)
            items = [
                sc
                for sc in items
                if sc.specializations and wanted & set(sc.specializations)
            ]

        # TODO: добавить фильтрацию по latitude/longitude/radius_km
        return items

    # ------------------------------------------------------------------
    # Обновление
    # ------------------------------------------------------------------
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
