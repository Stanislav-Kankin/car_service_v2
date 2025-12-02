from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ServiceCenterBase(BaseModel):
    name: str = Field(..., max_length=255)
    address: Optional[str] = Field(None, max_length=500)

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    phone: Optional[str] = Field(None, max_length=32)
    website: Optional[str] = Field(None, max_length=255)
    social_links: Optional[Dict[str, str]] = None  # {"vk": "...", "inst": "..."}

    specializations: Optional[List[str]] = None  # ["mechanic", "tire", "electrics", ...]

    is_mobile_service: bool = False   # выездной мастер
    has_tow_truck: bool = False       # эвакуатор
    is_active: bool = True


class ServiceCenterCreate(ServiceCenterBase):
    owner_user_id: Optional[int] = None


class ServiceCenterUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=500)

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    phone: Optional[str] = Field(None, max_length=32)
    website: Optional[str] = Field(None, max_length=255)
    social_links: Optional[Dict[str, str]] = None

    specializations: Optional[List[str]] = None

    is_mobile_service: Optional[bool] = None
    has_tow_truck: Optional[bool] = None
    is_active: Optional[bool] = None


class ServiceCenterRead(BaseModel):
    id: int
    owner_user_id: Optional[int]

    name: str
    address: Optional[str]

    latitude: Optional[float]
    longitude: Optional[float]

    phone: Optional[str]
    website: Optional[str]
    social_links: Optional[Dict[str, str]]

    specializations: Optional[List[str]]

    is_mobile_service: bool
    has_tow_truck: bool
    is_active: bool

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
