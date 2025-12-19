import logging
from typing import Iterable, Set

from sqlalchemy.ext.asyncio import AsyncConnection

from .config import settings

logger = logging.getLogger(__name__)


async def apply_safe_migrations(conn: AsyncConnection) -> None:
    """
    Безопасные миграции без Alembic.
    Цель: не ломать прод, добавлять только новые колонки, которые уже ожидает код.
    Запускать можно на каждом старте — команды идемпотентны.
    """
    db_type = (settings.DB_TYPE or "sqlite").lower()

    if db_type == "postgres":
        await _apply_postgres(conn)
    else:
        await _apply_sqlite(conn)


async def _apply_postgres(conn: AsyncConnection) -> None:
    stmts: list[str] = [
        # --- offers ---
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS price_text VARCHAR(100);",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS eta_text VARCHAR(100);",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS cashback_percent NUMERIC(5,2);",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();",

        # --- requests ---
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS final_price DOUBLE PRECISION;",
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS final_price_text VARCHAR(200);",
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS bonus_spent DOUBLE PRECISION NOT NULL DEFAULT 0;",
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS reject_reason TEXT;",
    ]

    for sql in stmts:
        try:
            await conn.exec_driver_sql(sql)
        except Exception:
            logger.exception("Safe migration failed (postgres): %s", sql)
            raise


async def _sqlite_get_columns(conn: AsyncConnection, table: str) -> Set[str]:
    res = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    rows = res.fetchall()
    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    return {r[1] for r in rows}


async def _sqlite_add_column(conn: AsyncConnection, table: str, column: str, ddl: str) -> None:
    sql = f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
    await conn.exec_driver_sql(sql)


async def _apply_sqlite(conn: AsyncConnection) -> None:
    # --- offers ---
    offers_cols = await _sqlite_get_columns(conn, "offers")

    if "price_text" not in offers_cols:
        await _sqlite_add_column(conn, "offers", "price_text", "VARCHAR(100)")
    if "eta_text" not in offers_cols:
        await _sqlite_add_column(conn, "offers", "eta_text", "VARCHAR(100)")
    if "cashback_percent" not in offers_cols:
        await _sqlite_add_column(conn, "offers", "cashback_percent", "NUMERIC(5,2)")
    if "updated_at" not in offers_cols:
        # важно: NOT NULL требует DEFAULT для существующих строк
        await _sqlite_add_column(
            conn,
            "offers",
            "updated_at",
            "DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP)",
        )

    # --- requests ---
    req_cols = await _sqlite_get_columns(conn, "requests")

    if "final_price" not in req_cols:
        await _sqlite_add_column(conn, "requests", "final_price", "REAL")
    if "final_price_text" not in req_cols:
        await _sqlite_add_column(conn, "requests", "final_price_text", "VARCHAR(200)")
    if "bonus_spent" not in req_cols:
        await _sqlite_add_column(conn, "requests", "bonus_spent", "REAL NOT NULL DEFAULT 0")
    if "reject_reason" not in req_cols:
        await _sqlite_add_column(conn, "requests", "reject_reason", "TEXT")
