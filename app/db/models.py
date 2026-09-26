from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "ai_messages"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "ai_conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    conversation: Mapped[Conversation] = relationship(
        back_populates="messages"
    )


class Project(Base):
    __tablename__ = "ai_projects"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(500),
        default="",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )


class ConversationProject(Base):
    __tablename__ = "ai_conversation_projects"

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "ai_conversations.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "ai_projects.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )


class KnowledgeSource(Base):
    __tablename__ = "ai_knowledge_sources"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "ai_projects.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(140),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )


class KnowledgeChunk(Base):
    __tablename__ = "ai_knowledge_chunks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "ai_knowledge_sources.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "ai_projects.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(
        JSON,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )


Index(
    "ix_ai_messages_conversation_created",
    Message.conversation_id,
    Message.created_at,
)

Index(
    "ix_ai_knowledge_project_source",
    KnowledgeChunk.project_id,
    KnowledgeChunk.source_id,
)
