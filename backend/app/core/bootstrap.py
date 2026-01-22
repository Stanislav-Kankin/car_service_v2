from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from ..models.user import User
from ..schemas.user import UserRole

logger = logging.getLogger(__name__)


def _normalize_emails(values: Iterable[str]) -> list[str]:
    res: list[str] = []
    for v in values:
        e = (v or "").strip().lower()
        if e:
            res.append(e)
    # unique
    return sorted(set(res))


async def ensure_initial_admins(db: AsyncSession) -> None:
    """
    Назначает роль admin пользователям, чьи email перечислены в INITIAL_ADMIN_EMAILS.
    ВАЖНО:
    - не создаёт пользователей
    - не понижает роль
    - идемпотентно: можно вызывать на каждом старте
    """
    emails = _normalize_emails(getattr(settings, "INITIAL_ADMIN_EMAILS", []) or [])
    if not emails:
        return

    stmt = select(User).where(User.email.is_not(None))
    users = (await db.execute(stmt)).scalars().all()

    promoted = 0
    for u in users:
        email = (getattr(u, "email", None) or "").strip().lower()
        if not email:
            continue
        if email in emails and getattr(u, "role", None) != UserRole.admin:
            u.role = UserRole.admin
            db.add(u)
            promoted += 1

    if promoted:
        await db.commit()
        logger.warning("Bootstrap: promoted %s user(s) to admin by INITIAL_ADMIN_EMAILS", promoted)
