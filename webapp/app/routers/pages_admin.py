import os

from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from httpx import AsyncClient

from ..dependencies import get_templates
from ..api_client import get_backend_client
from ..config import settings

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

templates = get_templates()


def _parse_admin_ids(raw: str | None) -> set[int]:
    """
    TELEGRAM_ADMIN_IDS может быть: "123" или "123,456" или "123 456"
    """
    if not raw:
        return set()
    parts = raw.replace(" ", ",").split(",")
    out: set[int] = set()
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except ValueError:
            continue
    return out


async def get_current_admin(request: Request, client: AsyncClient) -> dict[str, Any]:
    """
    Пользователь должен быть авторизован (cookie user_id).
    Дальше проверяем:
      - роль в backend = 'admin' (или 'superadmin')
      - ИЛИ его telegram_id входит в TELEGRAM_ADMIN_IDS (env)
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
    role = (user.get("role") or "").lower()
    telegram_id = user.get("telegram_id")

    admin_roles = {"admin", "superadmin"}

    # ✅ allowlist из настроек webapp (env)
    admin_ids = _parse_admin_ids(settings.TELEGRAM_ADMIN_IDS)

    is_admin = (role in admin_roles) or (isinstance(telegram_id, int) and telegram_id in admin_ids)

    if not is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав (нужен админ)")

    # best-effort: если прошёл по TELEGRAM_ADMIN_IDS, но роли admin нет — можем поднять роль
    if role not in admin_roles and isinstance(telegram_id, int) and telegram_id in admin_ids:
        try:
            await client.patch(f"/api/v1/users/{int(user_id)}", json={"role": "admin"})
        except Exception:
            pass

    return user


# ---------------------------------------------------------------------------
# ADMIN DASHBOARD
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
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
    Список всех СТО (для админа): активные и неактивные.

    ВАЖНО:
    - Не используем больше /api/v1/service-centers/all.
    - Дёргаем /api/v1/service-centers/ (со слешем) дважды:
      is_active=True и is_active=False.
    """
    _ = await get_current_admin(request, client)

    service_centers: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        # Активные СТО
        resp_active = await client.get(
            "/api/v1/service-centers/",   # <--- ВАЖНО: со слешем
            params={"is_active": True},
            follow_redirects=True,
        )
        resp_active.raise_for_status()
        active_list = resp_active.json()

        # Неактивные СТО
        resp_inactive = await client.get(
            "/api/v1/service-centers/",   # <--- ВАЖНО: со слешем
            params={"is_active": False},
            follow_redirects=True,
        )
        resp_inactive.raise_for_status()
        inactive_list = resp_inactive.json()

        combined = list(active_list) + list(inactive_list)

        # Пытаемся отсортировать по created_at (если есть)
        try:
            combined.sort(
                key=lambda sc: sc.get("created_at") or "",
                reverse=True,
            )
        except Exception:
            # Если с датой что-то не так — просто оставляем порядок как есть.
            pass

        service_centers = combined

    except Exception as e:
        print(
            "ERROR loading service-centers for admin (via /service-centers/):",
            repr(e),
        )
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
# Переключение активности СТО (модерация)
# ---------------------------------------------------------------------------

@router.post("/service-centers/{sc_id}/toggle", response_class=HTMLResponse)
async def admin_service_center_toggle(
    sc_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    action: str = Form(...),  # "activate" или "deactivate"
) -> HTMLResponse:
    """
    Активировать или деактивировать СТО.

    Использует PATCH /api/v1/service-centers/{id} с полем is_active.

    ДОПОЛНИТЕЛЬНО (важно для модерации):
    - при активации СТО best-effort поднимаем роль владельца до service_owner,
      чтобы у него появилось меню/кабинет СТО.
    """
    _ = await get_current_admin(request, client)

    is_active = True if action == "activate" else False

    # ✅ НОВОЕ: если активируем — поднимаем роль владельцу (best-effort)
    if is_active:
        try:
            resp_sc = await client.get(f"/api/v1/service-centers/{sc_id}")
            if resp_sc.status_code == status.HTTP_200_OK:
                sc_obj = resp_sc.json()
                owner_id = sc_obj.get("user_id")
                if owner_id:
                    await client.patch(
                        f"/api/v1/users/{int(owner_id)}",
                        json={"role": "service_owner"},
                    )
        except Exception as e:
            # Не валим модерацию из-за роли — это best-effort.
            print("WARN: cannot promote owner role:", sc_id, repr(e))

    try:
        resp = await client.patch(
            f"/api/v1/service-centers/{sc_id}",
            json={"is_active": is_active},
        )
        resp.raise_for_status()
    except Exception as e:
        print("ERROR toggling service-center:", sc_id, repr(e))
        # Пока просто игнорируем, UI всё равно перерисуем

    return await admin_service_centers(request, client)


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


@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Список пользователей для админа с фильтрами по дате/ID/Telegram ID.
    """
    _ = await get_current_admin(request, client)

    # Читаем фильтры из query-параметров
    qp = request.query_params
    date_from = qp.get("date_from") or None
    date_to = qp.get("date_to") or None
    user_id = qp.get("user_id") or None
    telegram_id = qp.get("telegram_id") or None

    params: dict[str, Any] = {}

    if date_from:
        params["registered_from"] = date_from
    if date_to:
        params["registered_to"] = date_to
    if user_id:
        try:
            params["user_id"] = int(user_id)
        except ValueError:
            pass
    if telegram_id:
        try:
            params["telegram_id"] = int(telegram_id)
        except ValueError:
            pass

    users: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get(
            "/api/v1/users/",
            params=params,
            follow_redirects=True,
        )
        resp.raise_for_status()
        users = resp.json()
    except Exception as e:
        print("ERROR loading users for admin:", repr(e))
        error_message = "Не удалось загрузить список пользователей."

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": users,
            "error_message": error_message,
            "filters": {
                "date_from": date_from or "",
                "date_to": date_to or "",
                "user_id": user_id or "",
                "telegram_id": telegram_id or "",
            },
        },
    )
