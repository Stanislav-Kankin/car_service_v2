
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class UserIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware, который вытаскивает user_id из cookie
    и кладёт его в request.state.user_id.

    Cookie ставится из base.html через вызов /api/v1/auth/telegram-webapp.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user_id: int | None = None
        raw = request.cookies.get("user_id")
        if raw is not None:
            try:
                user_id = int(raw)
            except ValueError:
                user_id = None

        # user_id = None если не авторизован
        request.state.user_id = user_id

        response = await call_next(request)
        return response
