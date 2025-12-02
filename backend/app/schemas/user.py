from typing import Optional

from pydantic import BaseModel, Field

from backend.app.models.user import UserRole


class UserBase(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    city: Optional[str] = Field(None, max_length=100)
    role: UserRole = UserRole.CLIENT


class UserCreate(UserBase):
    telegram_id: Optional[int] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    city: Optional[str] = Field(None, max_length=100)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserRead(BaseModel):
    id: int
    telegram_id: Optional[int]
    full_name: Optional[str]
    phone: Optional[str]
    city: Optional[str]
    role: UserRole
    is_active: bool
    bonus_balance: int

    class Config:
        from_attributes = True  # Pydantic v2: заменяет orm_mode
