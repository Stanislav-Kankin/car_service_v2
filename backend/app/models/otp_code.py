from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, func

from ..core.db import Base


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)

    # Нормализованный телефон (храним как строку)
    phone = Column(String(32), index=True, nullable=False)

    # SHA-256 hex от кода
    code_hash = Column(String(64), nullable=False)

    # Ограничение попыток ввода
    attempts = Column(Integer, nullable=False, default=0)

    # Статусы/времена
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
