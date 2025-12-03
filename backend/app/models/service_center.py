from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.db import Base


class ServiceCenter(Base):
    """
    Модель автосервиса / частного мастера.

    org_type:
      - "individual" — частный мастер (ФЛ)
      - "company"   — юридическое лицо / сервис
    """

    __tablename__ = "service_centers"

    id = Column(Integer, primary_key=True, index=True)

    # Владелец (пользователь бота)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Основные данные
    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    phone = Column(String(32), nullable=True)
    website = Column(String(255), nullable=True)

    # Например: {"vk": "...", "instagram": "..."}
    social_links = Column(JSON, nullable=True)

    # Список специализаций, например ["mechanic", "tyres", "electrics"]
    specializations = Column(JSON, nullable=True)

    # Тип организации: "individual" (частник) или "company" (юрлицо)
    org_type = Column(String(20), nullable=True)

    # Доп. возможности
    is_mobile_service = Column(Boolean, nullable=False, server_default="0")
    has_tow_truck = Column(Boolean, nullable=False, server_default="0")

    # Активна ли карточка СТО
    is_active = Column(Boolean, nullable=False, server_default="1")

    # Временные метки
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Связи
    owner = relationship("User", back_populates="service_centers")
    offers = relationship("Offer", back_populates="service_center")
    requests = relationship("Request", back_populates="service_center")
