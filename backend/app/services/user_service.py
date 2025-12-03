from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from ..schemas.user import UserCreate, UserUpdate, UserRole


class UsersService:
    @staticmethod
    async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
        user = User(
            telegram_id=user_in.telegram_id,
            full_name=user_in.full_name,
            phone=user_in.phone,
            city=user_in.city,
            role=user_in.role or UserRole.client,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def get_user_by_telegram(
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
            if field == "role" and value is not None:
                value = UserRole(value)
            setattr(user, field, value)

        await db.commit()
        await db.refresh(user)
        return user
