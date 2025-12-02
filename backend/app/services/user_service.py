from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import User, UserRole
from backend.app.schemas.user import UserCreate, UserUpdate


class UsersService:
    @staticmethod
    async def create_user(
        db: AsyncSession,
        user_in: UserCreate,
    ) -> User:
        user = User(
            telegram_id=user_in.telegram_id,
            full_name=user_in.full_name,
            phone=user_in.phone,
            city=user_in.city,
            role=user_in.role.value if isinstance(user_in.role, UserRole) else user_in.role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def get_user_by_id(
        db: AsyncSession,
        user_id: int,
    ) -> Optional[User]:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_telegram_id(
        db: AsyncSession,
        telegram_id: int,
    ) -> Optional[User]:
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user: User,
        user_in: UserUpdate,
    ) -> User:
        data = user_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            if field == "role" and isinstance(value, UserRole):
                value = value.value
            setattr(user, field, value)
        await db.commit()
        await db.refresh(user)
        return user
