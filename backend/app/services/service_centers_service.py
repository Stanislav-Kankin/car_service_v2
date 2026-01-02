from typing import List, Optional
import math

from sqlalchemy import select
from sqlalchemy.orm import selectinload
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
            segment=getattr(data_in, 'segment', None) or 'unspecified',
            is_mobile_service=data_in.is_mobile_service,
            has_tow_truck=data_in.has_tow_truck,
            is_active=False,  # модерация
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
        stmt = (
            select(ServiceCenter)
            .options(selectinload(ServiceCenter.owner))
            .where(ServiceCenter.id == sc_id)
        )
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

    @staticmethod
    async def list_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> List[ServiceCenter]:
        return await ServiceCentersService.list_by_user(db, user_id)

    @staticmethod
    async def search_service_centers(
        db: AsyncSession,
        *,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[int] = None,
        specializations: Optional[List[str]] = None,
        is_active: Optional[bool] = True,
        has_tow_truck: Optional[bool] = None,
        is_mobile_service: Optional[bool] = None,
        fallback_to_category: bool = True,
    ) -> List[ServiceCenter]:
        """
        Безопасный поиск:
        - фильтры активности/tow/mobile в SQL
        - фильтр специализаций и гео — в Python (работает и с JSON, и с SQLite, и с Postgres)
        - fallback (управляемый): если по гео пусто, можно вернуть список "по категории"

        fallback_to_category:
            True  -> если по радиусу никого нет, возвращаем список по категории (старое поведение)
            False -> если по радиусу никого нет, возвращаем пустой список (нужно для строгой рассылки)
        """
        stmt = select(ServiceCenter).options(selectinload(ServiceCenter.owner))

        if is_active is not None:
            stmt = stmt.where(ServiceCenter.is_active == is_active)
        if has_tow_truck is not None:
            stmt = stmt.where(ServiceCenter.has_tow_truck == has_tow_truck)
        if is_mobile_service is not None:
            stmt = stmt.where(ServiceCenter.is_mobile_service == is_mobile_service)

        result = await db.execute(stmt)
        items: List[ServiceCenter] = list(result.scalars().all())

        if specializations:
            wanted = set(specializations)
            items = [
                sc for sc in items
                if sc.specializations and wanted & set(sc.specializations)
            ]

        items_by_category = list(items)

        if (
            latitude is not None
            and longitude is not None
            and radius_km is not None
            and radius_km > 0
        ):
            origin_lat = float(latitude)
            origin_lon = float(longitude)

            def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
                R = 6371.0
                phi1 = math.radians(lat1)
                phi2 = math.radians(lat2)
                dphi = math.radians(lat2 - lat1)
                dlambda = math.radians(lon2 - lon1)
                a = (
                    math.sin(dphi / 2) ** 2
                    + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
                )
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                return R * c

            filtered_with_dist = []
            for sc in items:
                if sc.latitude is None or sc.longitude is None:
                    continue
                dist = haversine_km(
                    origin_lat, origin_lon,
                    float(sc.latitude), float(sc.longitude),
                )
                if dist <= radius_km:
                    filtered_with_dist.append((dist, sc))

            filtered_with_dist.sort(key=lambda x: x[0])
            items_geo = [sc for _, sc in filtered_with_dist]

            if not items_geo:
                return items_by_category if fallback_to_category else []

            return items_geo

        return items

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
