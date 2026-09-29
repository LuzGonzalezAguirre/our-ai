from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.connectors.action_tracker import ActionTrackerError
from app.core.action_tracker_context import build_action_tracker_result
from app.core.config import settings
from app.core.conversations import conversation_store
from app.core.knowledge import knowledge_store
from app.core.projects import project_store
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
    "Responde en el idioma utilizado por el usuario. "
    "Sé conciso salvo que el usuario pida detalle. "
    "Cuando recibas conocimiento del proyecto, úsalo solamente "
    "si es relevante para la pregunta. "
    "Cuando recibas datos live de Action Tracker, esos datos son "
    "la fuente de verdad para acciones, responsables, fechas, avances "
    "y métricas. No inventes filas, conteos, causas ni responsables. "
    "Distingue hechos medidos de interpretaciones. "
    "No realices ni prometas modificaciones de Action Tracker: "
    "esta integración es de solo lectura."
)


def _knowledge_message(
    chunks: list[tuple[object, float]],
) -> dict[str, str] | None:
    if not chunks:
        return None

    sections = []

    for index, (chunk, score) in enumerate(chunks, start=1):
        sections.append(
            f"[Fragmento {index} | similitud {score:.3f}]\n"
            f"{chunk.content}"
        )

    return {
        "role": "system",
        "content": (
            "Conocimiento recuperado del proyecto actual:\n\n"
            + "\n\n".join(sections)
        ),
    }


async def _save_exchange(
    *,
    conversation_id: str,
    project_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    try:
        await conversation_store.append_exchange(
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            project_id=project_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "La IA respondió, pero no se pudo guardar "
                "la conversación en PostgreSQL."
            ),
        ) from exc


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
) -> ChatResponse:

    project_id = (
        request.project_id
        or settings.default_project_id
    )

    try:
        project = await project_store.get(project_id)

        if project is None:
            raise HTTPException(
                status_code=404,
                detail="El proyecto no existe.",
            )

        if request.conversation_id:
            current_project_id = (
                await conversation_store.get_project_id(
                    request.conversation_id
                )
            )

            if (
                current_project_id is not None
                and current_project_id != project_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "La conversación pertenece a otro proyecto."
                    ),
                )

        conversation_id = (
            request.conversation_id
            or str(uuid4())
        )

        action_result = await build_action_tracker_result(
            request.message
        )

    except HTTPException:
        raise
    except ActionTrackerError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo consultar Action Tracker: "
                + str(exc)
            ),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo preparar el contexto del chat."
            ),
        ) from exc

    if action_result.direct_answer:
        await _save_exchange(
            conversation_id=conversation_id,
            project_id=project_id,
            user_message=request.message,
            assistant_message=action_result.direct_answer,
        )

        return ChatResponse(
            response=action_result.direct_answer,
            model=settings.ollama_model,
            conversation_id=conversation_id,
            project_id=project_id,
            knowledge_chunks_used=0,
            action_tracker_used=True,
        )

    try:
        history = await conversation_store.get_messages(
            conversation_id,
            limit=settings.chat_history_messages,
        )

        if action_result.context:
            knowledge_chunks = []
        else:
            knowledge_chunks = await knowledge_store.retrieve(
                project_id=project_id,
                query=request.message,
                top_k=3,
            )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo preparar el contexto del chat."
            ),
        ) from exc

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
    ]

    knowledge_message = _knowledge_message(
        knowledge_chunks
    )

    if knowledge_message:
        messages.append(knowledge_message)

    if action_result.context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Datos live de Action Tracker. "
                    "Úsalos para responder la pregunta actual. "
                    "Los cálculos incluidos ya fueron hechos por "
                    "el Analytics Engine; no los recalcules ni "
                    "inventes valores faltantes.\n\n"
                    + action_result.context
                ),
            }
        )

    messages.extend(
        [
            *history,
            {
                "role": "user",
                "content": request.message,
            },
        ]
    )

    try:
        response = await provider.chat(
            messages=messages
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    await _save_exchange(
        conversation_id=conversation_id,
        project_id=project_id,
        user_message=request.message,
        assistant_message=response,
    )

    return ChatResponse(
        response=response,
        model=settings.ollama_model,
        conversation_id=conversation_id,
        project_id=project_id,
        knowledge_chunks_used=len(knowledge_chunks),
        action_tracker_used=bool(action_result.context),
    )


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
)
async def list_conversations(
    project_id: str | None = Query(default=None),
) -> list[ConversationSummary]:
    try:
        conversations = await conversation_store.list_conversations(
            project_id=project_id
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudieron cargar las conversaciones.",
        ) from exc

    return [
        ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            project_id=conversation_project_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        for conversation, conversation_project_id
        in conversations
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
