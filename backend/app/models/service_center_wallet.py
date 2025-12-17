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


class ServiceCenterWalletTxType(str, Enum):
    # Пополнение админом (взнос/депозит)
    ADMIN_CREDIT = "admin_credit"

    # Списание (платформа/комиссия/действие) — на будущее
    DEBIT = "debit"

    # Корректировка админом — на будущее
    ADMIN_ADJUST = "admin_adjust"


class ServiceCenterWallet(Base):
    __tablename__ = "service_center_wallets"

    id = Column(Integer, primary_key=True, index=True)

    service_center_id = Column(
        Integer,
        ForeignKey("service_centers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Текущий баланс (в условных "рублях"/баллах)
    balance = Column(Integer, nullable=False, default=0)

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
    service_center = relationship("ServiceCenter", back_populates="wallet")
    transactions = relationship(
        "ServiceCenterWalletTransaction",
        back_populates="wallet",
        cascade="all, delete-orphan",
        order_by="ServiceCenterWalletTransaction.id.desc()",
    )


class ServiceCenterWalletTransaction(Base):
    __tablename__ = "service_center_wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)

    wallet_id = Column(
        Integer,
        ForeignKey("service_center_wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    service_center_id = Column(
        Integer,
        ForeignKey("service_centers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # положительное число — пополнение, отрицательное — списание
    amount = Column(Integer, nullable=False)

    tx_type = Column(
        SAEnum(ServiceCenterWalletTxType),
        nullable=False,
        default=ServiceCenterWalletTxType.ADMIN_CREDIT,
    )

    description = Column(String(255), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -------- связи --------
    wallet = relationship("ServiceCenterWallet", back_populates="transactions")
