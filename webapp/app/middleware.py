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

    _REGISTER_PATHS = ("/me/register", "/me/register/")

    def _clear_user_cookie(self, resp: Response) -> None:
        resp.delete_cookie("user_id", path="/")
        resp.delete_cookie("user_id", path="/", domain=".dev-cloud-ksa.ru")
        resp.delete_cookie("userId", path="/")
        resp.delete_cookie("userId", path="/", domain=".dev-cloud-ksa.ru")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path or "/"

        if path.startswith(self._ALWAYS_ALLOW_PREFIXES):
            return await call_next(request)

        # /me/register всегда доступен (но сам handler решит, что делать без cookie)
        if path in self._REGISTER_PATHS:
            return await call_next(request)

        # Не защищённые страницы не трогаем
        if not path.startswith(self._PROTECTED_PREFIXES):
            return await call_next(request)

        user_id = getattr(request.state, "user_id", None)

        # ✅ КЛЮЧЕВОЕ: если cookie нет — НЕ /me/register, а /
        if not user_id:
            return RedirectResponse(url="/", status_code=302)

        # грузим пользователя
        try:
            async with httpx.AsyncClient(base_url=str(settings.BACKEND_API_URL), timeout=10.0) as client:
                resp = await client.get(f"/api/v1/users/{int(user_id)}")

                if resp.status_code == 404:
                    r = RedirectResponse(url="/", status_code=302)
                    self._clear_user_cookie(r)
                    return r

                resp.raise_for_status()
                user_obj = resp.json()
        except Exception:
            return RedirectResponse(url="/", status_code=302)

        request.state.user_obj = user_obj

        full_name = ((user_obj or {}).get("full_name") or "").strip()
        phone = ((user_obj or {}).get("phone") or "").strip()
        profile_complete = bool(full_name) and bool(phone)

        if not profile_complete:
            next_url = str(request.url)
            parsed = urllib.parse.urlsplit(next_url)
            next_path = parsed.path
            if parsed.query:
                next_path = f"{next_path}?{parsed.query}"
            safe_next = urllib.parse.quote(next_path, safe="/?:=&")
            return RedirectResponse(url=f"/me/register?next={safe_next}", status_code=302)

        return await call_next(request)
