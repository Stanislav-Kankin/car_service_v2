from sqlalchemy import (
    Column,
    DateTime,
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

    # Владелец машины
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    license_plate = Column(String, nullable=True)
    vin = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

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
