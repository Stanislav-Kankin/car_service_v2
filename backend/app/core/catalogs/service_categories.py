
from __future__ import annotations

from typing import Dict, List, Optional

# Читабельные названия категорий заявок
SERVICE_CATEGORY_LABELS: Dict[str, str] = {
    "sto": "СТО / общий ремонт",
    "wash": "Автомойка",
    "tire": "Шиномонтаж",
    "electric": "Автоэлектрик",
    "mechanic": "Слесарные работы",
    "paint": "Малярные / кузовные работы",
    "maint": "ТО / обслуживание",
    "agg_turbo": "Ремонт турбин",
    "agg_starter": "Ремонт стартеров",
    "agg_generator": "Ремонт генераторов",
    "agg_steering": "Рулевые рейки",
    # Легаси-алиасы (если они всплывут в старых данных)
    "mech": "Слесарные работы",
    "elec": "Автоэлектрик",
    "body": "Малярные / кузовные работы",
    "diag": "Диагностика",
    "agg": "Ремонт агрегатов",
}

# Маппинг: код категории заявки -> коды специализаций СТО
# максимально повторяет CATEGORY_TO_SPECIALIZATIONS из бота.
CATEGORY_TO_SPECIALIZATIONS: Dict[str, List[str]] = {
    # 1:1 категории
    "wash": ["wash"],
    "tire": ["tire"],
    "electric": ["electric"],
    "mechanic": ["mechanic"],
    "paint": ["paint"],
    "maint": ["maint"],

    # Агрегаты по отдельности
    "agg_turbo": ["agg_turbo"],
    "agg_starter": ["agg_starter"],
    "agg_generator": ["agg_generator"],
    "agg_steering": ["agg_steering"],

    # Легаси-алиасы
    "mech": ["mechanic"],
    "elec": ["electric"],
    "body": ["paint"],
    "diag": ["electric", "mechanic", "maint"],
    "agg": ["agg_turbo", "agg_starter", "agg_generator", "agg_steering"],
    # Для "sto" спецов нет — не режем по специализациям
    "sto": [],
}


def get_specializations_for_category(category_code: Optional[str]) -> Optional[List[str]]:
    """
    Возвращает список кодов специализаций для категории заявки.

    Возвращает:
    - []        -> категорию знаем, но специально НЕ режем по спецам (например, 'sto')
    - список    -> конкретные коды спецов, по которым надо фильтровать
    - None      -> категории нет в словаре, можно пробовать 1:1 или не фильтровать
    """
    if not category_code:
        return None

    if category_code in CATEGORY_TO_SPECIALIZATIONS:
        return CATEGORY_TO_SPECIALIZATIONS[category_code][:]  # копия на всякий случай

    return None
