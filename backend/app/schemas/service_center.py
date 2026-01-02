from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class ServiceCenterBase(BaseModel):
    """
    Общие поля для создания/чтения/обновления СТО.
    """

    name: str = Field(..., max_length=255)
    address: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Адрес сервиса (строкой)",
    )

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    phone: Optional[str] = Field(default=None, max_length=32)
    website: Optional[str] = Field(default=None, max_length=255)

    # Например: {"vk": "...", "instagram": "..."}
    social_links: Optional[Dict[str, str]] = None

    # Список специализаций (см. словарь спецов в боте)
    specializations: Optional[List[str]] = None

    # Тип организации: ФЛ / ЮЛ
    org_type: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Тип организации: 'individual' (частник) или 'company' (юрлицо)",
    )

    # Сегментация/плашка СТО
    segment: str = Field(
        default="unspecified",
        max_length=32,
        description="Сегмент СТО: prem_plus/official/multibrand/club/specialized/unspecified",
    )

    # Флаги возможностей
    is_mobile_service: bool = False
    has_tow_truck: bool = False
    is_active: bool = True


class ServiceCenterCreate(ServiceCenterBase):
    """
    Схема создания СТО.
    """

    user_id: int


class ServiceCenterUpdate(BaseModel):
    """
    Частичное обновление профиля СТО.
    Все поля опциональные, мы обновляем только переданные.
    """

    name: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    phone: Optional[str] = Field(default=None, max_length=32)
    website: Optional[str] = Field(default=None, max_length=255)

    social_links: Optional[Dict[str, str]] = None
    specializations: Optional[List[str]] = None

    org_type: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Тип организации: 'individual' (частник) или 'company' (юрлицо)",
    )

    segment: Optional[str] = Field(default=None, max_length=32)

    is_mobile_service: Optional[bool] = None
    has_tow_truck: Optional[bool] = None
    is_active: Optional[bool] = None


class ServiceCenterRead(ServiceCenterBase):
    id: int
    user_id: int

    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
