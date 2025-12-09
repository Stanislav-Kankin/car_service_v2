from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from httpx import AsyncClient

from ..api_client import get_backend_client
from ..dependencies import get_templates

router = APIRouter(
    prefix="/me",
    tags=["user"],
)

templates = get_templates()


# TODO: когда появится нормальная авторизация в WebApp,
# брать текущего пользователя из сессии / куки / JWT.
# Пока для MVP используем "заглушку" user_id = 1.
FAKE_CURRENT_USER_ID = 1


@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request) -> HTMLResponse:
    """
    Личный кабинет клиента (пока простой экран).
    Дальше сюда можно добавить быстрые ссылки / статусы.
    """
    return templates.TemplateResponse(
        "user/dashboard.html",
        {
            "request": request,
        },
    )


@router.get("/garage", response_class=HTMLResponse)
async def user_garage(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Экран гаража:
    - тянем список машин текущего пользователя из backend
    - выводим их в виде горизонтальной карусели
    """
    user_id = FAKE_CURRENT_USER_ID

    cars: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get(f"/api/v1/cars/by-user/{user_id}")
        if resp.status_code == 404:
            # нет машин — это не ошибка, просто пустой гараж
            cars = []
        else:
            resp.raise_for_status()
            cars = resp.json()
    except Exception as exc:  # noqa: BLE001
        # На проде здесь можно логировать детальнее
        error_message = "Не удалось загрузить список автомобилей. Попробуйте позже."
        cars = []

    return templates.TemplateResponse(
        "user/garage.html",
        {
            "request": request,
            "cars": cars,
            "error_message": error_message,
        },
    )


@router.get("/cars/{car_id}", response_class=HTMLResponse)
async def car_detail(
    car_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Карточка конкретной машины.
    """
    try:
        resp = await client.get(f"/api/v1/cars/{car_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Автомобиль не найден",
            )
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ошибка при обращении к backend-сервису",
        ) from exc

    car = resp.json()

    return templates.TemplateResponse(
        "user/car_detail.html",
        {
            "request": request,
            "car": car,
        },
    )


@router.get("/requests/new", response_class=HTMLResponse)
async def request_create(
    request: Request,
    car_id: int | None = None,
) -> HTMLResponse:
    """
    Заглушка под создание новой заявки.
    Далее здесь появится полноценный мастер создания заявки (как в боте).
    """
    return templates.TemplateResponse(
        "user/request_create.html",
        {
            "request": request,
            "car_id": car_id,
        },
    )
