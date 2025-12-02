from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

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
    Простая инициализация БД для dev:
    создаём таблицы по всем моделям.

    В проде потом можно будет заменить на Alembic.
    """
    # важно импортнуть модели, чтобы Base.metadata знала про все таблицы
    from .. import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
