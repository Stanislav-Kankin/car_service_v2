import logging
from typing import Set

from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


# ------------------------------
# helpers
# ------------------------------

def _norm_db_type(db_type: str | None) -> str:
    return (db_type or "").strip().lower()


def _is_postgres(db_type: str | None) -> bool:
    s = _norm_db_type(db_type)
    return "postgres" in s


async def _sqlite_get_columns(conn: AsyncConnection, table: str) -> Set[str]:
    res = await conn.exec_driver_sql(f"PRAGMA table_info({table});")
    rows = res.fetchall()
    return {r[1] for r in rows}


async def _sqlite_add_column(conn: AsyncConnection, table: str, column: str, ddl_type: str) -> None:
    await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type};")


# ------------------------------
# Postgres migrations
# ------------------------------

async def _apply_postgres(conn: AsyncConnection) -> None:
    stmts: list[str] = [
        # offers
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_text TEXT;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS cashback_percent INTEGER;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS cashback_amount INTEGER;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_num INTEGER;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS is_cashback_applied BOOLEAN DEFAULT FALSE;",

        # requests
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS reject_reason TEXT;",

        # cars (new engine fields)
        "ALTER TABLE cars ADD COLUMN IF NOT EXISTS engine_type VARCHAR(64);",
        "ALTER TABLE cars ADD COLUMN IF NOT EXISTS engine_volume_l DOUBLE PRECISION;",
        "ALTER TABLE cars ADD COLUMN IF NOT EXISTS engine_power_kw INTEGER;",

        # service_centers
        "ALTER TABLE service_centers ADD COLUMN IF NOT EXISTS segment VARCHAR(32) DEFAULT 'unspecified';",
        "UPDATE service_centers SET segment='unspecified' WHERE segment IS NULL;",
        # service_centers
        "ALTER TABLE service_centers ADD COLUMN IF NOT EXISTS segment VARCHAR(20) NOT NULL DEFAULT 'unspecified';",
        "UPDATE service_centers SET segment='unspecified' WHERE segment IS NULL OR segment='';",

    ]

    for stmt in stmts:
        try:
            await conn.exec_driver_sql(stmt)
        except Exception:
            # Идемпотентность: даже если IF NOT EXISTS не сработал/ошибка драйвера — не падаем на старте
            logger.exception("safe_migration failed (postgres): %s", stmt)


# ------------------------------
# SQLite migrations
# ------------------------------

async def _apply_sqlite(conn: AsyncConnection) -> None:
    # offers
    try:
        cols = await _sqlite_get_columns(conn, "offers")
        if "final_price_text" not in cols:
            await _sqlite_add_column(conn, "offers", "final_price_text", "TEXT")
        if "cashback_percent" not in cols:
            await _sqlite_add_column(conn, "offers", "cashback_percent", "INTEGER")
        if "cashback_amount" not in cols:
            await _sqlite_add_column(conn, "offers", "cashback_amount", "INTEGER")
        if "final_price_num" not in cols:
            await _sqlite_add_column(conn, "offers", "final_price_num", "INTEGER")
        if "is_cashback_applied" not in cols:
            await _sqlite_add_column(conn, "offers", "is_cashback_applied", "BOOLEAN DEFAULT 0")
    except Exception:
        logger.exception("safe_migration failed (sqlite) on offers")

    # requests
    try:
        cols = await _sqlite_get_columns(conn, "requests")
        if "reject_reason" not in cols:
            await _sqlite_add_column(conn, "requests", "reject_reason", "TEXT")
    except Exception:
        logger.exception("safe_migration failed (sqlite) on requests")

    # cars
    try:
        cols = await _sqlite_get_columns(conn, "cars")
        if "engine_type" not in cols:
            await _sqlite_add_column(conn, "cars", "engine_type", "TEXT")
        if "engine_volume_l" not in cols:
            await _sqlite_add_column(conn, "cars", "engine_volume_l", "REAL")
        if "engine_power_kw" not in cols:
            await _sqlite_add_column(conn, "cars", "engine_power_kw", "INTEGER")
    except Exception:
        logger.exception("safe_migration failed (sqlite) on cars")
    # service_centers
    try:
        cols = await _sqlite_get_columns(conn, "service_centers")
        if "segment" not in cols:
            await _sqlite_add_column(conn, "service_centers", "segment", "TEXT")
            # на всякий — проставим дефолт всем существующим
            await conn.execute(
                "UPDATE service_centers SET segment='unspecified' WHERE segment IS NULL OR segment='';"
            )
    except Exception:
        logger.exception("safe_migration failed (sqlite) on service_centers")


async def apply_safe_migrations(conn: AsyncConnection, db_type: str | None = None) -> None:
    """
    Безопасные миграции без Alembic.

    ВАЖНО:
    - только ADD COLUMN (ничего не удаляем)
    - можно запускать на каждом старте (идемпотентно)
    - совместимо со старым вызовом apply_safe_migrations(conn)
    """
    if _is_postgres(db_type):
        await _apply_postgres(conn)
    else:
        await _apply_sqlite(conn)
