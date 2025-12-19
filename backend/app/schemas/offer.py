from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.app.models.offer import OfferStatus


class OfferBase(BaseModel):
    request_id: int
    service_center_id: int

    # старые поля (оставляем для совместимости)
    price: Optional[float] = None
    eta_hours: Optional[int] = None

    # новые текстовые поля (свободный формат)
    price_text: Optional[str] = Field(None, max_length=100)
    eta_text: Optional[str] = Field(None, max_length=100)

    comment: Optional[str] = Field(None, max_length=1000)


class OfferCreate(OfferBase):
    cashback_percent: Optional[float] = Field(default=None, ge=0, le=100)


class OfferUpdate(BaseModel):
    price: Optional[float] = None
    eta_hours: Optional[int] = None

    price_text: Optional[str] = Field(None, max_length=100)
    eta_text: Optional[str] = Field(None, max_length=100)

    comment: Optional[str] = Field(None, max_length=1000)
    cashback_percent: Optional[float] = Field(default=None, ge=0, le=100)
    status: Optional[OfferStatus] = None


class OfferRead(BaseModel):
    id: int
    request_id: int
    service_center_id: int

    price: Optional[float]
    eta_hours: Optional[int]

    price_text: Optional[str]
    eta_text: Optional[str]

    comment: Optional[str]
    cashback_percent: Optional[float]
    status: OfferStatus

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
