from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.db import Base


class ServiceCenter(Base):
    """
    Сервисный центр (СТО).
    org_type:
      - "individual" — частный мастер (ФЛ)
      - "company"   — юридическое лицо (ООО/ИП и т.д.)
    """

    __tablename__ = "service_centers"

    id = Column(Integer, primary_key=True, index=True)

    # владелец/менеджер СТО (User)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(255), nullable=False)

    address = Column(String(500), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    phone = Column(String(32), nullable=True)
    website = Column(String(255), nullable=True)

    # соцсети/контакты в виде JSON
    social_links = Column(JSON, nullable=True)

    # список специализаций (строковые коды)
    specializations = Column(JSON, nullable=True)

    org_type = Column(String(20), nullable=True)

    # Сегментация/категория СТО (для фильтров/плашек в UI).
    # Значения: premium_plus / official / multibrand / club / specialized / unspecified
    segment = Column(String(20), nullable=False, server_default="unspecified")

    # выездной мастер/эвакуатор
    is_mobile_service = Column(Boolean, nullable=True, default=False)
    has_tow_truck = Column(Boolean, nullable=True, default=False)

    # модерация
    is_active = Column(Boolean, nullable=False, default=False)

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
    owner = relationship("User", back_populates="service_centers")
    wallet = relationship(
        "ServiceCenterWallet",
        back_populates="service_center",
        uselist=False,
        cascade="all, delete-orphan",
    )
    offers = relationship("Offer", back_populates="service_center")
    requests = relationship("Request", back_populates="service_center")

    # распределения заявок по этому СТО
    request_distributions = relationship(
        "RequestDistribution",
        back_populates="service_center",
        cascade="all, delete-orphan",
    )
