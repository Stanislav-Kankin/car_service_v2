import os
import logging
import logging.config
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import pages_public, pages_user, pages_referrals, pages_service_center, pages_admin
from .middleware import RegistrationGuardMiddleware, UserIDMiddleware


def setup_logging(service_name: str) -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "/app/logs")
    log_to_file = os.getenv("LOG_TO_FILE", "1").lower() in ("1", "true", "yes", "on")
    max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10 MB
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "10"))

    Path(log_dir).mkdir(parents=True, exist_ok=True)

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": log_level,
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    }

    root_handlers = ["console"]

    if log_to_file:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": log_level,
            "formatter": "default",
            "filename": str(Path(log_dir) / f"{service_name}.log"),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        handlers["file_error"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "default",
            "filename": str(Path(log_dir) / f"{service_name}.error.log"),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        root_handlers.extend(["file", "file_error"])

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": handlers,
            "root": {"level": log_level, "handlers": root_handlers},
            "loggers": {
                "uvicorn": {"level": log_level, "handlers": root_handlers, "propagate": False},
                "uvicorn.error": {"level": log_level, "handlers": root_handlers, "propagate": False},
                "uvicorn.access": {"level": log_level, "handlers": ["console"], "propagate": False},
            },
        }
    )


setup_logging("webapp")

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
    app.include_router(pages_referrals.router)
    app.include_router(pages_service_center.router)
    app.include_router(pages_admin.router)

    return app


app = create_app()
