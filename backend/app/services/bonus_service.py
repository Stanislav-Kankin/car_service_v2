from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import BonusReason, BonusTransaction, User


class BonusService:
    @staticmethod
    async def add_bonus(
        db: AsyncSession,
        user_id: int,
        amount: int,
        reason: BonusReason,
        request_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        description: Optional[str] = None,
    ) -> BonusTransaction:
        # обновляем баланс пользователя
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        user.bonus_balance += amount

        tx = BonusTransaction(
            user_id=user_id,
            amount=amount,
            reason=reason,
            request_id=request_id,
            offer_id=offer_id,
            description=description,
        )

        db.add(tx)
        await db.commit()
        await db.refresh(tx)
        return tx

    @staticmethod
    async def get_user_balance(
        db: AsyncSession,
        user_id: int,
    ) -> int:
        result = await db.execute(
            select(User.bonus_balance).where(User.id == user_id)
        )
        balance = result.scalar_one_or_none()
        return balance or 0

    @staticmethod
    async def list_user_transactions(
        db: AsyncSession,
        user_id: int,
    ):
        result = await db.execute(
            select(BonusTransaction).where(BonusTransaction.user_id == user_id)
        )
        return result.scalars().all()
