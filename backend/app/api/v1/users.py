from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import get_db
from ...models.user import User
from ...schemas.user import UserCreate, UserRead, UserUpdate
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
):
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
