from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import get_db
from ...models.user import User
from ...services.user_service import UsersService


router = APIRouter(prefix="/referrals", tags=["referrals"])


class ReferralRecentItem(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    role: Optional[str] = None
    created_at: Optional[datetime] = None
    ref_confirmed_at: Optional[datetime] = None


class ReferralStatsOut(BaseModel):
    user_id: int
    ref_code: str
    referred_by_user_id: Optional[int] = None
    referred_at: Optional[datetime] = None
    invited_total: int
    invited_confirmed: int
    invited_by_role: Dict[str, int]
    recent: List[ReferralRecentItem]


@router.get("/by-user/{user_id}", response_model=ReferralStatsOut)
async def referral_stats_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user = await UsersService.ensure_ref_code(db, user)

    # totals
    total_stmt = select(func.count(User.id)).where(User.referred_by_user_id == user_id)
    confirmed_stmt = select(func.count(User.id)).where(
        User.referred_by_user_id == user_id,
        User.ref_confirmed_at.isnot(None),
    )

    total = (await db.execute(total_stmt)).scalar_one()
    confirmed = (await db.execute(confirmed_stmt)).scalar_one()

    # by role
    by_role_stmt = (
        select(User.role, func.count(User.id))
        .where(User.referred_by_user_id == user_id)
        .group_by(User.role)
    )
    res = await db.execute(by_role_stmt)
    invited_by_role = {str(role): int(cnt) for role, cnt in res.all()}

    # recent 10
    recent_stmt = (
        select(User)
        .where(User.referred_by_user_id == user_id)
        .order_by(User.created_at.desc())
        .limit(10)
    )
    recent_res = await db.execute(recent_stmt)
    recent_users = list(recent_res.scalars().all())

    recent = [
        ReferralRecentItem(
            user_id=u.id,
            full_name=u.full_name,
            role=str(u.role) if u.role is not None else None,
            created_at=getattr(u, "created_at", None),
            ref_confirmed_at=getattr(u, "ref_confirmed_at", None),
        )
        for u in recent_users
    ]

    return ReferralStatsOut(
        user_id=user.id,
        ref_code=user.ref_code,
        referred_by_user_id=getattr(user, "referred_by_user_id", None),
        referred_at=getattr(user, "referred_at", None),
        invited_total=int(total or 0),
        invited_confirmed=int(confirmed or 0),
        invited_by_role=invited_by_role,
        recent=recent,
    )
