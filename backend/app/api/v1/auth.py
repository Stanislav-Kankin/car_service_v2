from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.services.user_service import UserService
from backend.app.core.config import settings

import hashlib
import hmac
import urllib.parse

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
    db: AsyncSession = Depends(get_db)
):
    """
    Принимает initData от Telegram WebApp, проверяет подпись,
    возвращает user_id.
    """
    parsed = check_telegram_auth(payload.init_data, settings.BOT_TOKEN)

    tg_user = parsed.get("user", [None])[0]
    if tg_user is None:
        raise HTTPException(400, "No user in initData")

    import json
    tg_user = json.loads(tg_user)

    telegram_id = tg_user.get("id")
    if not telegram_id:
        raise HTTPException(400, "Invalid user data")

    # Ищем юзера в базе
    user = await UserService.get_user_by_telegram_id(db, telegram_id)

    # Если нет — создаём пустого (webapp-first регистрация)
    if not user:
        user = await UserService.create_user(
            db=db,
            telegram_id=telegram_id,
            name=tg_user.get("first_name", "Пользователь"),
        )

    return {"user_id": user.id}
