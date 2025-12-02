from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Car
from backend.app.schemas.car import CarCreate, CarUpdate


class CarsService:
    @staticmethod
    async def create_car(
        db: AsyncSession,
        data_in: CarCreate,
    ) -> Car:
        car = Car(
            user_id=data_in.user_id,
            brand=data_in.brand,
            model=data_in.model,
            year=data_in.year,
            license_plate=data_in.license_plate,
            vin=data_in.vin,
        )
        db.add(car)
        await db.commit()
        await db.refresh(car)
        return car

    @staticmethod
    async def get_car_by_id(
        db: AsyncSession,
        car_id: int,
    ) -> Optional[Car]:
        result = await db.execute(
            select(Car).where(Car.id == car_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_cars_by_user(
        db: AsyncSession,
        user_id: int,
    ) -> List[Car]:
        result = await db.execute(
            select(Car).where(Car.user_id == user_id)
        )
        return result.scalars().all()

    @staticmethod
    async def update_car(
        db: AsyncSession,
        car: Car,
        data_in: CarUpdate,
    ) -> Car:
        data = data_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(car, field, value)
        await db.commit()
        await db.refresh(car)
        return car

    @staticmethod
    async def delete_car(
        db: AsyncSession,
        car: Car,
    ) -> None:
        await db.delete(car)
        await db.commit()
