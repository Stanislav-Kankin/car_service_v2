from typing import Dict, List, Optional, Any

# Категории услуг при создании заявки + специализации СТО
SERVICE_CATEGORY_LABELS: Dict[str, str] = {
    # --- Заявка (клиент) ---
    "wash_combo": "Мойка, детейлинг, химчистка",
    "tire": "Шиномонтаж",
    "maint": "ТО/ обслуживание",

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

    # Агрегатный ремонт (заявка/СТО)
    "agg_turbo": "Турбина",
    "agg_starter": "Стартер",
    "agg_generator": "Генератор",
    "agg_steering": "Рулевая рейка",
    "agg_gearbox": "Коробка передач",
    "agg_fuel_system": "Топливная система",
    "agg_exhaust": "Выхлопная система",
    "agg_compressor": "Компрессор",
    "agg_driveshaft": "Карданный вал",
    "agg_motor": "Мотор",

    # --- Специализации СТО (отдельные) ---
    "wash": "Мойка",
    "detailing": "Детейлинг",
    "dry_cleaning": "Химчистка",
    "truck_tire": "Грузовой шиномонтаж",

    # Legacy/старые значения (для отображения старых заявок/СТО, если где-то остались)
    "sto": "СТО (общий ремонт)",
    "agg": "Агрегатный ремонт (общее)",
}


# Для логики подбора СТО под заявку: категория заявки -> какие специализации подходят
CATEGORY_TO_SPECIALIZATIONS: Dict[str, List[str]] = {
    # Клиентская заявка
    "wash_combo": ["wash", "detailing", "dry_cleaning"],
    "tire": ["tire"],
    "maint": ["maint"],

    # Помощь на дороге
    "road_tow": ["road_tow"],
    "road_fuel": ["road_fuel"],
    "road_unlock": ["road_unlock"],
    "road_jump": ["road_jump"],
    "road_mobile_tire": ["road_mobile_tire"],
    "road_mobile_master": ["road_mobile_master"],

    # СТО / общий ремонт
    "diag": ["diag"],
    "electric": ["electric"],
    "engine_fuel": ["engine_fuel"],
    "mechanic": ["mechanic"],
    "body_work": ["body_work"],
    "welding": ["welding"],
    "argon_welding": ["argon_welding"],
    "auto_glass": ["auto_glass"],
    "ac_climate": ["ac_climate"],
    "exhaust": ["exhaust"],
    "alignment": ["alignment"],

    # Агрегатный ремонт
    "agg_turbo": ["agg_turbo"],
    "agg_starter": ["agg_starter"],
    "agg_generator": ["agg_generator"],
    "agg_steering": ["agg_steering"],
    "agg_gearbox": ["agg_gearbox"],
    "agg_fuel_system": ["agg_fuel_system"],
    "agg_exhaust": ["exhaust"],
    "agg_compressor": ["agg_compressor"],
    "agg_driveshaft": ["agg_driveshaft"],
    "agg_motor": ["agg_motor"],

    # Legacy
    "sto": ["diag", "electric", "engine_fuel", "mechanic", "body_work"],
    "agg": ["agg_turbo", "agg_starter", "agg_generator", "agg_steering", "agg_gearbox"],
}


# --------------------------------------------------------------------
# Группы категорий (для UI)
# --------------------------------------------------------------------

# Группы для создания ЗАЯВКИ (клиент)
REQUEST_CATEGORY_GROUPS: List[tuple[str, List[str]]] = [
    ("Мойка / детейлинг / химчистка", ["wash_combo"]),
    ("Шиномонтаж", ["tire"]),
    ("ТО/ обслуживание", ["maint"]),
    (
        "Помощь на дороге",
        ["road_tow", "road_fuel", "road_unlock", "road_jump", "road_mobile_tire", "road_mobile_master"],
    ),
    (
        "СТО / общий ремонт",
        [
            "diag",
            "electric",
            "engine_fuel",
            "mechanic",
            "body_work",
            "welding",
            "argon_welding",
            "auto_glass",
            "ac_climate",
            "exhaust",
            "alignment",
        ],
    ),
    (
        "Агрегатный ремонт",
        [
            "agg_turbo",
            "agg_starter",
            "agg_generator",
            "agg_steering",
            "agg_gearbox",
            "agg_fuel_system",
            "agg_exhaust",
            "agg_compressor",
            "agg_driveshaft",
            "agg_motor",
        ],
    ),
]


