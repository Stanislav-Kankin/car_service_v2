import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


async def _apply_postgres(conn: AsyncConnection) -> None:
    stmts: list[str] = [
        # --- offers ---
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_text TEXT;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS cashback_percent INTEGER;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS cashback_amount INTEGER;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_num INTEGER;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS is_cashback_applied BOOLEAN;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_confirmed BOOLEAN;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_confirmed_at TIMESTAMP;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_confirmed_by INTEGER;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_rejected_at TIMESTAMP;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_rejected_by INTEGER;",
        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS final_price_reject_reason TEXT;",

        # --- requests ---
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS reject_reason TEXT;",

        # --- cars (✅ новые поля карточки авто) ---
        "ALTER TABLE cars ADD COLUMN IF NOT EXISTS engine_type VARCHAR(20);",
        "ALTER TABLE cars ADD COLUMN IF NOT EXISTS engine_volume_l DOUBLE PRECISION;",
        "ALTER TABLE cars ADD COLUMN IF NOT EXISTS engine_power_kw INTEGER;",
    ]

    for stmt in stmts:
        try:
            await conn.execute(text(stmt))
        except Exception as e:
            # safe-migration: не валим приложение
            logger.warning("safe_migrations postgres skipped/failed: %s (%s)", stmt, e)


async def _apply_sqlite(conn: AsyncConnection) -> None:
    stmts: list[str] = [
        # --- offers ---
        "ALTER TABLE offers ADD COLUMN final_price_text TEXT;",
        "ALTER TABLE offers ADD COLUMN cashback_percent INTEGER;",
        "ALTER TABLE offers ADD COLUMN cashback_amount INTEGER;",
        "ALTER TABLE offers ADD COLUMN final_price_num INTEGER;",
        "ALTER TABLE offers ADD COLUMN is_cashback_applied BOOLEAN;",
        "ALTER TABLE offers ADD COLUMN final_price_confirmed BOOLEAN;",
        "ALTER TABLE offers ADD COLUMN final_price_confirmed_at DATETIME;",
        "ALTER TABLE offers ADD COLUMN final_price_confirmed_by INTEGER;",
        "ALTER TABLE offers ADD COLUMN final_price_rejected_at DATETIME;",
        "ALTER TABLE offers ADD COLUMN final_price_rejected_by INTEGER;",
        "ALTER TABLE offers ADD COLUMN final_price_reject_reason TEXT;",

        # --- requests ---
        "ALTER TABLE requests ADD COLUMN reject_reason TEXT;",

        # --- cars (✅ новые поля карточки авто) ---
        "ALTER TABLE cars ADD COLUMN engine_type TEXT;",
        "ALTER TABLE cars ADD COLUMN engine_volume_l REAL;",
        "ALTER TABLE cars ADD COLUMN engine_power_kw INTEGER;",
    ]

    for stmt in stmts:
        try:
            await conn.execute(text(stmt))
        except Exception:
            # SQLite: IF NOT EXISTS нет — игнорируем ошибку "duplicate column"
            continue


async def apply_safe_migrations(conn: AsyncConnection, db_type: str) -> None:
    if (db_type or "").lower().startswith("postgres"):
        await _apply_postgres(conn)
    else:
        await _apply_sqlite(conn)
