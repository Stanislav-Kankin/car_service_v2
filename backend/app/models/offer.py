from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.db import Base


class OfferStatus(str, Enum):
    NEW = "new"              # предложение отправлено клиенту
    ACCEPTED = "accepted"    # клиент выбрал этот отклик
    REJECTED = "rejected"    # клиент отклонил
    CANCELLED = "cancelled"  # СТО отозвало


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

    price = Column(Numeric(10, 2), nullable=True)
    eta_hours = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)

    # ✅ процент кэшбека (например 5.0 = 5%)
    cashback_percent = Column(Numeric(5, 2), nullable=True)

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

    request = relationship("Request", back_populates="offers")
    service_center = relationship("ServiceCenter", back_populates="offers")
