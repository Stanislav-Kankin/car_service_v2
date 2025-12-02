from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CarBase(BaseModel):
    brand: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    year: Optional[int] = None
    license_plate: Optional[str] = Field(None, max_length=32)
    vin: Optional[str] = Field(None, max_length=64)


class CarCreate(CarBase):
    user_id: int  # владелец машины


class CarUpdate(BaseModel):
    brand: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    year: Optional[int] = None
    license_plate: Optional[str] = Field(None, max_length=32)
    vin: Optional[str] = Field(None, max_length=64)


class CarRead(BaseModel):
    id: int
    user_id: int

    brand: Optional[str]
    model: Optional[str]
    year: Optional[int]
    license_plate: Optional[str]
    vin: Optional[str]

    created_at: datetime

    class Config:
        from_attributes = True
