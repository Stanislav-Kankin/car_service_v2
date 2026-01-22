from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import get_db
from ..models.user import User
from ..models.user_session import UserSession
from ..schemas.user import UserRole


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()



async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve current user from server-side session cookie.

    IMPORTANT:
    - Do NOT trust user_id cookies.
    - Cookie stores raw session token, DB stores only SHA-256 hex token_hash.
    """
    cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "session_id")
    token = (request.cookies.get(cookie_name) or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token_hash = _sha256_hex(token)
    now = _now_utc()

    stmt = (
        select(UserSession)
        .where(UserSession.token_hash == token_hash)
        .where(UserSession.revoked_at.is_(None))
        .where(UserSession.expires_at > now)
        .limit(1)
    )
    sess = (await db.execute(stmt)).scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await db.get(User, int(sess.user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if getattr(user, "is_active", True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return current_user
