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

        await connection.execute(
            text(
                """
                INSERT INTO ai_projects (
                    id,
                    name,
                    description,
                    created_at,
                    updated_at
                )
                VALUES (
                    :project_id,
                    'General',
                    'Proyecto general creado automáticamente.',
                    NOW(),
                    NOW()
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "project_id": settings.default_project_id,
            },
        )

        await connection.execute(
            text(
                """
                INSERT INTO ai_conversation_projects (
                    conversation_id,
                    project_id
                )
                SELECT
                    conversations.id,
                    :project_id
                FROM ai_conversations AS conversations
                LEFT JOIN ai_conversation_projects AS mapping
                    ON mapping.conversation_id = conversations.id
                WHERE mapping.conversation_id IS NULL
                """
            ),
            {
                "project_id": settings.default_project_id,
            },
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
