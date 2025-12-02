from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from backend.app.models.bonus import BonusReason


class BonusTransactionRead(BaseModel):
    id: int
    user_id: int
    amount: int
    reason: BonusReason
    request_id: Optional[int]
    offer_id: Optional[int]
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class BonusAdjust(BaseModel):
    amount: int
    reason: BonusReason = BonusReason.MANUAL_ADJUST
    request_id: Optional[int] = None
    offer_id: Optional[int] = None
    description: Optional[str] = None
