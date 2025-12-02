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


class OfferCreate(OfferBase):
    pass


class OfferUpdate(BaseModel):
    price: Optional[float] = None
    eta_hours: Optional[int] = None
    comment: Optional[str] = Field(None, max_length=1000)
    status: Optional[OfferStatus] = None


class OfferRead(BaseModel):
    id: int
    request_id: int
    service_center_id: int

    price: Optional[float]
    eta_hours: Optional[int]
    comment: Optional[str]
    status: OfferStatus

    created_at: datetime

    class Config:
        from_attributes = True
