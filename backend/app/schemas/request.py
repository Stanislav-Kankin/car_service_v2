from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.app.models.request import RequestStatus


class RequestBase(BaseModel):
    user_id: int
    car_id: Optional[int] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_text: Optional[str] = Field(None, max_length=500)

    is_car_movable: bool = True
    need_tow_truck: bool = False
    need_mobile_master: bool = False

    radius_km: Optional[int] = None
    service_category: Optional[str] = Field(None, max_length=100)

    description: str = Field(..., min_length=3)
    photos: Optional[List[str]] = None

    hide_phone: bool = True


class RequestCreate(RequestBase):
    pass


class RequestUpdate(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_text: Optional[str] = Field(None, max_length=500)

    is_car_movable: Optional[bool] = None
    need_tow_truck: Optional[bool] = None
    need_mobile_master: Optional[bool] = None

    radius_km: Optional[int] = None
    service_category: Optional[str] = Field(None, max_length=100)

    description: Optional[str] = Field(None, min_length=3)
    photos: Optional[List[str]] = None

    hide_phone: Optional[bool] = None
    status: Optional[RequestStatus] = None
    service_center_id: Optional[int] = None


class RequestRead(BaseModel):
    id: int
    user_id: int
    car_id: Optional[int]
    service_center_id: Optional[int]

    latitude: Optional[float]
    longitude: Optional[float]
    address_text: Optional[str]

    is_car_movable: bool
    need_tow_truck: bool
    need_mobile_master: bool

    radius_km: Optional[int]
    service_category: Optional[str]

    description: str
    photos: Optional[List[str]]

    hide_phone: bool
    status: RequestStatus

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
