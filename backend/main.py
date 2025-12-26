import os
import logging
import logging.config
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.db import init_db
from backend.app.api.v1 import (
    users,
    service_centers,
    cars,
    requests,
    offers,
    bonus,
    auth,
    geo,
)


def setup_logging(service_name: str) -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "/app/logs")
    log_to_file = os.getenv("LOG_TO_FILE", "1").lower() in ("1", "true", "yes", "on")

    max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": log_level,
            "formatter": "default",
        }
    }

    root_handlers = ["console"]

    if log_to_file:
        Path(log_dir).mkdir(parents=True, exist_ok=True)

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
        }
    )


setup_logging("backend")

app = FastAPI(title="CarBot V2 API")


@app.on_event("startup")
async def on_startup():
    await init_db()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1
app.include_router(users.router, prefix="/api/v1")
app.include_router(service_centers.router, prefix="/api/v1")
app.include_router(cars.router, prefix="/api/v1")
app.include_router(requests.router, prefix="/api/v1")
app.include_router(offers.router, prefix="/api/v1")
app.include_router(bonus.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(geo.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
