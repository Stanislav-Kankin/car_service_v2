from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.db import get_db
from backend.app.core.config import settings
from backend.app.services.user_service import UsersService
from backend.app.models.user import User
from backend.app.models.otp_code import OtpCode
from backend.app.models.user_session import UserSession
from backend.app.schemas.user import UserCreate, UserRole

import hashlib
import hmac
import urllib.parse
import json
import logging
from datetime import datetime, timezone, timedelta
import secrets
import re

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


class TelegramAuthIn(BaseModel):
    init_data: str
    start_param: Optional[str] = None


class OtpRequestIn(BaseModel):
    phone: str


class OtpVerifyIn(BaseModel):
    phone: str
    code: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_phone(raw: str) -> str:
    # Оставляем только цифры
    digits = re.sub(r"\D+", "", (raw or "").strip())
    if not digits:
        return ""
    # РФ: 8XXXXXXXXXX -> 7XXXXXXXXXX
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    # РФ: 10 цифр -> считаем как +7XXXXXXXXXX
    if len(digits) == 10:
        digits = "7" + digits
    # Возвращаем в виде +<digits>
    return f"+{digits}"


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
    Строгая проверка подписи Telegram Mini App (Telegram.WebApp.initData).

    По официальной документации Telegram:
    - data_check_string: все пары key=value из initData, кроме hash, отсортировать по key и склеить через '\n'
    - secret_key = HMAC_SHA256(key='WebAppData', msg=bot_token)
    - expected_hash = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))
    """
    parsed = urllib.parse.parse_qs(init_data, keep_blank_values=True)

    received_hash = parsed.get("hash", [""])[0]
    if not received_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid hash")

    data_check_string = "\n".join(
        f"{k}={v[0]}" for k, v in sorted(parsed.items()) if k != "hash"
    )

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if expected_hash != received_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid hash")

    return parsed


@router.post("/telegram-webapp")
async def auth_telegram_webapp(
    payload: TelegramAuthIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Telegram WebApp auth (оставлено для совместимости).
    В ветке app основная авторизация — по телефону + OTP.
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


@router.post("/otp/request")
async def otp_request(
    payload: OtpRequestIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Запрос одноразового кода (OTP) для входа по телефону.
    """
    phone = _normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone")

    now = _now_utc()
    cooldown = int(getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 30))
    ttl = int(getattr(settings, "OTP_TTL_SECONDS", 300))

    # Простая защита от частых запросов: если в cooldown уже запрашивали — 429
    recent_stmt = (
        select(OtpCode)
        .where(OtpCode.phone == phone)
        .where(OtpCode.created_at >= (now - timedelta(seconds=cooldown)))
        .order_by(OtpCode.id.desc())
        .limit(1)
    )
    recent = (await db.execute(recent_stmt)).scalar_one_or_none()
    if recent:
        raise HTTPException(status_code=429, detail="Too many requests")

    # Инвалидируем старые активные коды по телефону (без удаления)
    await db.execute(
        update(OtpCode)
        .where(OtpCode.phone == phone)
        .where(OtpCode.used_at.is_(None))
        .where(OtpCode.expires_at > now)
        .values(expires_at=now)
    )

    code = f"{secrets.randbelow(1000000):06d}"
    code_hash = _sha256_hex(code)

    otp = OtpCode(
        phone=phone,
        code_hash=code_hash,
        attempts=0,
        expires_at=now + timedelta(seconds=ttl),
        used_at=None,
    )
    db.add(otp)
    await db.commit()

    # TODO: здесь подключится реальный SMS-провайдер.
    # В staging/dev для теста можем вернуть код в ответе (только если DEBUG или DEV_SMS_RETURN_CODE).
    dev_return = bool(getattr(settings, "DEBUG", False)) or bool(getattr(settings, "DEV_SMS_RETURN_CODE", False))
    if dev_return:
        logger.warning("OTP DEV MODE: phone=%s code=%s", phone, code)
        return {"ok": True, "dev_code": code}

    # В проде не светим код
    logger.info("OTP requested: phone=%s", phone)
    return {"ok": True}


