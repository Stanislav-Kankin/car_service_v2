from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.db import get_db
from backend.app.core.config import settings
from backend.app.services.user_service import UsersService
from backend.app.models.user import User
from backend.app.schemas.user import UserCreate, UserRole

import hashlib
import hmac
import urllib.parse
import json
import logging
from datetime import datetime, timezone

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


class TelegramAuthIn(BaseModel):
    init_data: str
    start_param: Optional[str] = None


def normalize_ref_code(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Telegram может прислать start_param как "ref_XXXX" или просто "XXXX"
    if s.lower().startswith("ref_"):
        s = s[4:]
    # отсекаем слишком длинные/странные значения (защита от мусора)
    s = s.strip()
    if not s or len(s) > 32:
        return None
    return s


def check_telegram_auth(init_data: str, bot_token: str) -> dict:
    """
    Строгая проверка подписи Telegram Mini App (WebApp initData).

    Актуальный алгоритм (Telegram Mini Apps / core.telegram.org):
    - Берём все пары key=value из init_data, исключая `hash` (и `signature`, если есть).
    - Сортируем по ключу.
    - Склеиваем через '\n' в data_check_string.
    - secret_key = HMAC_SHA256(key='WebAppData', msg=bot_token)  (в байтах)
    - expected_hash = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))
    """
    # Telegram передаёт initData как query string (urlencoded)
    pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)

    received_hash = None
    filtered: list[tuple[str, str]] = []
    for k, v in pairs:
        if k == "hash":
            received_hash = v
            continue
        # signature используется в режиме "Third-Party Use" (Ed25519). Для обычного WebApp initData он не нужен.
        if k == "signature":
            continue
        filtered.append((k, v))

    if not received_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid hash")

    filtered.sort(key=lambda kv: kv[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in filtered)

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if expected_hash != received_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid hash")

    # Возвращаем структуру в формате parse_qs, как ожидал остальной код ниже
    return urllib.parse.parse_qs(init_data)


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
            # Диагностика: выясняем, что реально пришло от webapp (без полного дампа init_data)
            init_data = payload.init_data or ""
            logger.warning(
                "Telegram WebApp auth: Invalid hash. init_data_len=%s has_user=%s has_hash=%s has_start_param=%s init_data_head=%r",
                len(init_data),
                ("user=" in init_data),
                ("hash=" in init_data),
                ("start_param=" in init_data),
                init_data[:120],
            )

            # В PROD/STAGING подпись Telegram обязана быть валидной.
            # Обход проверки допустим ТОЛЬКО в DEBUG-режиме для локальной разработки.
            if not settings.DEBUG:
                raise

            logger.warning(
                "Telegram WebApp auth: invalid hash (DEBUG MODE: пропускаем проверку подписи). "
                "Подробнее: %s",
                e.detail,
            )
            # DEBUG: Парсим init_data без проверки подписи
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

    # Рефералы: обеспечим ref_code даже для старых пользователей
    user = await UsersService.ensure_ref_code(db, user)

    # Рефералы: привязка по start_param
    start_param = payload.start_param
    if not start_param:
        # иногда start_param лежит прямо в init_data
        start_param = (parsed.get("start_param") or [None])[0]
    ref_code = normalize_ref_code(start_param)
    if ref_code and not getattr(user, "referred_by_user_id", None):
        # Ищем пригласившего
        res = await db.execute(select(User).where(User.ref_code == ref_code))
        referrer = res.scalar_one_or_none()
        if referrer and referrer.id != user.id:
            user.referred_by_user_id = referrer.id
            user.referred_at = datetime.now(timezone.utc)
            db.add(user)
            await db.commit()
            await db.refresh(user)

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

    return {"user_id": user.id}
