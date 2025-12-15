from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import pages_public, pages_user, pages_service_center, pages_admin
from .middleware import RegistrationGuardMiddleware, UserIDMiddleware

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="CarBot WebApp",
        debug=settings.DEBUG,
    )

    # Статика (CSS/JS/изображения)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ⚠️ ВАЖНО: Starlette применяет middleware в обратном порядке.
    # Поэтому Guard добавляем ПЕРВЫМ, а UserID — ПОСЛЕДНИМ,
    # чтобы UserID отработал раньше Guard.
    app.add_middleware(RegistrationGuardMiddleware)
    app.add_middleware(UserIDMiddleware)

    # Роутеры
    app.include_router(pages_public.router)
    app.include_router(pages_user.router)
    app.include_router(pages_service_center.router)
    app.include_router(pages_admin.router)

    return app


app = create_app()
