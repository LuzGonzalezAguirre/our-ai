from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_database() -> None:
    from app.db.models import Base

    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all
        )


async def check_database() -> tuple[bool, str | None]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, str(exc)


async def close_database() -> None:
    await engine.dispose()
