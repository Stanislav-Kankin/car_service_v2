from typing import Optional
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.user import User
from ..models.bonus import BonusReason, BonusTransaction
from ..schemas.user import UserCreate, UserUpdate, UserRole
from ..services.bonus_service import BonusService


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

        # BONUS HIDDEN MODE: временно отключаем авто-начисления при регистрации
        if not settings.BONUS_HIDDEN_MODE:
            # ✅ Бонус за регистрацию: начисляем только один раз
            # (страховка от дублей, если по какой-то причине create_user вызовется повторно)
            reg_bonus_amount = int(getattr(settings, "REGISTRATION_BONUS", 500))

            result = await db.execute(
                select(BonusTransaction.id).where(
                    BonusTransaction.user_id == user.id,
                    BonusTransaction.reason == BonusReason.REGISTRATION,
                )
            )
            already_has_registration_bonus = result.scalar_one_or_none() is not None

            if not already_has_registration_bonus and reg_bonus_amount:
                await BonusService.add_bonus(
                    db=db,
                    user_id=user.id,
                    amount=reg_bonus_amount,
                    reason=BonusReason.REGISTRATION,
                    description="Бонус за регистрацию",
                )

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
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """Получить пользователя по внутреннему ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_users(
        db: AsyncSession,
        *,
        registered_from: Optional[date] = None,
        registered_to: Optional[date] = None,
        user_id: Optional[int] = None,
        telegram_id: Optional[int] = None,
    ) -> list[User]:
        """
        Получить список пользователей с простыми фильтрами для админки.
        """
        stmt = select(User)
        conditions = []

        # Фильтр по ID пользователя
        if user_id is not None:
            conditions.append(User.id == user_id)

        # Фильтр по Telegram ID
        if telegram_id is not None:
            conditions.append(User.telegram_id == telegram_id)

        # Фильтры по дате регистрации (по полю created_at, если оно есть)
        created_at_col = getattr(User, "created_at", None)
        if created_at_col is not None:
            if registered_from is not None:
                dt_from = datetime.combine(registered_from, time.min)
                conditions.append(created_at_col >= dt_from)
            if registered_to is not None:
                dt_to = datetime.combine(registered_to, time.max)
                conditions.append(created_at_col <= dt_to)

        if conditions:
            stmt = stmt.where(*conditions)

        # Новые сверху
        if created_at_col is not None:
            stmt = stmt.order_by(created_at_col.desc())
        else:
            stmt = stmt.order_by(User.id.desc())

        result = await db.execute(stmt)
        users = result.scalars().all()
        return list(users)

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
