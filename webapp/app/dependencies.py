from pathlib import Path

from fastapi.templating import Jinja2Templates

from .config import settings

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"


def get_settings():
    """
    Общий доступ к settings, если понадобится как dependency.
    """
    return settings


def get_templates() -> Jinja2Templates:
    """
    Инициализация Jinja2Templates.

    Используем одну и ту же директорию для всех роутов.
    """
    return Jinja2Templates(directory=str(TEMPLATES_DIR))