# Плоский список специализаций СТО (для чекбоксов в WebApp)
SERVICE_CENTER_SPECIALIZATION_OPTIONS: List[tuple[str, str]] = [
    ("wash", SERVICE_CATEGORY_LABELS.get("wash", "Мойка")),
    ("detailing", SERVICE_CATEGORY_LABELS.get("detailing", "Детейлинг")),
    ("dry_cleaning", SERVICE_CATEGORY_LABELS.get("dry_cleaning", "Химчистка")),
    ("maint", SERVICE_CATEGORY_LABELS.get("maint", "ТО/ обслуживание")),
    ("diag", SERVICE_CATEGORY_LABELS.get("diag", "Диагностика")),
    ("electric", SERVICE_CATEGORY_LABELS.get("electric", "Автоэлектрик")),
    ("engine_fuel", SERVICE_CATEGORY_LABELS.get("engine_fuel", "Двигатель и топливная система")),
    ("mechanic", SERVICE_CATEGORY_LABELS.get("mechanic", "Слесарные работы")),
    ("body_work", SERVICE_CATEGORY_LABELS.get("body_work", "Кузовные работы")),
    ("welding", SERVICE_CATEGORY_LABELS.get("welding", "Сварочные работы")),
    ("argon_welding", SERVICE_CATEGORY_LABELS.get("argon_welding", "Аргонная сварка")),
    ("auto_glass", SERVICE_CATEGORY_LABELS.get("auto_glass", "Автостекло")),
    ("ac_climate", SERVICE_CATEGORY_LABELS.get("ac_climate", "Автокондиционер и системы климата")),
    ("exhaust", SERVICE_CATEGORY_LABELS.get("exhaust", "Выхлопная система")),
    ("alignment", SERVICE_CATEGORY_LABELS.get("alignment", "Развал-схождение")),
    ("tire", SERVICE_CATEGORY_LABELS.get("tire", "Шиномонтаж")),
    ("truck_tire", SERVICE_CATEGORY_LABELS.get("truck_tire", "Грузовой шиномонтаж")),
    # Агрегатный ремонт
    ("agg_turbo", SERVICE_CATEGORY_LABELS.get("agg_turbo", "Турбина")),
    ("agg_starter", SERVICE_CATEGORY_LABELS.get("agg_starter", "Стартер")),
    ("agg_generator", SERVICE_CATEGORY_LABELS.get("agg_generator", "Генератор")),
    ("agg_steering", SERVICE_CATEGORY_LABELS.get("agg_steering", "Рулевая рейка")),
    ("agg_gearbox", SERVICE_CATEGORY_LABELS.get("agg_gearbox", "Коробка передач")),
    ("agg_fuel_system", SERVICE_CATEGORY_LABELS.get("agg_fuel_system", "Топливная система")),
    ("agg_compressor", SERVICE_CATEGORY_LABELS.get("agg_compressor", "Компрессор")),
    ("agg_driveshaft", SERVICE_CATEGORY_LABELS.get("agg_driveshaft", "Карданный вал")),
    ("agg_motor", SERVICE_CATEGORY_LABELS.get("agg_motor", "Мотор")),
    # Помощь на дороге
    ("road_tow", SERVICE_CATEGORY_LABELS.get("road_tow", "Эвакуация")),
    ("road_fuel", SERVICE_CATEGORY_LABELS.get("road_fuel", "Топливо")),
    ("road_unlock", SERVICE_CATEGORY_LABELS.get("road_unlock", "Вскрытие автомобиля")),
    ("road_jump", SERVICE_CATEGORY_LABELS.get("road_jump", "Прикурить автомобиль")),
    ("road_mobile_tire", SERVICE_CATEGORY_LABELS.get("road_mobile_tire", "Выездной шиномонтаж")),
    ("road_mobile_master", SERVICE_CATEGORY_LABELS.get("road_mobile_master", "Выездной мастер")),
]


def get_request_category_groups() -> List[dict[str, Any]]:
    """
    Для шаблонов WebApp: [{"label": "...", "options": [(code, label), ...]}, ...]
    """
    groups: List[dict[str, Any]] = []
    for group_label, codes in REQUEST_CATEGORY_GROUPS:
        options: List[tuple[str, str]] = [
            (code, SERVICE_CATEGORY_LABELS.get(code, code)) for code in codes if code in SERVICE_CATEGORY_LABELS
        ]
        groups.append({"label": group_label, "options": options})
    return groups


def get_service_center_specialization_options() -> List[tuple[str, str]]:
    """Плоский список (code, label) в правильном порядке для чекбоксов."""
    return SERVICE_CENTER_SPECIALIZATION_OPTIONS


def get_service_category_label(code: str) -> str:
    return SERVICE_CATEGORY_LABELS.get(code, code)


def get_specializations_for_category(category_code: str) -> List[str]:
    return CATEGORY_TO_SPECIALIZATIONS.get(category_code, [])


def is_known_category(category_code: str) -> bool:
    return category_code in SERVICE_CATEGORY_LABELS


def is_known_specialization(spec_code: str) -> bool:
    return spec_code in SERVICE_CATEGORY_LABELS
