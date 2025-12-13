from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.db import Base


class RequestStatus(str, Enum):
    NEW = "new"
    SENT = "sent"
    ACCEPTED_BY_SERVICE = "accepted_by_service"
    IN_WORK = "in_work"
    DONE = "done"
    CANCELLED = "cancelled"
    REJECTED_BY_SERVICE = "rejected_by_service"


class Request(Base):
    __tablename__ = "requests"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    car_id = Column(Integer, ForeignKey("cars.id"), nullable=True)

    service_center_id = Column(Integer, ForeignKey("service_centers.id"), nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    address_text = Column(String(500), nullable=True)

    is_car_movable = Column(Boolean, nullable=False, default=True)
    need_tow_truck = Column(Boolean, nullable=False, default=False)
    need_mobile_master = Column(Boolean, nullable=False, default=False)

    radius_km = Column(Integer, nullable=True)
    service_category = Column(String(100), nullable=True)

    description = Column(Text, nullable=False)
    photos = Column(JSON, nullable=True)

    hide_phone = Column(Boolean, nullable=False, default=True)

    # финальная цена (при завершении)
    final_price = Column(Float, nullable=True)

    # причина отказа
    reject_reason = Column(Text, nullable=True)

    status = Column(
        SAEnum(RequestStatus),
        nullable=False,
        default=RequestStatus.NEW,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="requests")
    car = relationship("Car", back_populates="requests")
    service_center = relationship("ServiceCenter", back_populates="requests")
