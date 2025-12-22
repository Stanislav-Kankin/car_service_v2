from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.car import Car
from ..schemas.car import CarCreate, CarUpdate


class CarsService:
    @staticmethod
    async def create_car(db: AsyncSession, data_in: CarCreate) -> Car:
        car = Car(
            user_id=data_in.user_id,
            brand=data_in.brand,
            model=data_in.model,
            year=data_in.year,
            license_plate=data_in.license_plate,
            vin=data_in.vin,
            engine_type=data_in.engine_type,
            engine_volume_l=data_in.engine_volume_l,
            engine_power_kw=data_in.engine_power_kw,
        )
        db.add(car)
        await db.commit()
        await db.refresh(car)
        return car

    @staticmethod
    async def get_car(db: AsyncSession, car_id: int) -> Car | None:
        res = await db.execute(select(Car).where(Car.id == car_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def list_cars_by_user(db: AsyncSession, user_id: int) -> list[Car]:
        res = await db.execute(select(Car).where(Car.user_id == user_id).order_by(Car.id.desc()))
        return list(res.scalars().all())

    @staticmethod
    async def update_car(db: AsyncSession, car: Car, data_in: CarUpdate) -> Car:
        for field, value in data_in.model_dump(exclude_unset=True).items():
            setattr(car, field, value)

        db.add(car)
        await db.commit()
        await db.refresh(car)
        return car

    @staticmethod
    async def delete_car(db: AsyncSession, car: Car) -> None:
        await db.delete(car)
        await db.commit()
