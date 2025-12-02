from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ВАЖНО: относительные импорты, т.к. мы внутри пакета backend.app
from .api.v1 import (
    users,
    service_centers,
    cars,
    requests,
    offers,
    bonus,
)

app = FastAPI(title="CarBot V2 API")

# CORS можно потом сузить, сейчас оставляем максимально свободным для dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Регистрируем роутеры
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(
    service_centers.router,
    prefix="/api/v1/service-centers",
    tags=["service_centers"],
)
app.include_router(cars.router, prefix="/api/v1/cars", tags=["cars"])
app.include_router(requests.router, prefix="/api/v1/requests", tags=["requests"])
app.include_router(offers.router, prefix="/api/v1/offers", tags=["offers"])
app.include_router(bonus.router, prefix="/api/v1/bonus", tags=["bonus"])


@app.get("/health")
async def health():
    return {"status": "ok"}
