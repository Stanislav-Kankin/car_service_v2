from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.config import settings
from backend.app.services.user_service import UsersService
from backend.app.schemas.user import UserCreate, UserRole

import hashlib
import hmac
import urllib.parse
import json

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthIn(BaseModel):
    init_data: str


def check_telegram_auth(init_data: str, bot_token: str) -> dict:
    """
    Проверка подписи Telegram WebApp.
    """
    parsed = urllib.parse.parse_qs(init_data)
    data_check_string = "\n".join(
        f"{k}={v[0]}" for k, v in sorted(parsed.items()) if k != "hash"
    )

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if h != parsed.get("hash", [""])[0]:
        raise HTTPException(status_code=403, detail="Invalid hash")

    return parsed


@router.post("/telegram-webapp")
async def auth_telegram_webapp(
    payload: TelegramAuthIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Принимает initData от Telegram WebApp, проверяет подпись,
    возвращает user_id.
    """
    parsed = check_telegram_auth(payload.init_data, settings.BOT_TOKEN)

    tg_user_raw = parsed.get("user", [None])[0]
    if tg_user_raw is None:
        raise HTTPException(status_code=400, detail="No user in initData")

    try:
        tg_user = json.loads(tg_user_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user JSON")

    telegram_id = tg_user.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Invalid user data")

    # Ищем юзера в базе по Telegram ID
    user = await UsersService.get_user_by_telegram(db, telegram_id)

    # Если нет — создаём (webapp-first регистрация)
    if not user:
        user_in = UserCreate(
            telegram_id=telegram_id,
            full_name=tg_user.get("first_name") or "Пользователь",
            phone=None,
            city=None,
            role=UserRole.client,
        )
        user = await UsersService.create_user(db, user_in)

    return {"user_id": user.id}
