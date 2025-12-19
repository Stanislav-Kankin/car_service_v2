from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.db import Base


class OfferStatus(str, Enum):
    NEW = "new"              # предложение отправлено клиенту
    ACCEPTED = "accepted"    # клиент выбрал это предложение
    REJECTED = "rejected"    # клиент отклонил


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)

    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    service_center_id = Column(
        Integer,
        ForeignKey("service_centers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # старые поля (совместимость)
    price = Column(Numeric(10, 2), nullable=True)
    eta_hours = Column(Integer, nullable=True)  # срок в часах/днях, трактуем в сервисе

    # ✅ новые текстовые поля (свободный ввод)
    price_text = Column(String(100), nullable=True)
    eta_text = Column(String(100), nullable=True)

    cashback_percent = Column(
        Numeric(5, 2),
        nullable=True,
        doc="Кэшбек, % (0-100). Используется для начисления бонусов при завершении заявки.",
    )

    comment = Column(Text, nullable=True)

    status = Column(
        SAEnum(OfferStatus),
        nullable=False,
        default=OfferStatus.NEW,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ✅ нужно для response_model (OfferRead)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # relationships
    request = relationship("Request", back_populates="offers")
    service_center = relationship("ServiceCenter", back_populates="offers")
