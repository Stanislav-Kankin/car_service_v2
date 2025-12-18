from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.app.models.offer import OfferStatus


class OfferBase(BaseModel):
    request_id: int
    service_center_id: int

    price: Optional[float] = None
    eta_hours: Optional[int] = None
    comment: Optional[str] = Field(None, max_length=1000)

    # ✅ процент кэшбека
    cashback_percent: Optional[float] = Field(default=None, ge=0, le=100)


class OfferCreate(OfferBase):
    pass


class OfferUpdate(BaseModel):
    price: Optional[float] = None
    eta_hours: Optional[int] = None
    comment: Optional[str] = Field(None, max_length=1000)
    cashback_percent: Optional[float] = Field(default=None, ge=0, le=100)
    status: Optional[OfferStatus] = None


class OfferRead(BaseModel):
    id: int
    request_id: int
    service_center_id: int

    price: Optional[float]
    eta_hours: Optional[int]
    comment: Optional[str]
    cashback_percent: Optional[float]

    status: OfferStatus
    created_at: datetime

    class Config:
        from_attributes = True
