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
        Ищем СТО по:
          - категории/специализациям
          - флагам (активен, эвакуатор, выездной)
          - гео (если пришли latitude/longitude + radius_km)

        Возвращаем список СТО, отсортированный по расстоянию (если geo включено).

        ⚠️ ВАЖНО:
          - если geo-фильтр дал пусто -> можно сделать fallback "все по категории" (без гео)
            (для сохранения старого поведения). Для рассылки "Отправить всем" мы будем отключать fallback.
        """

        # 1) Базовый запрос "по категории/флагам" (без гео)
        stmt = select(ServiceCenter)

        if specializations:
            stmt = stmt.where(ServiceCenter.specializations.overlap(specializations))

        if is_active is not None:
            stmt = stmt.where(ServiceCenter.is_active == is_active)

        if has_tow_truck is not None:
            stmt = stmt.where(ServiceCenter.has_tow_truck == has_tow_truck)

        if is_mobile_service is not None:
            stmt = stmt.where(ServiceCenter.is_mobile_service == is_mobile_service)

        res = await db.execute(stmt)
        items_by_category = list(res.scalars().all())

        # 2) Если geo не задано — возвращаем как раньше
        if latitude is None or longitude is None or not radius_km:
            return items_by_category

        # 3) Geo-фильтрация по радиусу
        items_geo: list[tuple[ServiceCenter, float]] = []
        for sc in items_by_category:
            if sc.latitude is None or sc.longitude is None:
                continue

            dist = ServiceCentersService._haversine_km(
                latitude, longitude, sc.latitude, sc.longitude
            )
            if dist <= radius_km:
                items_geo.append((sc, dist))

        items_geo.sort(key=lambda x: x[1])
        items = [sc for sc, _dist in items_geo]

        # ✅ fallback: если "рядом" никого — по желанию вернём "все по категории"
        if not items_geo:
            return items_by_category if fallback_to_category else []

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
