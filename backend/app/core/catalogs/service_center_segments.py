from __future__ import annotations

from typing import Iterable


# ВАЖНО: значения (keys) — стабильные коды, их можно хранить в БД.
# Лейблы — человекочитаемые для UI.
SERVICE_CENTER_SEGMENTS: list[tuple[str, str]] = [
    ("unspecified", "Не указано"),
    ("prem_plus", "Прем+"),
    ("official", "Официальный"),
    ("multibrand", "Мультибренд"),
    ("club", "Клубный"),
    ("specialized", "Специализированный"),
]


def get_service_center_segment_options() -> Iterable[tuple[str, str]]:
    return SERVICE_CENTER_SEGMENTS


def get_service_center_segment_label(code: str | None) -> str:
    code = (code or "").strip()
    for k, v in SERVICE_CENTER_SEGMENTS:
        if k == code:
            return v
    return "Не указано"
