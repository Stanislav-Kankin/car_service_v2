from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.car import CarCreate, CarRead, CarUpdate
from backend.app.services.cars_service import CarsService

router = APIRouter(
    prefix="/cars",
    tags=["cars"],
)


@router.post(
    "/",
    response_model=CarRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_car(
    data_in: CarCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создать машину пользователя (элемент гаража).
    """
    car = await CarsService.create_car(db, data_in)
    return car


@router.get(
    "/{car_id}",
    response_model=CarRead,
)
async def get_car(
    car_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить машину по ID.
    """
    car = await CarsService.get_car_by_id(db, car_id)
    if not car:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Car not found",
        )
    return car


@router.get(
    "/by-user/{user_id}",
    response_model=List[CarRead],
)
async def list_cars_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список машин пользователя.
    """
    cars = await CarsService.list_cars_by_user(db, user_id)
    return cars


@router.patch(
    "/{car_id}",
    response_model=CarRead,
)
async def update_car(
    car_id: int,
    data_in: CarUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Частичное обновление машины.
    """
    car = await CarsService.get_car_by_id(db, car_id)
    if not car:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Car not found",
        )
    car = await CarsService.update_car(db, car, data_in)
    return car


@router.delete(
    "/{car_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_car(
    car_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Удаление машины.
    """
    car = await CarsService.get_car_by_id(db, car_id)
    if not car:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Car not found",
        )
    await CarsService.delete_car(db, car)
    return None
