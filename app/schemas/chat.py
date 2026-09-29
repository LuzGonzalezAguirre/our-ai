from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        description="Mensaje enviado por el usuario",
    )

    conversation_id: str | None = Field(
        default=None,
        description=(
            "Identificador de la conversación. "
            "Si no se proporciona, se crea uno nuevo."
        ),
    )

    project_id: str | None = Field(
        default=None,
        description=(
            "Proyecto que contiene el conocimiento y las "
            "conversaciones de este chat."
        ),
    )


class ChatResponse(BaseModel):
    response: str
    model: str
    conversation_id: str
    project_id: str
    knowledge_chunks_used: int = 0
    action_tracker_used: bool = False


class ConversationSummary(BaseModel):
    id: str
    title: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
