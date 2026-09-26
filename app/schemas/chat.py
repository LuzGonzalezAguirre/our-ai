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


class ChatResponse(BaseModel):
    response: str
    model: str
    conversation_id: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
