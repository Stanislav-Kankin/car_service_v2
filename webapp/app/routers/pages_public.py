from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["public"])


@router.get("/", response_class=HTMLResponse)
async def index(_: Request) -> HTMLResponse:
    # Публичная заглушка. Mini App обычно открывает /me/dashboard.
    return HTMLResponse("CarBot WebApp is running")


@router.get("/health", response_class=HTMLResponse)
async def health(_: Request) -> HTMLResponse:
    return HTMLResponse("ok")


# Исторический маршрут /register — больше не используем.
# Жёсткая регистрация только через /me/register.
@router.get("/register")
async def register_redirect(_: Request) -> RedirectResponse:
    return RedirectResponse("/me/register", status_code=302)


@router.post("/register")
async def register_redirect_post(_: Request) -> RedirectResponse:
    return RedirectResponse("/me/register", status_code=302)
