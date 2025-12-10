from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from httpx import AsyncClient

from ..dependencies import get_templates
from ..api_client import get_backend_client

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

templates = get_templates()


async def get_current_admin(
    request: Request,
    client: AsyncClient,
) -> dict[str, Any]:
    """
    Проверяем, что пользователь авторизован и что у него роль 'admin'.

    ВАЖНО:
    Если в Enum UserRole значение для админа другое — поменяй строку 'admin'
    на актуальное.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Не авторизован")

    try:
        resp = await client.get(f"/api/v1/users/{int(user_id)}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Пользователь не найден")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Ошибка при загрузке профиля пользователя")

    user = resp.json()
    role = user.get("role")
    if role != "admin":
        # если Enum сериализуется иначе — изменишь это условие
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав (нужен админ)")

    return user


# ---------------------------------------------------------------------------
# ADMIN DASHBOARD
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Стартовая страница админки.
    """
    admin_user = await get_current_admin(request, client)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "admin_user": admin_user,
        },
    )


# ---------------------------------------------------------------------------
# СПИСОК СТО (все сервисы)
# ---------------------------------------------------------------------------

@router.get("/service-centers", response_class=HTMLResponse)
async def admin_service_centers(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Список всех СТО (по текущему API: /api/v1/service-centers).
    """
    _ = await get_current_admin(request, client)

    service_centers: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get("/api/v1/service-centers")
        resp.raise_for_status()
        service_centers = resp.json()
    except Exception:
        error_message = "Не удалось загрузить список СТО."
        service_centers = []

    return templates.TemplateResponse(
        "admin/service_centers.html",
        {
            "request": request,
            "service_centers": service_centers,
            "error_message": error_message,
        },
    )


# ---------------------------------------------------------------------------
# ПОИСК ПОЛЬЗОВАТЕЛЯ ПО ID
# ---------------------------------------------------------------------------

@router.get("/user-lookup", response_class=HTMLResponse)
async def admin_user_lookup_get(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Страница поиска пользователя по ID.
    """
    _ = await get_current_admin(request, client)

    return templates.TemplateResponse(
        "admin/user_lookup.html",
        {
            "request": request,
            "user_obj": None,
            "error_message": None,
        },
    )


@router.post("/user-lookup", response_class=HTMLResponse)
async def admin_user_lookup_post(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    user_id: int = Form(...),
) -> HTMLResponse:
    """
    Обработка формы поиска пользователя по ID.
    """
    _ = await get_current_admin(request, client)

    user_obj: dict[str, Any] | None = None
    error_message: str | None = None

    try:
        resp = await client.get(f"/api/v1/users/{user_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            error_message = "Пользователь с таким ID не найден."
        else:
            resp.raise_for_status()
            user_obj = resp.json()
    except Exception:
        error_message = "Ошибка при обращении к backend."

    return templates.TemplateResponse(
        "admin/user_lookup.html",
        {
            "request": request,
            "user_obj": user_obj,
            "error_message": error_message,
        },
    )
