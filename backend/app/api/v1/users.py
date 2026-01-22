from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import get_db
from ...api.deps import get_current_user
from ...models.user import User
from ...schemas.user import UserCreate, UserRead, UserUpdate, UserRole
from ...services.user_service import UsersService

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    user = await UsersService.create_user(db, user_in)
    return user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 🔒 IDOR защита: редактировать профиль может только владелец или админ
    if current_user.role != UserRole.admin and int(current_user.id) != int(user_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    # 🔒 Права: роль и is_active меняет только админ
    if current_user.role != UserRole.admin and (user_in.role is not None or user_in.is_active is not None):
        raise HTTPException(status_code=403, detail="Forbidden")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user = await UsersService.update_user(db, user, user_in)
    return user


@router.get("/by-telegram/{telegram_id}", response_model=UserRead)
async def get_user_by_telegram(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
):
    user = await UsersService.get_user_by_telegram(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/", response_model=List[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    registered_from: Optional[date] = Query(
        None,
        description="Дата регистрации с (включительно), формат YYYY-MM-DD",
    ),
    registered_to: Optional[date] = Query(
        None,
        description="Дата регистрации по (включительно), формат YYYY-MM-DD",
    ),
    user_id: Optional[int] = Query(
        None,
        description="Фильтр по внутреннему ID пользователя",
    ),
    telegram_id: Optional[int] = Query(
        None,
        description="Фильтр по Telegram ID",
    ),
):
    """
    Список пользователей для админки с базовыми фильтрами.
    """
    users = await UsersService.list_users(
        db,
        registered_from=registered_from,
        registered_to=registered_to,
        user_id=user_id,
        telegram_id=telegram_id,
    )
    return users
