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

    # ------------------------------------------------------------------
    # Создание
    # ------------------------------------------------------------------
    @staticmethod
    async def create_service_center(
        db: AsyncSession,
        data_in: ServiceCenterCreate,
    ) -> ServiceCenter:
        """
        Создаём СТО. ВАЖНО:
        - is_active всегда False при создании (требуется модерация админом).
        """
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
            # Модерация: новые СТО всегда неактивны
            is_active=False,
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
        # алиас для обратной совместимости (в т.ч. при старых образах/хардкодах)
        return await ServiceCentersService.list_by_user(db, user_id)

    # ------------------------------------------------------------------
    # Поиск подходящих СТО с учётом гео и специализаций
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
        has_tow_truck: Optional[bool] = None,
        is_mobile_service: Optional[bool] = None,
        fallback_to_category: bool = True,
    ) -> List[ServiceCenter]:
        """
        Подбор СТО без .overlap (specializations у нас JSON).
        1) SQL-фильтры (active/tow/mobile)
        2) специализации в Python (пересечение)
        3) geo-фильтр с сортировкой по расстоянию
        4) fallback (опционально): если geo пусто — вернуть по категории
        """
        import math  # чтобы не зависеть от верхних импортов файла

        stmt = select(ServiceCenter).options(selectinload(ServiceCenter.owner))

        if is_active is not None:
            stmt = stmt.where(ServiceCenter.is_active == is_active)
        if has_tow_truck is not None:
            stmt = stmt.where(ServiceCenter.has_tow_truck == has_tow_truck)
        if is_mobile_service is not None:
            stmt = stmt.where(ServiceCenter.is_mobile_service == is_mobile_service)

        result = await db.execute(stmt)
        items: List[ServiceCenter] = list(result.scalars().all())

        # 1) Специализации: пересечение множеств (JSON)
        if specializations:
            wanted = {s.strip() for s in specializations if s and s.strip()}
            if wanted:
                filtered: List[ServiceCenter] = []
                for sc in items:
                    sc_specs = sc.specializations or []
                    sc_set = {s.strip() for s in sc_specs if isinstance(s, str) and s.strip()}
                    if wanted & sc_set:
                        filtered.append(sc)
                items = filtered

        items_by_category = list(items)

        # 2) Geo-фильтр
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

            filtered_with_dist: list[tuple[float, ServiceCenter]] = []
            for sc in items:
                if sc.latitude is None or sc.longitude is None:
                    continue
                dist = haversine_km(
                    origin_lat,
                    origin_lon,
                    float(sc.latitude),
                    float(sc.longitude),
                )
                if dist <= radius_km:
                    filtered_with_dist.append((dist, sc))

            filtered_with_dist.sort(key=lambda x: x[0])
            items_geo = [sc for _, sc in filtered_with_dist]

            if not items_geo:
                return items_by_category if fallback_to_category else []

            return items_geo

        return items_by_category

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
