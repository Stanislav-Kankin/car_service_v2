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
    __tablename__ = "service_centers"

    id = Column(Integer, primary_key=True, index=True)

    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=True)

    latitude = Column(Float, nullable=True, index=True)
    longitude = Column(Float, nullable=True, index=True)

    phone = Column(String(32), nullable=True)
    website = Column(String(255), nullable=True)
    social_links = Column(JSON, nullable=True)  # список/словарь ссылок

    # специализации (категории СТО) — храним как JSON-массив строк
    specializations = Column(JSON, nullable=True)

    is_mobile_service = Column(Boolean, nullable=False, default=False)  # выездной мастер
    has_tow_truck = Column(Boolean, nullable=False, default=False)      # эвакуатор

    is_active = Column(Boolean, nullable=False, default=True)

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

    owner = relationship("User", back_populates="service_centers")
    offers = relationship("Offer", back_populates="service_center")
    requests = relationship("Request", back_populates="service_center")
