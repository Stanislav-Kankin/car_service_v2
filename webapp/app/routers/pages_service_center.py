from typing import Any
import os

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from httpx import AsyncClient

from ..dependencies import get_templates
from ..api_client import get_backend_client

router = APIRouter(
    prefix="/sc",
    tags=["service_center"],
)

templates = get_templates()


BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")


def get_current_user_id(request: Request) -> int:
    """
    Берём user_id из request.state.user_id, который кладёт middleware.
    Все маршруты кабинета СТО требуют авторизации.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не авторизован",
        )
    return int(user_id)


# ---------------------------------------------------------------------------
# DASHBOARD СТО
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def sc_dashboard(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Кабинет СТО: список сервисов, привязанных к пользователю.
    """
    user_id = get_current_user_id(request)

    service_centers: list[dict[str, Any]] = []
    error_message: str | None = None

    try:
        resp = await client.get(f"/api/v1/service-centers/by-user/{user_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            service_centers = []
        else:
            resp.raise_for_status()
            service_centers = resp.json()

            # --- Wallet balances (best-effort) ---
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

    except Exception:
        error_message = "Не удалось загрузить список ваших СТО. Попробуйте позже."
        service_centers = []

    return templates.TemplateResponse(
        "service_center/dashboard.html",
        {
            "request": request,
            "service_centers": service_centers,
            "error_message": error_message,
        },
    )


# ---------------------------------------------------------------------------
# СОЗДАНИЕ НОВОГО СТО
# ---------------------------------------------------------------------------

@router.get("/create", response_class=HTMLResponse)
async def sc_create_get(
    request: Request,
) -> HTMLResponse:
    _ = get_current_user_id(request)

    # ✅ Единый список специализаций (код -> лейбл)
    # Подогнано под твой реальный список из бота (SERVICE_SPECIALIZATION_OPTIONS).
    # Если ты хочешь хранить это в backend — позже вынесем в /api/v1/dicts.
    specialization_options = [
        ("wash", "Автомойка"),
        ("tire", "Шиномонтаж"),
        ("electric", "Автоэлектрик"),
        ("mechanic", "Слесарные работы"),
        ("paint", "Кузовные/покраска"),
        ("maint", "ТО/обслуживание"),
        ("agg_turbo", "Турбины"),
        ("agg_starter", "Стартеры"),
        ("agg_generator", "Генераторы"),
        ("agg_steering", "Рулевые рейки"),
    ]

    return templates.TemplateResponse(
        "service_center/create.html",
        {
            "request": request,
            "error_message": None,
            "specialization_options": specialization_options,
        },
    )


@router.post("/create", response_class=HTMLResponse)
async def sc_create_post(
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    name: str = Form(...),
    address: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    org_type: str = Form("company"),
    is_mobile_service: bool = Form(False),
    has_tow_truck: bool = Form(False),
    # ✅ НОВОЕ: специализации приходят как multi-select/checkboxes (несколько значений)
    specializations: list[str] = Form(default_factory=list),
) -> HTMLResponse:
    user_id = get_current_user_id(request)

    # ✅ Валидация: минимум 1 специализация
    specializations = [s.strip() for s in (specializations or []) if s and s.strip()]
    if not specializations:
        specialization_options = [
            ("wash", "Автомойка"),
            ("tire", "Шиномонтаж"),
            ("electric", "Автоэлектрик"),
            ("mechanic", "Слесарные работы"),
            ("paint", "Кузовные/покраска"),
            ("maint", "ТО/обслуживание"),
            ("agg_turbo", "Турбины"),
            ("agg_starter", "Стартеры"),
            ("agg_generator", "Генераторы"),
            ("agg_steering", "Рулевые рейки"),
        ]
        return templates.TemplateResponse(
            "service_center/create.html",
            {
                "request": request,
                "error_message": "Выберите минимум одну специализацию.",
                "specialization_options": specialization_options,
            },
        )

    payload = {
        "user_id": user_id,
        "name": name,
        "address": address or None,
        "phone": phone or None,
        "website": website or None,
        "org_type": org_type or None,
        "is_mobile_service": bool(is_mobile_service),
        "has_tow_truck": bool(has_tow_truck),
        "specializations": specializations,
    }

    try:
        resp = await client.post("/api/v1/service-centers/", json=payload, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        specialization_options = [
            ("wash", "Автомойка"),
            ("tire", "Шиномонтаж"),
            ("electric", "Автоэлектрик"),
            ("mechanic", "Слесарные работы"),
            ("paint", "Кузовные/покраска"),
            ("maint", "ТО/обслуживание"),
            ("agg_turbo", "Турбины"),
            ("agg_starter", "Стартеры"),
            ("agg_generator", "Генераторы"),
            ("agg_steering", "Рулевые рейки"),
        ]
        return templates.TemplateResponse(
            "service_center/create.html",
            {
                "request": request,
                "error_message": "Не удалось создать СТО. Проверьте данные и попробуйте ещё раз.",
                "specialization_options": specialization_options,
            },
        )

    return RedirectResponse(
        url="/sc/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНОЕ: загрузить СТО и проверить принадлежность
# ---------------------------------------------------------------------------

async def _load_sc_for_owner(
    request: Request,
    client: AsyncClient,
    sc_id: int,
) -> dict[str, Any]:
    """
    Загрузить СТО и проверить, что он принадлежит текущему пользователю.
    """
    user_id = get_current_user_id(request)

    try:
        resp = await client.get(f"/api/v1/service-centers/{sc_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Сервис не найден")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Ошибка backend при загрузке СТО")

    sc = resp.json()
    if sc.get("user_id") != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому сервису")

    return sc


# ---------------------------------------------------------------------------
# ПРОСМОТР / РЕДАКТИРОВАНИЕ ПРОФИЛЯ СТО
# ---------------------------------------------------------------------------

@router.get("/edit/{sc_id}", response_class=HTMLResponse)
async def sc_edit_get(
    sc_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
) -> HTMLResponse:
    """
    Форма редактирования профиля СТО.
    """
    sc = await _load_sc_for_owner(request, client, sc_id)

    # ✅ список специализаций для UI (коды должны совпадать с backend)
    specialization_options = [
        ("wash", "Автомойка"),
        ("tire", "Шиномонтаж"),
        ("electric", "Автоэлектрик"),
        ("mechanic", "Слесарные работы"),
        ("paint", "Малярные / кузовные работы"),
        ("maint", "ТО / обслуживание"),
        ("agg_turbo", "Ремонт турбин"),
        ("agg_starter", "Ремонт стартеров"),
        ("agg_generator", "Ремонт генераторов"),
        ("agg_steering", "Рулевые рейки"),
    ]

    return templates.TemplateResponse(
        "service_center/edit.html",
        {
            "request": request,
            "service_center": sc,
            "error_message": None,
            "success": False,
            "specialization_options": specialization_options,
        },
    )


@router.post("/edit/{sc_id}", response_class=HTMLResponse)
async def sc_edit_post(
    sc_id: int,
    request: Request,
    client: AsyncClient = Depends(get_backend_client),
    name: str = Form(...),
    address: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    org_type: str = Form("company"),
    # ✅ НОВОЕ: список чекбоксов специализаций
    specializations: list[str] = Form([]),
    is_mobile_service: bool = Form(False),
    has_tow_truck: bool = Form(False),
    is_active: bool = Form(True),
) -> HTMLResponse:
    """
    Обработка формы редактирования СТО.
    """
    _ = get_current_user_id(request)

    # ✅ список специализаций для UI (чтобы при ошибке форма не "обнулялась")
    specialization_options = [
        ("wash", "Автомойка"),
        ("tire", "Шиномонтаж"),
        ("electric", "Автоэлектрик"),
        ("mechanic", "Слесарные работы"),
        ("paint", "Малярные / кузовные работы"),
        ("maint", "ТО / обслуживание"),
        ("agg_turbo", "Ремонт турбин"),
        ("agg_starter", "Ремонт стартеров"),
        ("agg_generator", "Ремонт генераторов"),
        ("agg_steering", "Рулевые рейки"),
    ]

    # ✅ валидация: минимум одна специализация
    specs_clean = [s for s in (specializations or []) if s]
    if not specs_clean:
        sc = await _load_sc_for_owner(request, client, sc_id)
        return templates.TemplateResponse(
            "service_center/edit.html",
            {
                "request": request,
                "service_center": sc,
                "error_message": "Выберите минимум одну специализацию.",
                "success": False,
                "specialization_options": specialization_options,
            },
        )

    payload: dict[str, Any] = {
        "name": name,
        "address": address or None,
        "phone": phone or None,
        "website": website or None,
        "org_type": org_type or None,
        "specializations": specs_clean,  # ✅ отправляем в backend
        "is_mobile_service": bool(is_mobile_service),
        "has_tow_truck": bool(has_tow_truck),
        "is_active": bool(is_active),
    }

    error_message: str | None = None
    sc: dict[str, Any] | None = None
    success = False

    try:
        resp = await client.patch(f"/api/v1/service-centers/{sc_id}", json=payload)
        resp.raise_for_status()
        sc = resp.json()
        success = True
    except Exception:
        error_message = "Не удалось сохранить изменения. Попробуйте позже."
        try:
            sc = await _load_sc_for_owner(request, client, sc_id)
        except HTTPException:
            raise

    return templates.TemplateResponse(
        "service_center/edit.html",
        {
            "request": request,
            "service_center": sc,
            "error_message": error_message,
            "success": success,
            "specialization_options": specialization_options,
        },
    )
