from __future__ import annotations

import urllib.parse

import httpx
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from .config import settings


class SessionMiddleware(BaseHTTPMiddleware):
    """
    Восстанавливает user_id из server-side сессии (cookie session_id).

    Логика:
    - если session_id нет -> user_id=None
    - если session_id есть -> проверяем через backend /api/v1/auth/session
    """
    _COOKIE_NAME = "session_id"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user_id: int | None = None

        token = (request.cookies.get(self._COOKIE_NAME) or "").strip()
        if token:
            try:
                async with httpx.AsyncClient(base_url=str(settings.BACKEND_API_URL), timeout=10.0) as client:
                    resp = await client.get(
                        "/api/v1/auth/session",
                        headers={"Cookie": f"{self._COOKIE_NAME}={token}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json() or {}
                        raw_uid = data.get("user_id")
                        if raw_uid is not None:
                            user_id = int(raw_uid)
            except Exception:
                # backend недоступен/ошибка — считаем что не авторизован
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

    def _clear_auth_cookie(self, resp: Response) -> None:
        # Новая cookie
        resp.delete_cookie("session_id", path="/")
        resp.delete_cookie("session_id", path="/", domain=".dev-cloud-ksa.ru")

        # Legacy cookies (на всякий случай, чтобы не мешали тестам)
        resp.delete_cookie("user_id", path="/")
        resp.delete_cookie("user_id", path="/", domain=".dev-cloud-ksa.ru")
        resp.delete_cookie("userId", path="/")
        resp.delete_cookie("userId", path="/", domain=".dev-cloud-ksa.ru")

    def _build_next_path(self, request: Request) -> str:
        # path + query (без домена)
        path = request.url.path or "/"
        qs = request.url.query
        if qs:
            return f"{path}?{qs}"
        return path

    def _redirect_to_entry_with_next(self, request: Request) -> RedirectResponse:
        next_path = self._build_next_path(request)
        safe_next = urllib.parse.quote(next_path, safe="/?:=&")
        return RedirectResponse(url=f"/?next={safe_next}", status_code=302)

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

        # Если сессии нет — ведём на "/" с next
        if not user_id:
            return self._redirect_to_entry_with_next(request)

        # грузим пользователя
        try:
            async with httpx.AsyncClient(base_url=str(settings.BACKEND_API_URL), timeout=10.0) as client:
                resp = await client.get(f"/api/v1/users/{int(user_id)}")

                if resp.status_code == 404:
                    r = self._redirect_to_entry_with_next(request)
                    self._clear_auth_cookie(r)
                    return r

                resp.raise_for_status()
                user_obj = resp.json()
        except Exception:
            # backend недоступен/ошибка — всё равно ведём на "/" с next (без цикла)
            return self._redirect_to_entry_with_next(request)

        request.state.user_obj = user_obj

        full_name = ((user_obj or {}).get("full_name") or "").strip()
        phone = ((user_obj or {}).get("phone") or "").strip()
        profile_complete = bool(full_name) and bool(phone)

        if not profile_complete:
            next_path = self._build_next_path(request)
            safe_next = urllib.parse.quote(next_path, safe="/?:=&")
            return RedirectResponse(url=f"/me/register?next={safe_next}", status_code=302)

        # ADMIN-only guard (UI уровень; backend всё равно должен проверять роль)
        if path.startswith("/admin/"):
            role = ((user_obj or {}).get("role") or "").strip().lower()
            if role != "admin":
                return RedirectResponse(url="/me/dashboard", status_code=302)

        return await call_next(request)
