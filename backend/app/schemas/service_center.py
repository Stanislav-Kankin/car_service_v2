from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class ServiceCenterBase(BaseModel):
    """
    Общие поля для создания/чтения СТО.
    """

    name: str = Field(..., max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    phone: Optional[str] = Field(default=None, max_length=50)
    website: Optional[str] = Field(default=None, max_length=255)
    social_links: Optional[Dict] = None

    specializations: Optional[List[str]] = None
    org_type: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Тип организации: 'individual' (частник) или 'company' (юрлицо)",
    )

    # ✅ сегментация СТО
    segment: str = Field(
        default="unspecified",
        max_length=20,
        description="Сегмент СТО: premium_plus / official / multibrand / club / specialized / unspecified",
    )

    # Флаги возможностей
    is_mobile_service: bool = False
    has_tow_truck: bool = False
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class ServiceCenterCreate(ServiceCenterBase):
    """
    Схема создания СТО.
    """
    user_id: int


class ServiceCenterUpdate(BaseModel):
    """
    Частичное обновление профиля СТО.
    Все поля опциональные: обновляем только переданные (exclude_unset=True).
    """

    name: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    phone: Optional[str] = Field(default=None, max_length=50)
    website: Optional[str] = Field(default=None, max_length=255)
    social_links: Optional[Dict] = None

    specializations: Optional[List[str]] = None
    org_type: Optional[str] = Field(default=None, max_length=20)

    # ✅ сегментация СТО — ВОТ ЭТОГО НЕ ХВАТАЕТ, из-за этого “не сохраняется”
    segment: Optional[str] = Field(default=None, max_length=20)

    # флаги — тоже опциональные (чтобы PATCH не требовал их всегда)
    is_mobile_service: Optional[bool] = None
    has_tow_truck: Optional[bool] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class ServiceCenterRead(ServiceCenterBase):
    """
    Схема чтения СТО (то, что возвращает API наружу).
    """

    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
