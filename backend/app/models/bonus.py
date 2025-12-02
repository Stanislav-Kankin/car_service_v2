from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.db import Base


class BonusReason(str, Enum):
    REGISTRATION = "registration"
    CREATE_REQUEST = "create_request"
    COMPLETE_REQUEST = "complete_request"
    RATE_SERVICE = "rate_service"
    MANUAL_ADJUST = "manual_adjust"


class BonusTransaction(Base):
    __tablename__ = "bonus_transactions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # положительное число — начисление, отрицательное — списание
    amount = Column(Integer, nullable=False)

    reason = Column(
        SAEnum(BonusReason),
        nullable=False,
        default=BonusReason.MANUAL_ADJUST,
    )

    # можно связать бонус с конкретной заявкой/откликом
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    offer_id = Column(
        Integer,
        ForeignKey("offers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    description = Column(String(255), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="bonus_transactions")
