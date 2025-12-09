from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.db import Base


class RequestDistributionStatus(str, Enum):
    SENT = "sent"          # заявка отправлена этому СТО
    WINNER = "winner"      # заявка выиграна этим СТО (клиент выбрал)
    DECLINED = "declined"  # заявка была отправлена, но клиент выбрал другой сервис


class RequestDistribution(Base):
    """
    Таблица распределения заявок по СТО.
    Каждая запись означает, что конкретная заявка была отправлена конкретному сервису.
    """

    __tablename__ = "request_distribution"

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

    status = Column(
        SAEnum(RequestDistributionStatus),
        default=RequestDistributionStatus.SENT,
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    request = relationship("Request", back_populates="distributions")
    service_center = relationship("ServiceCenter", back_populates="request_distributions")
