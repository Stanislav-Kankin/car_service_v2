from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.db import init_db
from backend.app.api.v1 import users

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


# Подключаем API v1
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])


@app.get("/health")
async def health():
    return {"status": "ok"}