@router.post("/otp/verify")
async def otp_verify(
    payload: OtpVerifyIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Проверка OTP и выдача server-side сессии (session_id cookie).
    """
    phone = _normalize_phone(payload.phone)
    code = (payload.code or "").strip()
    if not phone or not code or not code.isdigit():
        raise HTTPException(status_code=400, detail="Invalid payload")

    now = _now_utc()
    max_attempts = int(getattr(settings, "OTP_MAX_ATTEMPTS", 5))

    stmt = (
        select(OtpCode)
        .where(OtpCode.phone == phone)
        .where(OtpCode.used_at.is_(None))
        .where(OtpCode.expires_at > now)
        .order_by(OtpCode.id.desc())
        .limit(1)
    )
    otp = (await db.execute(stmt)).scalar_one_or_none()
    if not otp:
        raise HTTPException(status_code=400, detail="OTP expired or not found")

    if int(getattr(otp, "attempts", 0)) >= max_attempts:
        raise HTTPException(status_code=403, detail="Too many attempts")

    if otp.code_hash != _sha256_hex(code):
        otp.attempts = int(getattr(otp, "attempts", 0)) + 1
        db.add(otp)
        await db.commit()
        raise HTTPException(status_code=403, detail="Invalid code")

    # Код валиден
    otp.used_at = now
    db.add(otp)
    await db.commit()

    # Находим/создаём пользователя по телефону
    user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if not user:
        user_in = UserCreate(
            telegram_id=None,
            full_name=None,
            phone=phone,
            city=None,
            role=UserRole.client,
        )
        user = await UsersService.create_user(db, user_in)

        # Реф-код — делаем детерминированный (без вызова ensure_ref_code, чтобы не зависеть от внешних побочных эффектов)
        user.ref_code = UsersService.make_ref_code(user.id)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Создаём сессию
    ttl_seconds = int(getattr(settings, "AUTH_SESSION_TTL_SECONDS", 2592000))
    session_token = secrets.token_urlsafe(32)
    session_hash = _sha256_hex(session_token)

    sess = UserSession(
        user_id=int(user.id),
        token_hash=session_hash,
        expires_at=now + timedelta(seconds=ttl_seconds),
        revoked_at=None,
    )
    db.add(sess)
    await db.commit()

    # Устанавливаем cookie (HttpOnly, Secure)
    cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "session_id")
    cookie_domain = getattr(settings, "AUTH_COOKIE_DOMAIN", ".dev-cloud-ksa.ru")
    cookie_samesite = str(getattr(settings, "AUTH_COOKIE_SAMESITE", "none")).lower()
    cookie_secure = bool(getattr(settings, "AUTH_COOKIE_SECURE", True))

    response.set_cookie(
        key=cookie_name,
        value=session_token,
        max_age=ttl_seconds,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,  # type: ignore[arg-type]
        domain=cookie_domain,
        path="/",
    )

    return {"ok": True, "user_id": int(user.id)}


@router.get("/session")
async def auth_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Возвращает user_id по текущей cookie session_id.
    Используется WebApp middleware для восстановления request.state.user_id.
    """
    cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "session_id")
    token = (request.cookies.get(cookie_name) or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

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
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {"user_id": int(sess.user_id)}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Отзывает текущую сессию и удаляет cookie.
    """
    cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "session_id")
    token = (request.cookies.get(cookie_name) or "").strip()
    if token:
        token_hash = _sha256_hex(token)
        now = _now_utc()
        sess = (
            await db.execute(select(UserSession).where(UserSession.token_hash == token_hash).limit(1))
        ).scalar_one_or_none()
        if sess and sess.revoked_at is None:
            sess.revoked_at = now
            db.add(sess)
            await db.commit()

    cookie_domain = getattr(settings, "AUTH_COOKIE_DOMAIN", ".dev-cloud-ksa.ru")
    response.delete_cookie(cookie_name, path="/")
    response.delete_cookie(cookie_name, path="/", domain=cookie_domain)
    return {"ok": True}
