from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, func, BigInteger
from sqlalchemy.orm import relationship

from ..core.db import Base
from ..schemas.user import UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Telegram
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=True)

    # Профиль
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    city = Column(String, nullable=True)

    # Рефералы
    # ref_code: код, который пользователь может шарить (формируется из user.id, см. UsersService)
    ref_code = Column(String(32), nullable=True, index=True)
    # кто привёл (user_id пригласившего)
    referred_by_user_id = Column(Integer, nullable=True, index=True)
    # когда зафиксировали привязку реферала
    referred_at = Column(DateTime(timezone=True), nullable=True)
    # когда реферал подтвердился (например, после заполнения телефона)
    ref_confirmed_at = Column(DateTime(timezone=True), nullable=True)


    role = Column(Enum(UserRole), nullable=False, default=UserRole.client)
    is_active = Column(Boolean, default=True)

    # Бонусы
    bonus_balance = Column(Integer, default=0)

    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ==========
    # Связи
    # ==========

    # 1) Владелец СТО
    # В ServiceCenter ожидается что-то типа:
    # owner = relationship("User", back_populates="service_centers")
    service_centers = relationship(
        "ServiceCenter",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    # 2) Машины пользователя (гараж)
    # В Car ожидается:
    # user = relationship("User", back_populates="cars")
    cars = relationship(
        "Car",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # 3) Заявки клиента
    # В Request ожидается:
    # user = relationship("User", back_populates="requests")
    requests = relationship(
        "Request",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # 4) Бонусные транзакции
    # В BonusTransaction ожидается:
    # user = relationship("User", back_populates="bonus_transactions")
    bonus_transactions = relationship(
        "BonusTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    service_centers = relationship(
        "ServiceCenter",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    cars = relationship(
        "Car",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    requests = relationship(
        "Request",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    bonus_transactions = relationship(
        "BonusTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
    )
