from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..dependencies import get_templates

router = APIRouter(
    prefix="/me",
    tags=["user"],
)

templates = get_templates()


@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request):
    """
    Личный кабинет клиента (пока заглушка).
    Здесь позже будет гараж, карусель авто и список заявок.
    """
    return templates.TemplateResponse(
        "user/dashboard.html",
        {"request": request},
    )
