from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.conversations import conversation_store
from app.providers.ollama import OllamaProvider
from app.schemas.chat import ChatRequest, ChatResponse


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

    history = conversation_store.get_messages(
        conversation_id
    )

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

    conversation_store.add_message(
        conversation_id=conversation_id,
        role="user",
        content=request.message,
    )

    conversation_store.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=response,
    )

    return ChatResponse(
        response=response,
        model=settings.ollama_model,
        conversation_id=conversation_id,
    )
