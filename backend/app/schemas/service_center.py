from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


# -----------------------------------------------------------------------------
# ВАЖНО:
# Это Pydantic-схемы (DTO) для API.
# Здесь НЕ ДОЛЖНО быть SQLAlchemy Base / Column / __tablename__.
# Иначе SQLAlchemy попытается объявить таблицу "service_centers" второй раз,
# что приводит к ошибке:
#   sqlalchemy.exc.InvalidRequestError: Table 'service_centers' is already defined
# -----------------------------------------------------------------------------

# Разрешённые значения сегмента. Храним строкой, чтобы:
# - не ломать SQLite/PG
# - легко менять/расширять без миграций enum-типа
ServiceCenterSegment = Literal[
    "unspecified",
    "premium_plus",
    "official",
    "multibrand",
    "club",
    "specialized",
]


class ServiceCenterBase(BaseModel):
    """
    Базовые поля СТО, общие для Create/Read.
    """

    name: str = Field(..., max_length=255, description="Название СТО")
    address: Optional[str] = Field(default=None, max_length=500, description="Адрес")

    latitude: Optional[float] = Field(default=None, description="Широта")
    longitude: Optional[float] = Field(default=None, description="Долгота")

    phone: Optional[str] = Field(default=None, max_length=50, description="Телефон")
    website: Optional[str] = Field(default=None, max_length=255, description="Сайт")

    # Соцсети/контакты (JSON)
    social_links: Optional[Dict] = Field(default=None, description="Соцсети/контакты (JSON)")

    # Список специализаций (коды)
    specializations: Optional[List[str]] = Field(
        default=None,
        description="Список специализаций (коды строками)",
    )

    org_type: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Тип организации: individual/company",
    )

    # ✅ сегментация
    segment: ServiceCenterSegment = Field(
        default="unspecified",
        description="Сегмент СТО: premium_plus/official/multibrand/club/specialized/unspecified",
    )

    # Флаги возможностей
    is_mobile_service: bool = Field(default=False, description="Выездной мастер")
    has_tow_truck: bool = Field(default=False, description="Есть эвакуатор")

    # Модерация (в create по умолчанию у тебя false в сервисе)
    is_active: bool = Field(default=True, description="Активность (модерация)")

    model_config = ConfigDict(from_attributes=True)


class ServiceCenterCreate(ServiceCenterBase):
    """
    Создание СТО.
    user_id обязателен.
    segment можно передать, иначе будет unspecified.
    """
    user_id: int = Field(..., description="ID владельца (User.id)")


class ServiceCenterUpdate(BaseModel):
    """
    PATCH-обновление СТО.
    Все поля опциональны — обновляем только те, что реально передали.
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

    # ✅ сегментация
    segment: Optional[ServiceCenterSegment] = Field(default=None)

    is_mobile_service: Optional[bool] = None
    has_tow_truck: Optional[bool] = None

    # Модерация (админка/вебапп)
    is_active: Optional[bool] = None

    # Игнорируем лишние поля из webapp/bot, чтобы не падать
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class ServiceCenterRead(ServiceCenterBase):
    """
    Ответ API для чтения СТО.
    """

    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
