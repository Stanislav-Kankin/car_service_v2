from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.user import UserCreate, UserRead, UserUpdate
from backend.app.services.user_service import UsersService

router = APIRouter()


@router.post(
    "/",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создать пользователя (клиента).

    На практике это будет дергать бот при первой регистрации.
    """
    user = await UsersService.create_user(db, user_in)
    return user


@router.get(
    "/{user_id}",
    response_model=UserRead,
)
async def get_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    user = await UsersService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.get(
    "/by-telegram/{telegram_id}",
    response_model=UserRead,
)
async def get_user_by_telegram_id(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
):
    user = await UsersService.get_user_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.patch(
    "/{user_id}",
    response_model=UserRead,
)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
):
    user = await UsersService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user = await UsersService.update_user(db, user, user_in)
    return user
