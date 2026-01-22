from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, func

from ..core.db import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, index=True, nullable=False)

    # SHA-256 hex от session token (сам токен хранится только в cookie у клиента)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
