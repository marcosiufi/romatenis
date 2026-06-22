from sqlalchemy import Enum as _SAEnum
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


def pg_enum(cls, **kw):
    """Enum que armazena o VALUE do enum Python (não o name) no PostgreSQL."""
    return _SAEnum(cls, values_callable=lambda obj: [e.value for e in obj], **kw)

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
