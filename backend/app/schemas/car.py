from typing import Optional

from pydantic import BaseModel, Field


class CarBase(BaseModel):
    user_id: int
    brand: str = Field(..., max_length=64)
    model: str = Field(..., max_length=64)
    year: Optional[int] = Field(None, ge=1900, le=2100)
    license_plate: Optional[str] = Field(None, max_length=32)
    vin: Optional[str] = Field(None, max_length=64)

    # Новые поля
    # engine_type: gasoline | diesel | hybrid | electric
    engine_type: Optional[str] = Field(None, max_length=20)
    engine_volume_l: Optional[float] = Field(None, ge=0)
    engine_power_kw: Optional[int] = Field(None, ge=0)


class CarCreate(CarBase):
    pass


class CarUpdate(BaseModel):
    brand: Optional[str] = Field(None, max_length=64)
    model: Optional[str] = Field(None, max_length=64)
    year: Optional[int] = Field(None, ge=1900, le=2100)
    license_plate: Optional[str] = Field(None, max_length=32)
    vin: Optional[str] = Field(None, max_length=64)

    engine_type: Optional[str] = Field(None, max_length=20)
    engine_volume_l: Optional[float] = Field(None, ge=0)
    engine_power_kw: Optional[int] = Field(None, ge=0)


class CarRead(BaseModel):
    id: int
    user_id: int
    brand: str
    model: str
    year: Optional[int]
    license_plate: Optional[str]
    vin: Optional[str]

    engine_type: Optional[str] = None
    engine_volume_l: Optional[float] = None
    engine_power_kw: Optional[int] = None

    class Config:
        from_attributes = True
