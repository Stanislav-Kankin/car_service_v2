from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings
from .safe_migrations import apply_safe_migrations


engine = create_async_engine(
    settings.DB_URL,
    echo=settings.DEBUG,
    future=True,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """
    Инициализация БД:
    1) create_all() — создаёт таблицы, если их нет
    2) apply_safe_migrations() — добавляет недостающие колонки (безопасно, идемпотентно)
    """
    # важно импортнуть модели, чтобы Base.metadata знала про все таблицы
    from .. import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Совместимость: в проекте могла оказаться версия apply_safe_migrations()
        # либо с сигнатурой (conn), либо (conn, db_type).
        try:
            await apply_safe_migrations(conn, settings.DB_TYPE)
        except TypeError:
            # fallback для старой сигнатуры
            await apply_safe_migrations(conn)
