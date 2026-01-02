from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from httpx import AsyncClient

from webapp.app.api_client import get_backend_client
from webapp.app.dependencies import get_current_user
from webapp.app.config import BOT_USERNAME


templates = Jinja2Templates(directory="webapp/app/templates")
router = APIRouter(prefix="/me", tags=["user"])


@router.get("/referrals", response_class=HTMLResponse)
async def referrals_page(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    user=Depends(get_current_user),
):
    stats: Optional[dict[str, Any]] = None
    deep_link: Optional[str] = None

    resp = await client.get(f"/api/v1/referrals/by-user/{user.id}")
    if resp.status_code == 200:
        stats = resp.json()
        ref_code = stats.get("ref_code")
        if BOT_USERNAME and ref_code:
            deep_link = f"https://t.me/{BOT_USERNAME}?startapp=ref_{ref_code}"

    return templates.TemplateResponse(
        "user/referral.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "deep_link": deep_link,
        },
    )
