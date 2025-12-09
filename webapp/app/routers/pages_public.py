from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..dependencies import get_templates

router = APIRouter(tags=["public"])

templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Главная публичная страница: приветствие / дашборд.
    """
    return templates.TemplateResponse(
        "public/index.html",
        {"request": request},
    )
