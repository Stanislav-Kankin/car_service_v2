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

from ..core.db import Base


class RequestStatus(str, Enum):
    NEW = "new"                      # создана, но не разослана
    SENT = "sent"                    # разослана подходящим СТО, ждём отклики
    ACCEPTED_BY_SERVICE = "accepted_by_service"
    IN_WORK = "in_work"
    DONE = "done"
    CANCELLED = "cancelled"
    REJECTED_BY_SERVICE = "rejected_by_service"


class Request(Base):
    __tablename__ = "requests"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    car_id = Column(
        Integer,
        ForeignKey("cars.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # выбранный сервис (после выбора отклика/из списка)
    service_center_id = Column(
        Integer,
        ForeignKey("service_centers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # геопозиция заявки
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    address_text = Column(String(500), nullable=True)

    # состояние авто
    is_car_movable = Column(Boolean, nullable=False, default=True)
    need_tow_truck = Column(Boolean, nullable=False, default=False)
    need_mobile_master = Column(Boolean, nullable=False, default=False)

    # радиус поиска / район
    radius_km = Column(Integer, nullable=True)

    # тип услуги / категория (совместимо с категориями СТО)
    service_category = Column(String(100), nullable=True)

    # описание проблемы
    description = Column(Text, nullable=False)

    # фото — список file_id / ссылок
    photos = Column(JSON, nullable=True)

    # скрывать ли телефон клиента от СТО до явного согласия
    hide_phone = Column(Boolean, nullable=False, default=True)

    status = Column(
        SAEnum(RequestStatus),
        nullable=False,
        default=RequestStatus.NEW,
        index=True,
    )

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

    # -------- связи --------
    user = relationship("User", back_populates="requests")
    car = relationship("Car", back_populates="requests")
    service_center = relationship("ServiceCenter", back_populates="requests")

    offers = relationship(
        "Offer",
        back_populates="request",
        cascade="all, delete-orphan",
    )

    # новые распределения заявки по СТО
    distributions = relationship(
        "RequestDistribution",
        back_populates="request",
        cascade="all, delete-orphan",
    )
