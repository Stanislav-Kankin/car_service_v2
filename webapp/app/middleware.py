from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


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
