from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings
from .safe_migrations import apply_safe_migrations

logger = logging.getLogger(__name__)

Base = declarative_base()

engine = create_async_engine(
    settings.DB_URL,
    echo=getattr(settings, "DEBUG", False),
    future=True,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """
    Инициализация БД:
    1) create_all() — создаёт таблицы, если их нет
    2) safe_migrations — добавляет недостающие колонки (безопасно, идемпотентно)
    """
    # важно импортнуть модели, чтобы Base.metadata знала про все таблицы
    from .. import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # ✅ совместимость: safe_migrations принимает db_type опционально,
        # но передадим явно — так читаемее.
        try:
            await apply_safe_migrations(conn, getattr(settings, "DB_TYPE", None))
        except TypeError:
            # на случай, если где-то осталась старая сигнатура
            await apply_safe_migrations(conn)  # type: ignore[misc]
