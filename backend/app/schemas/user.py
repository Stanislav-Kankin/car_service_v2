from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class UserRole(str, Enum):
    client = "client"
    service_owner = "service_owner"
    admin = "admin"


class UserBase(BaseModel):
    telegram_id: Optional[int] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = True


class UserCreate(UserBase):
    telegram_id: int
    role: Optional[UserRole] = UserRole.client


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserRead(UserBase):
    id: int
    bonus_balance: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
