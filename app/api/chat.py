from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.conversations import conversation_store
from app.providers.ollama import OllamaProvider
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationSummary,
    MessageResponse,
)


router = APIRouter(
    prefix="/v1",
    tags=["AI"],
)


provider = OllamaProvider()


SYSTEM_PROMPT = (
    "Eres un asistente de inteligencia artificial. "
    "Responde de manera clara, precisa y útil. "
    "Responde en el idioma utilizado por el usuario."
)


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
) -> ChatResponse:

    conversation_id = (
        request.conversation_id
        or str(uuid4())
    )

    try:
        history = await conversation_store.get_messages(
            conversation_id
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo leer la conversación desde PostgreSQL."
            ),
        ) from exc

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        *history,
        {
            "role": "user",
            "content": request.message,
        },
    ]

    try:
        response = await provider.chat(
            messages=messages
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    try:
        await conversation_store.append_exchange(
            conversation_id=conversation_id,
            user_message=request.message,
            assistant_message=response,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "La IA respondió, pero no se pudo guardar "
                "la conversación en PostgreSQL."
            ),
        ) from exc

    return ChatResponse(
        response=response,
        model=settings.ollama_model,
        conversation_id=conversation_id,
    )


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
)
async def list_conversations() -> list[ConversationSummary]:
    try:
        conversations = await conversation_store.list_conversations()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudieron cargar las conversaciones.",
        ) from exc

    return [
        ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        for conversation in conversations
    ]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def conversation_messages(
    conversation_id: str,
) -> list[MessageResponse]:
    try:
        exists = await conversation_store.conversation_exists(
            conversation_id
        )

        if not exists:
            raise HTTPException(
                status_code=404,
                detail="La conversación no existe.",
            )

        messages = await conversation_store.get_message_records(
            conversation_id
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo cargar el historial.",
        ) from exc

    return [
        MessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )
        for message in messages
    ]


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: str,
) -> Response:
    try:
        deleted = await conversation_store.delete(
            conversation_id
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo eliminar la conversación.",
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="La conversación no existe.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
