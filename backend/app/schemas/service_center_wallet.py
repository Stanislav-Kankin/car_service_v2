from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


class ServiceCenterWalletTxType(str, Enum):
    ADMIN_CREDIT = "admin_credit"
    DEBIT = "debit"
    ADMIN_ADJUST = "admin_adjust"


class ServiceCenterWalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_center_id: int
    balance: int
    created_at: datetime
    updated_at: datetime


class ServiceCenterWalletTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wallet_id: int
    service_center_id: int
    amount: int
    tx_type: ServiceCenterWalletTxType
    description: Optional[str] = None
    created_at: datetime


class ServiceCenterWalletWithTransactions(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet: ServiceCenterWalletRead
    transactions: List[ServiceCenterWalletTransactionRead]


class ServiceCenterWalletCreditIn(BaseModel):
    amount: int = Field(..., ge=1, description="Сумма пополнения (в рублях/баллах).")
    description: Optional[str] = Field(default=None, max_length=255)
    tx_type: ServiceCenterWalletTxType = Field(default=ServiceCenterWalletTxType.ADMIN_CREDIT)
