from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.db import Base


class UserRole(str, Enum):
    CLIENT = "client"
    SERVICE_CENTER_OWNER = "service_center_owner"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=True)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=True, index=True)
    city = Column(String(100), nullable=True)

    role = Column(String(50), nullable=False, default=UserRole.CLIENT.value)
    is_active = Column(Boolean, nullable=False, default=True)

    bonus_balance = Column(Integer, nullable=False, default=0)

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

    # связи
    cars = relationship(
        "Car",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    requests = relationship(
        "Request",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    service_centers = relationship(
        "ServiceCenter",
        back_populates="owner",
    )
    bonus_transactions = relationship(
        "BonusTransaction",
        back_populates="user",
    )
