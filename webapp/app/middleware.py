from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

import urllib.parse

import httpx

from .config import settings


class UserIDMiddleware(BaseHTTPMiddleware):
    """
    Достаём user_id из cookie и кладём в request.state.user_id.

    Поддерживаем:
      - cookie: user_id (основная)
      - cookie: userId (на всякий случай, если где-то был другой нейминг)
      - header: X-User-Id (если когда-то понадобится проксировать/пробрасывать)
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user_id: int | None = None

        # 1) Cookie (основной сценарий)
        raw = request.cookies.get("user_id") or request.cookies.get("userId")
        if raw:
            try:
                user_id = int(raw)
            except (TypeError, ValueError):
                user_id = None

        # 2) Fallback: header (не мешает, но может спасти при прокси/диагностике)
        if user_id is None:
            hdr = request.headers.get("x-user-id")
            if hdr:
                try:
                    user_id = int(hdr)
                except (TypeError, ValueError):
                    user_id = None

        request.state.user_id = user_id

        response = await call_next(request)
        return response


class RegistrationGuardMiddleware(BaseHTTPMiddleware):
    """
    Жёсткий guard регистрации для WebApp.

    Правила (как в ТЗ):
    - user_id cookie должен быть проставлен через Telegram WebApp auth
    - если пользователь новый ИЛИ full_name пустой ИЛИ phone пустой =>
      НЕЛЬЗЯ попасть в /me/*, /sc/*, /admin/* (кроме /me/register и /me/dashboard)
      -> редирект на /me/register
    - /me/dashboard допускается БЕЗ cookie, чтобы отработал JS auth
      (но с cookie и без профиля -> редирект на /me/register)
    """

    # Публичные/служебные пути, которые никогда не должны редиректиться
    _ALWAYS_ALLOW_PREFIXES = (
        "/static/",
        "/favicon.ico",
        "/robots.txt",
    )

    # Пути, которые допускаются при отсутствии cookie
    _ALLOW_WITHOUT_COOKIE = (
        "/",
        "/me/dashboard",
        "/me/register",
    )

    # Зоны, которые требуют (1) cookie и (2) полного профиля
    _PROTECTED_PREFIXES = (
        "/me/",
        "/admin/",
        "/sc/",
    )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path or "/"

        # 0) Статика/служебные — пропускаем
        if path.startswith(self._ALWAYS_ALLOW_PREFIXES):
            return await call_next(request)

        # 1) Если это не защищённая зона — пропускаем
        if not path.startswith(self._PROTECTED_PREFIXES):
            return await call_next(request)

        user_id = getattr(request.state, "user_id", None)

        # 2) Если cookie нет — разрешаем только /me/dashboard и /me/register
        if not user_id:
            if path in self._ALLOW_WITHOUT_COOKIE:
                return await call_next(request)
            # Любые другие попытки попасть в кабинет — возвращаем на dashboard,
            # чтобы JS auth проставил cookie.
            return RedirectResponse(url="/me/dashboard", status_code=302)

        # 3) Есть cookie: грузим user из backend и проверяем заполненность профиля
        user_obj: dict | None = None
        try:
            async with httpx.AsyncClient(base_url=str(settings.BACKEND_API_URL), timeout=10.0) as client:
                resp = await client.get(f"/api/v1/users/{int(user_id)}")
                if resp.status_code == 404:
                    user_obj = None
                else:
                    resp.raise_for_status()
                    user_obj = resp.json()
        except Exception:
            # Если backend временно недоступен — НЕ пускаем дальше в кабинет,
            # иначе будет куча ошибок в роутерах.
            return RedirectResponse(url="/me/dashboard", status_code=302)

        request.state.user_obj = user_obj

        full_name = ((user_obj or {}).get("full_name") or "").strip()
        phone = ((user_obj or {}).get("phone") or "").strip()
        profile_complete = bool(full_name) and bool(phone)

        # 4) /me/register всегда можно открыть (иначе будет цикл)
        if path == "/me/register":
            return await call_next(request)

        # 5) /me/dashboard: без профиля — на регистрацию
        if path == "/me/dashboard" and not profile_complete:
            return RedirectResponse(url="/me/register", status_code=302)

        # 6) Любые защищённые зоны: если профиль не заполнен — на регистрацию
        if not profile_complete:
            next_url = str(request.url)
            # Оставляем только path+query, без схемы/домена
            parsed = urllib.parse.urlsplit(next_url)
            next_path = parsed.path
            if parsed.query:
                next_path = f"{next_path}?{parsed.query}"

            safe_next = urllib.parse.quote(next_path, safe="/?:=&")
            return RedirectResponse(url=f"/me/register?next={safe_next}", status_code=302)

        return await call_next(request)
