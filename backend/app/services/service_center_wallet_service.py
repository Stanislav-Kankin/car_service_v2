from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    ServiceCenterWallet,
    ServiceCenterWalletTransaction,
    ServiceCenterWalletTxType,
)


class ServiceCenterWalletService:
    @staticmethod
    async def get_or_create_wallet(
        db: AsyncSession,
        service_center_id: int,
    ) -> ServiceCenterWallet:
        stmt = select(ServiceCenterWallet).where(
            ServiceCenterWallet.service_center_id == service_center_id
        )
        res = await db.execute(stmt)
        wallet = res.scalar_one_or_none()
        if wallet:
            return wallet

        wallet = ServiceCenterWallet(service_center_id=service_center_id, balance=0)
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)
        return wallet

    @staticmethod
    async def get_wallet(
        db: AsyncSession,
        service_center_id: int,
    ) -> Optional[ServiceCenterWallet]:
        stmt = select(ServiceCenterWallet).where(
            ServiceCenterWallet.service_center_id == service_center_id
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_transactions(
        db: AsyncSession,
        service_center_id: int,
        limit: int = 50,
    ) -> List[ServiceCenterWalletTransaction]:
        stmt = (
            select(ServiceCenterWalletTransaction)
            .where(ServiceCenterWalletTransaction.service_center_id == service_center_id)
            .order_by(ServiceCenterWalletTransaction.id.desc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def credit_wallet(
        db: AsyncSession,
        service_center_id: int,
        amount: int,
        tx_type: ServiceCenterWalletTxType = ServiceCenterWalletTxType.ADMIN_CREDIT,
        description: Optional[str] = None,
    ) -> Tuple[ServiceCenterWallet, ServiceCenterWalletTransaction]:
        if amount <= 0:
            raise ValueError("amount must be positive")

        # Важно: стараемся делать атомарно (в Postgres с FOR UPDATE),
        # но если БД/драйвер не поддержит — всё равно отработает обычным select.
        stmt = (
            select(ServiceCenterWallet)
            .where(ServiceCenterWallet.service_center_id == service_center_id)
            .with_for_update()
        )

        res = await db.execute(stmt)
        wallet = res.scalar_one_or_none()

        if not wallet:
            wallet = ServiceCenterWallet(service_center_id=service_center_id, balance=0)
            db.add(wallet)
            await db.flush()  # чтобы получить wallet.id

        wallet.balance = int(wallet.balance or 0) + int(amount)

        tx = ServiceCenterWalletTransaction(
            wallet_id=int(wallet.id),
            service_center_id=service_center_id,
            amount=int(amount),
            tx_type=tx_type,
            description=description,
        )
        db.add(tx)

        await db.commit()
        await db.refresh(wallet)
        await db.refresh(tx)
        return wallet, tx
