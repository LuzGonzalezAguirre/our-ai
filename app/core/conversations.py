from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Conversation, Message


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
    ) -> list[dict[str, str]]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at, Message.id)
            )

            return [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in result.scalars().all()
            ]

    async def append_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        async with SessionLocal() as session:
            async with session.begin():
                conversation = await session.get(
                    Conversation,
                    conversation_id,
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
        limit: int = 100,
    ) -> list[Conversation]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Conversation)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

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
