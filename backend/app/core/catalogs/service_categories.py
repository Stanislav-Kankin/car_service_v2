from __future__ import annotations

from typing import Dict, List, Optional

#
# ВАЖНО:
# - В БД (requests.service_category / service_centers.specializations) хранятся строковые коды.
# - Старые коды НЕ удаляем (могут быть в данных), только добавляем новые.
# - UI может показывать группировку, но хранение/фильтрация — по коду.
#

SERVICE_CATEGORY_LABELS: Dict[str, str] = {
    # --- Новые категории заявки (клиент) ---
    "wash_combo": "Мойка, детейлинг, химчистка",
    "tire": "Шиномонтаж",
    "maint": "ТО / обслуживание",

    # Помощь на дороге
    "road_tow": "Эвакуация",
    "road_fuel": "Топливо",
    "road_unlock": "Вскрытие автомобиля",
    "road_jump": "Прикурить автомобиль",
    "road_mobile_tire": "Выездной шиномонтаж",
    "road_mobile_master": "Выездной мастер",

    # СТО / общий ремонт
    "diag": "Диагностика",
    "electric": "Автоэлектрик",
    "engine_fuel": "Двигатель и топливная система",
    "mechanic": "Слесарные работы",
    "body_work": "Кузовные работы",
    "welding": "Сварочные работы",
    "argon_welding": "Аргонная сварка",
    "auto_glass": "Автостекло",
    "ac_climate": "Автокондиционер и системы климата",
    "exhaust": "Выхлопная система",
    "alignment": "Развал-схождение",

    # Агрегатный ремонт
    "agg_turbo": "Турбина",
    "agg_starter": "Стартер",
    "agg_generator": "Генератор",
    "agg_steering": "Рулевая рейка",
    "agg_gearbox": "Коробка передач",
    "agg_fuel_system": "Топливная система",
    "agg_compressor": "Компрессор",
    "agg_driveshaft": "Карданный вал",
    "agg_motor": "Мотор",

    # --- Новые специализации СТО (добавлены заказчиком) ---
    "wash": "Мойка",
    "detailing": "Детейлинг",
    "dry_cleaning": "Химчистка",
    "truck_tire": "Грузовой шиномонтаж",

    # --- Legacy (старые значения, могли попасть в БД) ---
    "sto": "СТО / общий ремонт",
    "paint": "Кузовные работы",
    "body": "Кузовные работы",
    "mech": "Слесарные работы",
    "elec": "Автоэлектрик",
    "agg": "Агрегатный ремонт",
}


# Маппинг: категория заявки (request.service_category) -> какие специализации СТО подходят
# ВАЖНО: тут мы не ломаем старые коды, просто расширяем.
CATEGORY_TO_SPECIALIZATIONS: Dict[str, List[str]] = {
    # основное
    "wash_combo": ["wash", "detailing", "dry_cleaning"],
    "tire": ["tire", "truck_tire"],
    "maint": ["maint"],

    # помощь на дороге
    "road_tow": ["road_tow"],
    "road_fuel": ["road_fuel"],
    "road_unlock": ["road_unlock"],
    "road_jump": ["road_jump"],
    "road_mobile_tire": ["road_mobile_tire"],
    "road_mobile_master": ["road_mobile_master"],

    # СТО / общий ремонт
    "diag": ["diag"],
    "electric": ["electric", "elec"],  # legacy elec
    "engine_fuel": ["engine_fuel"],
    "mechanic": ["mechanic", "mech"],  # legacy mech
    "body_work": ["body_work", "paint", "body"],  # legacy
    "welding": ["welding"],
    "argon_welding": ["argon_welding"],
    "auto_glass": ["auto_glass"],
    "ac_climate": ["ac_climate"],
    "exhaust": ["exhaust"],
    "alignment": ["alignment"],

    # агрегаты
    "agg_turbo": ["agg_turbo"],
    "agg_starter": ["agg_starter"],
    "agg_generator": ["agg_generator"],
    "agg_steering": ["agg_steering"],
    "agg_gearbox": ["agg_gearbox"],
    "agg_fuel_system": ["agg_fuel_system"],
    "agg_compressor": ["agg_compressor"],
    "agg_driveshaft": ["agg_driveshaft"],
    "agg_motor": ["agg_motor"],

    # legacy broad categories
    "sto": ["sto", "mechanic", "mech", "electric", "elec", "body_work", "paint", "body", "diag"],
    "wash": ["wash"],
    "detailing": ["detailing"],
    "dry_cleaning": ["dry_cleaning"],
    "truck_tire": ["truck_tire"],
    "paint": ["paint", "body_work", "body"],
    "body": ["body", "body_work", "paint"],
    "mech": ["mech", "mechanic"],
    "elec": ["elec", "electric"],
    "agg": [
        "agg_turbo",
        "agg_starter",
        "agg_generator",
        "agg_steering",
        "agg_gearbox",
        "agg_fuel_system",
        "agg_compressor",
        "agg_driveshaft",
        "agg_motor",
    ],
}


def get_service_category_label(code: Optional[str]) -> str:
    code = (code or "").strip()
    if not code:
        return "Услуга"
    return SERVICE_CATEGORY_LABELS.get(code, code)


def get_specializations_for_category(service_category_code: Optional[str]) -> List[str]:
    code = (service_category_code or "").strip()
    if not code:
        return []
    return CATEGORY_TO_SPECIALIZATIONS.get(code, [code])
