from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.schemas.bonus import BonusAdjust, BonusTransactionRead
from backend.app.services.bonus_service import BonusService

router = APIRouter(
    prefix="/bonus",
    tags=["bonus"],
)


@router.get(
    "/{user_id}/balance",
    response_model=int,
)
async def get_user_balance(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> int:
    return await BonusService.get_user_balance(db, user_id)


@router.get(
    "/{user_id}/transactions",
    response_model=List[BonusTransactionRead],
)
async def list_user_transactions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[BonusTransactionRead]:
    txs = await BonusService.list_user_transactions(db, user_id)
    return list(txs)


@router.post(
    "/{user_id}/adjust",
    response_model=BonusTransactionRead,
    status_code=status.HTTP_201_CREATED,
)
async def adjust_user_bonus(
    user_id: int,
    data_in: BonusAdjust,
    db: AsyncSession = Depends(get_db),
) -> BonusTransactionRead:
    try:
        tx = await BonusService.add_bonus(
            db=db,
            user_id=user_id,
            amount=data_in.amount,
            reason=data_in.reason,
            request_id=data_in.request_id,
            offer_id=data_in.offer_id,
            description=data_in.description,
        )
        return tx
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
