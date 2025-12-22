from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
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

    brand = Column(String, nullable=False)
    model = Column(String, nullable=False)
    year = Column(Integer, nullable=True)

    license_plate = Column(String, nullable=True)
    vin = Column(String, nullable=True)

    # Новые поля (добавляются через safe_migrations)
    # engine_type: gasoline | diesel | hybrid | electric
    engine_type = Column(String(20), nullable=True)
    engine_volume_l = Column(Float, nullable=True)     # литры (для ДВС/гибридов)
    engine_power_kw = Column(Integer, nullable=True)   # кВт (для электромобилей)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ---------- связи ----------

    # Владелец: User.cars <-> Car.user
    user = relationship(
        "User",
        back_populates="cars",
    )

    # Заявки по этой машине: Request.car <-> Car.requests
    requests = relationship(
        "Request",
        back_populates="car",
        cascade="all, delete-orphan",
    )
