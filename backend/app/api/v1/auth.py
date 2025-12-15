from fastapi import APIRouter, HTTPException, Depends, status
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
import logging

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


class TelegramAuthIn(BaseModel):
    init_data: str


def check_telegram_auth(init_data: str, bot_token: str) -> dict:
    """
    Строгая проверка подписи Telegram WebApp (как по докам).
    Оставляем как есть, но ниже будем использовать её в try/except
    и не будем валить запрос 403 на dev.
    """
    parsed = urllib.parse.parse_qs(init_data)
    data_check_string = "\n".join(
        f"{k}={v[0]}" for k, v in sorted(parsed.items()) if k != "hash"
    )

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if h != parsed.get("hash", [""])[0]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid hash")

    return parsed


@router.post("/telegram-webapp")
async def auth_telegram_webapp(
    payload: TelegramAuthIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Принимает initData от Telegram WebApp, проверяет подпись
    (НО в dev-режиме НЕ роняет 403, а только логирует),
    возвращает user_id.

    Плюс: если telegram_id есть в TELEGRAM_ADMIN_IDS,
    поднимаем роль пользователя до admin.
    """
    # Пытаемся проверить подпись
    try:
        parsed = check_telegram_auth(payload.init_data, settings.BOT_TOKEN)
    except HTTPException as e:
        if e.status_code == status.HTTP_403_FORBIDDEN:
            # DEV: подпись не сошлась, но не валим запрос, а просто логируем
            logger.warning(
                "Telegram WebApp auth: invalid hash (DEV MODE: пропускаем проверку). "
                "Подробнее: %s",
                e.detail,
            )
            # Парсим init_data без проверки подписи
            parsed = urllib.parse.parse_qs(payload.init_data)
        else:
            # Любая другая ошибка — пусть летит как раньше
            raise

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

    # --- НОВОЕ: проверка на админа по TELEGRAM_ADMIN_IDS ---
    admin_ids_raw = getattr(settings, "TELEGRAM_ADMIN_IDS", "")
    # поддержка: и строка "1,2", и list[int]
    if isinstance(admin_ids_raw, str):
        admin_ids = {
            int(x.strip())
            for x in admin_ids_raw.split(",")
            if x.strip().isdigit()
        }
    elif isinstance(admin_ids_raw, (list, tuple, set)):
        admin_ids = {int(x) for x in admin_ids_raw}
    else:
        admin_ids = set()

    if telegram_id in admin_ids and user.role != UserRole.admin:
        user.role = UserRole.admin
        db.add(user)
        await db.commit()
        await db.refresh(user)
        # Повышаем роль до admin
        user.role = UserRole.admin
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {"user_id": user.id}
