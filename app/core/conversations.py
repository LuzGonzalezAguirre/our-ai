from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import (
    Conversation,
    ConversationProject,
    Message,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _conversation_title(message: str) -> str:
    compact = " ".join(message.strip().split())
    if not compact:
        return "Nueva conversación"

    if len(compact) <= 56:
        return compact

    return compact[:53].rstrip() + "..."


class ConversationStore:
    async def get_messages(
        self,
        conversation_id: str,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        async with SessionLocal() as session:
            statement = select(Message).where(
                Message.conversation_id == conversation_id
            )

            if limit:
                statement = (
                    statement
                    .order_by(
                        Message.created_at.desc(),
                        Message.id.desc(),
                    )
                    .limit(limit)
                )
                result = await session.execute(statement)
                records = list(result.scalars().all())
                records.reverse()
            else:
                statement = statement.order_by(
                    Message.created_at,
                    Message.id,
                )
                result = await session.execute(statement)
                records = list(result.scalars().all())

            return [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in records
            ]

    async def get_project_id(
        self,
        conversation_id: str,
    ) -> str | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ConversationProject.project_id).where(
                    ConversationProject.conversation_id
                    == conversation_id
                )
            )
            return result.scalar_one_or_none()

    async def append_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        project_id: str | None = None,
    ) -> None:
        project_id = (
            project_id
            or settings.default_project_id
        )

        async with SessionLocal() as session:
            async with session.begin():
                conversation = await session.get(
                    Conversation,
                    conversation_id,
                )

                mapping = await session.get(
                    ConversationProject,
                    conversation_id,
                )

                if (
                    mapping is not None
                    and mapping.project_id != project_id
                ):
                    raise ValueError(
                        "La conversación pertenece a otro proyecto."
                    )

                now = _utcnow()

                if conversation is None:
                    conversation = Conversation(
                        id=conversation_id,
                        title=_conversation_title(user_message),
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(conversation)
                else:
                    conversation.updated_at = now

                if mapping is None:
                    session.add(
                        ConversationProject(
                            conversation_id=conversation_id,
                            project_id=project_id,
                        )
                    )

                session.add_all(
                    [
                        Message(
                            conversation_id=conversation_id,
                            role="user",
                            content=user_message,
                            created_at=now,
                        ),
                        Message(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=assistant_message,
                            created_at=_utcnow(),
                        ),
                    ]
                )

    async def list_conversations(
        self,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[tuple[Conversation, str]]:
        async with SessionLocal() as session:
            statement = (
                select(
                    Conversation,
                    ConversationProject.project_id,
                )
                .join(
                    ConversationProject,
                    ConversationProject.conversation_id
                    == Conversation.id,
                )
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )

            if project_id:
                statement = statement.where(
                    ConversationProject.project_id == project_id
                )

            result = await session.execute(statement)
            return list(result.all())

    async def conversation_exists(
        self,
        conversation_id: str,
    ) -> bool:
        async with SessionLocal() as session:
            return (
                await session.get(Conversation, conversation_id)
            ) is not None

    async def get_message_records(
        self,
        conversation_id: str,
    ) -> list[Message]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at, Message.id)
            )
            return list(result.scalars().all())

    async def delete(
        self,
        conversation_id: str,
    ) -> bool:
        async with SessionLocal() as session:
            async with session.begin():
                conversation = await session.get(
                    Conversation,
                    conversation_id,
                )

                if conversation is None:
                    return False

                await session.execute(
                    delete(Conversation).where(
                        Conversation.id == conversation_id
                    )
                )
                return True


conversation_store = ConversationStore()
