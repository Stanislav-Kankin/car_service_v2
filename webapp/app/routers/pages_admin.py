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


def get_current_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не авторизован",
        )
    return int(user_id)


async def get_current_admin(request: Request, client: AsyncClient) -> dict[str, Any]:
    """
    Админ определяется по allowlist в .env (TELEGRAM_ADMIN_IDS).
    """
    user_id = get_current_user_id(request)

    # Получаем user из backend
    try:
        resp = await client.get(f"/api/v1/users/{user_id}")
        resp.raise_for_status()
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")

    user = resp.json()

    # allowlist по telegram_id (TELEGRAM_ADMIN_IDS)
    admin_ids_raw = (os.getenv("TELEGRAM_ADMIN_IDS") or "").strip()
    admin_ids: set[int] = set()
    if admin_ids_raw:
        for part in admin_ids_raw.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                admin_ids.add(int(part))
            except ValueError:
                continue

    telegram_id = user.get("telegram_id")
    if not telegram_id or int(telegram_id) not in admin_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа (не админ)")

    # (опционально) прокидываем роль admin в backend, если вдруг не стоит
    if user.get("role") != "admin":
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
            pass

        service_centers = combined

        # --- Wallet balances (best-effort) ---
        # Чтобы не ломать страницу даже если wallet-ручки временно недоступны.
        try:
            import asyncio

            async def _load_balance(sc: dict[str, Any]) -> None:
                sc_id = sc.get("id")
                if not sc_id:
                    sc["wallet_balance"] = None
                    return
                try:
                    r = await client.get(f"/api/v1/service-centers/{int(sc_id)}/wallet")
                    if r.status_code < 400:
                        w = r.json()
                        sc["wallet_balance"] = w.get("balance")
                    else:
                        sc["wallet_balance"] = None
                except Exception:
                    sc["wallet_balance"] = None

            await asyncio.gather(*[_load_balance(sc) for sc in service_centers])
        except Exception:
            pass

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
    action: str = Form(...),
) -> HTMLResponse:
    _ = await get_current_admin(request, client)

    is_active = action == "activate"

    try:
        resp = await client.patch(
            f"/api/v1/service-centers/{sc_id}",
            json={"is_active": is_active},
        )
        resp.raise_for_status()
    except Exception as e:
        print("ERROR toggling service center:", sc_id, repr(e))

    return await admin_service_centers(request, client)


# ---------------------------------------------------------------------------
# Пополнение кошелька СТО (взнос/депозит)
# ---------------------------------------------------------------------------

@router.post("/service-centers/{sc_id}/wallet-credit", response_class=HTMLResponse)
async def admin_service_center_wallet_credit(
    sc_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    amount: int = Form(...),
    description: str = Form(""),
) -> HTMLResponse:
    _ = await get_current_admin(request, client)

    try:
        payload = {
            "amount": int(amount),
            "description": (description or "").strip() or None,
            "tx_type": "admin_credit",
        }
        resp = await client.post(
            f"/api/v1/service-centers/{sc_id}/wallet/credit",
            json=payload,
        )
        resp.raise_for_status()
    except Exception as e:
        print("ERROR wallet-credit:", sc_id, repr(e))
        # Мягко игнорируем: просто вернём пользователя обратно в список
        # (если хочешь вывод красивого сообщения — сделаем позже "flash").
        pass

    return await admin_service_centers(request, client)


# ---------------------------------------------------------------------------
# ПОИСК ПОЛЬЗОВАТЕЛЯ ПО ID
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    _ = await get_current_admin(request, client)

    users: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get("/api/v1/users/")
        resp.raise_for_status()
        users = resp.json()
    except Exception as e:
        print("ERROR loading users:", repr(e))
        error_message = "Не удалось загрузить список пользователей."
        users = []

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": users,
            "error_message": error_message,
        },
    )
