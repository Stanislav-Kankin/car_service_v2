from __future__ import annotations

import urllib.parse

import httpx
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from .config import settings


class UserIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user_id: int | None = None

        raw = request.cookies.get("user_id") or request.cookies.get("userId")
        if raw:
            try:
                user_id = int(raw)
            except (TypeError, ValueError):
                user_id = None

        if user_id is None:
            hdr = request.headers.get("x-user-id")
            if hdr:
                try:
                    user_id = int(hdr)
                except (TypeError, ValueError):
                    user_id = None

        request.state.user_id = user_id
        return await call_next(request)


class RegistrationGuardMiddleware(BaseHTTPMiddleware):
    _ALWAYS_ALLOW_PREFIXES = (
        "/static/",
        "/favicon.ico",
        "/robots.txt",
    )

    _PROTECTED_PREFIXES = (
        "/me/",
        "/admin/",
        "/sc/",
    )

    # Разрешённые пути без cookie (чтобы не было тупика):
    _ALLOW_WITHOUT_COOKIE = (
        "/me/register",
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

        # 2) НЕТ cookie => считаем пользователя незарегистрированным => жёстко на /me/register
        if not user_id:
            if path in self._ALLOW_WITHOUT_COOKIE:
                return await call_next(request)
            return RedirectResponse(url="/me/register", status_code=302)

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
            # backend недоступен => не пускаем в кабинет
            return RedirectResponse(url="/me/register", status_code=302)

        request.state.user_obj = user_obj

        full_name = ((user_obj or {}).get("full_name") or "").strip()
        phone = ((user_obj or {}).get("phone") or "").strip()
        profile_complete = bool(full_name) and bool(phone)

        # /me/register всегда разрешаем (иначе цикл)
        if path == "/me/register":
            return await call_next(request)

        # 4) Профиль не заполнен => на регистрацию
        if not profile_complete:
            next_url = str(request.url)
            parsed = urllib.parse.urlsplit(next_url)
            next_path = parsed.path
            if parsed.query:
                next_path = f"{next_path}?{parsed.query}"
            safe_next = urllib.parse.quote(next_path, safe="/?:=&")
            return RedirectResponse(url=f"/me/register?next={safe_next}", status_code=302)

        return await call_next(request)
