from typing import List, Optional
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import httpx

from backend.app.core.db import get_db
from backend.app.schemas.service_center import (
    ServiceCenterCreate,
    ServiceCenterRead,
    ServiceCenterUpdate,
)
from backend.app.schemas.service_center_wallet import (
    ServiceCenterWalletRead,
    ServiceCenterWalletCreditIn,
    ServiceCenterWalletTransactionRead,
)
from backend.app.services.service_centers_service import ServiceCentersService
from backend.app.services.service_center_wallet_service import ServiceCenterWalletService
from backend.app.services.requests_service import RequestsService
from backend.app.core.catalogs.service_categories import get_specializations_for_category
from backend.app.models.user import User

router = APIRouter(
    prefix="/service-centers",
    tags=["service_centers"],
)


# ----------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНОЕ: уведомление админам о новой СТО на модерации
# ----------------------------------------------------------------------

def _parse_admin_ids_from_env() -> list[int]:
    raw = (os.getenv("TELEGRAM_ADMIN_IDS") or "").strip()
    if not raw:
        return []
    parts = raw.replace(";", ",").split(",")
    ids: list[int] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        try:
            ids.append(int(p))
        except ValueError:
            continue
    return ids


def _admin_moderation_webapp_url() -> str:
    base = (os.getenv("WEBAPP_PUBLIC_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/admin/service-centers"


async def _notify_admins_new_service_center(sc: ServiceCenterRead) -> None:
    """
    Best-effort уведомление админов в Telegram через bot notify API.
    Контракт 1:1 как в bot/app/notify_api.py:
      POST {BOT_API_URL}/api/v1/notify
      payload: recipient_type, telegram_id, message, buttons[{text,type,url}]
      auth: Authorization: Bearer BOT_API_TOKEN
    """
    admin_ids = _parse_admin_ids_from_env()
    bot_api_url = (os.getenv("BOT_API_URL") or "").strip().rstrip("/")
    bot_api_token = (os.getenv("BOT_API_TOKEN") or "").strip()

    if not admin_ids:
        print("WARN notify_admins_new_sc: TELEGRAM_ADMIN_IDS is empty in BACKEND env")
        return
    if not bot_api_url:
        print("WARN notify_admins_new_sc: BOT_API_URL is empty in BACKEND env")
        return

    url = _admin_moderation_webapp_url()

    specs = sc.specializations or []
    if isinstance(specs, list) and specs:
        specs_text = ", ".join(str(x) for x in specs)
    else:
        specs_text = "—"

    msg = (
        "🛂 <b>Новая СТО на модерации</b>\n\n"
        f"ID: <b>{sc.id}</b>\n"
        f"Название: <b>{sc.name}</b>\n"
        f"Тип: <b>{sc.org_type or '—'}</b>\n"
        f"Телефон: <b>{sc.phone or '—'}</b>\n"
        f"Адрес: <b>{sc.address or '—'}</b>\n"
        f"Специализации: <b>{specs_text}</b>\n"
    )

    buttons = []
    if url:
        buttons = [{"text": "Открыть модерацию", "type": "url", "url": url}]

    # best-effort
    try:
        headers = {}
        if bot_api_token:
            headers["Authorization"] = f"Bearer {bot_api_token}"

        async with httpx.AsyncClient(timeout=10.0) as c:
            for admin_id in admin_ids:
                payload = {
                    "recipient_type": "user",
                    "telegram_id": admin_id,
                    "message": msg,
                    "buttons": buttons,
                }
                resp = await c.post(f"{bot_api_url}/api/v1/notify", json=payload, headers=headers)
                if resp.status_code >= 400:
                    print(
                        "WARN notify_admins_new_sc:",
                        admin_id,
                        resp.status_code,
                        resp.text[:200],
                    )
    except Exception as e:
        print("WARN notify_admins_new_sc exception:", repr(e))


# ----------------------------------------------------------------------
# Wallet СТО (баланс/пополнение)
# ----------------------------------------------------------------------

@router.get(
    "/{sc_id}/wallet",
    response_model=ServiceCenterWalletRead,
)
async def get_service_center_wallet(
    sc_id: int,
    db: AsyncSession = Depends(get_db),
):
    # wallet должен быть "всегда", но на всякий — создаём при первом запросе
    wallet = await ServiceCenterWalletService.get_or_create_wallet(db, sc_id)
    return wallet


@router.get(
    "/{sc_id}/wallet/transactions",
    response_model=List[ServiceCenterWalletTransactionRead],
)
async def list_service_center_wallet_transactions(
    sc_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    _ = await ServiceCenterWalletService.get_or_create_wallet(db, sc_id)
    txs = await ServiceCenterWalletService.list_transactions(db, sc_id, limit=limit)
    return txs


@router.post(
    "/{sc_id}/wallet/credit",
    response_model=ServiceCenterWalletRead,
    status_code=status.HTTP_201_CREATED,
)
async def credit_service_center_wallet(
    sc_id: int,
    data_in: ServiceCenterWalletCreditIn,
    db: AsyncSession = Depends(get_db),
):
    # ⚠️ ВАЖНО: сейчас в backend нет полноценной авторизации (как и у других ручек),
    # поэтому ограничение "только админ" реализуем на уровне webapp (allowlist).
    wallet, _tx = await ServiceCenterWalletService.credit_wallet(
        db=db,
        service_center_id=sc_id,
        amount=data_in.amount,
        tx_type=data_in.tx_type,
        description=data_in.description,
    )
    return wallet


# ----------------------------------------------------------------------
# Список / поиск СТО
# ----------------------------------------------------------------------

@router.get("/", response_model=List[ServiceCenterRead])
async def list_service_centers(
    db: AsyncSession = Depends(get_db),
    is_active: Optional[bool] = Query(default=None),
) -> List[ServiceCenterRead]:
    items = await ServiceCentersService.list_all(db, is_active=is_active)
    return [ServiceCenterRead.model_validate(x) for x in items]


@router.get("/{sc_id}", response_model=ServiceCenterRead)
async def get_service_center(
    sc_id: int,
    db: AsyncSession = Depends(get_db),
) -> ServiceCenterRead:
    sc = await ServiceCentersService.get_by_id(db, sc_id=sc_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Service center not found")
    return ServiceCenterRead.model_validate(sc)


@router.get("/by-user/{user_id}", response_model=List[ServiceCenterRead])
async def list_service_centers_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[ServiceCenterRead]:
    items = await ServiceCentersService.list_by_user_id(db, user_id=user_id)
    if not items:
        raise HTTPException(status_code=404, detail="No service centers for this user")
    return [ServiceCenterRead.model_validate(x) for x in items]


@router.post("/", response_model=ServiceCenterRead, status_code=status.HTTP_201_CREATED)
async def create_service_center(
    payload: ServiceCenterCreate,
    db: AsyncSession = Depends(get_db),
) -> ServiceCenterRead:
    # создаём СТО
    sc = await ServiceCentersService.create(db, payload)

    sc_out = ServiceCenterRead.model_validate(sc)

    # уведомляем админов (best-effort)
    await _notify_admins_new_service_center(sc_out)

    return sc_out


@router.patch("/{sc_id}", response_model=ServiceCenterRead)
async def update_service_center(
    sc_id: int,
    payload: ServiceCenterUpdate,
    db: AsyncSession = Depends(get_db),
) -> ServiceCenterRead:
    sc = await ServiceCentersService.update(db, sc_id=sc_id, payload=payload)
    if not sc:
        raise HTTPException(status_code=404, detail="Service center not found")
    return ServiceCenterRead.model_validate(sc)


@router.get("/{sc_id}/specializations", response_model=List[str])
async def get_service_center_specializations(
    sc_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    sc = await ServiceCentersService.get_by_id(db, sc_id=sc_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Service center not found")
    specs = sc.specializations or []
    if not isinstance(specs, list):
        return []
    return [str(x) for x in specs]


@router.get("/{sc_id}/supported-categories", response_model=List[str])
async def get_supported_categories(
    sc_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    sc = await ServiceCentersService.get_by_id(db, sc_id=sc_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Service center not found")
    specs = sc.specializations or []
    if not specs:
        return []
    categories = set()
    for spec in specs:
        categories.update(get_specializations_for_category(str(spec)))
    return sorted(list(categories))


@router.get("/{sc_id}/offers", response_model=List[dict])
async def list_offers_for_service_center(
    sc_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    offers = await RequestsService.list_offers_for_service_center(db, service_center_id=sc_id)
    return [o.to_dict() for o in offers]


@router.get("/{sc_id}/owner", response_model=dict)
async def get_service_center_owner(
    sc_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(User).join(User.service_centers).where(User.service_centers.any(id=sc_id))
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Owner not found")
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
    }
