from __future__ import annotations

from typing import Any

import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from httpx import AsyncClient

from ..api_client import get_backend_client
from ..dependencies import get_templates


router = APIRouter(prefix="/me", tags=["user"])
templates = get_templates()

# BOT_USERNAME нужен только чтобы собрать красивую ссылку на Mini App.
# Если переменной нет — всё равно покажем ref_code и статистику.
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")


def get_current_user_id(request: Request) -> int:
    """
    Берём user_id из request.state.user_id, который кладёт UserIDMiddleware.
    Все маршруты /me/* требуют авторизации.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не авторизован",
        )
    return int(user_id)


async def _get_user_obj(client: AsyncClient, user_id: int) -> dict[str, Any] | None:
    try:
        resp = await client.get(f"/api/v1/users/{int(user_id)}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None


@router.get("/referrals", response_class=HTMLResponse)
async def referrals_page(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Страница реферальной программы для текущего пользователя.
    - Данные берём из backend: /api/v1/referrals/by-user/{user_id}
    - Ссылку на Mini App строим через BOT_USERNAME (если задан).
    """
    user_id = get_current_user_id(request)

    user = await _get_user_obj(client, user_id)
    if not user:
        # Не фантазируем — если backend не знает такого юзера, отдаём 401
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")

    stats: dict[str, Any] | None = None
    deep_link: str | None = None

    try:
        resp = await client.get(f"/api/v1/referrals/by-user/{user_id}")
        if resp.status_code == 200:
            stats = resp.json() if isinstance(resp.json(), dict) else None
    except Exception:
        stats = None

    if stats:
        ref_code = (stats.get("ref_code") or "").strip()
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
