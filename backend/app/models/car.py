from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Float,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from ..core.db import Base


class Car(Base):
    __tablename__ = "cars"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user = relationship("User", back_populates="cars")

    brand = Column(String, nullable=False)
    model = Column(String, nullable=False)
    year = Column(Integer, nullable=True)

    license_plate = Column(String, nullable=True)
    vin = Column(String, nullable=True)

    # Новые поля (безопасно добавляются через safe_migrations)
    # engine_type: gasoline | diesel | hybrid | electric
    engine_type = Column(String(20), nullable=True)
    engine_volume_l = Column(Float, nullable=True)
    engine_power_kw = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
