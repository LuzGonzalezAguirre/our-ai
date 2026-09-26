from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.providers.ollama import OllamaProvider
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter(
    prefix="/v1",
    tags=["AI"],
)


provider = OllamaProvider()


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(request: ChatRequest) -> ChatResponse:

    try:
        response = await provider.chat(
            message=request.message,
            system_prompt=(
                "Eres un asistente de inteligencia artificial. "
                "Responde de manera clara, precisa y útil. "
                "Responde en el idioma utilizado por el usuario."
            ),
        )

        return ChatResponse(
            response=response,
            model=settings.ollama_model,
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
