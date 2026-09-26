from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.core.knowledge import knowledge_store
from app.core.projects import project_store
from app.schemas.projects import (
    KnowledgeCreate,
    KnowledgeResponse,
)


router = APIRouter(
    prefix="/v1/projects/{project_id}/knowledge",
    tags=["Knowledge"],
)


async def _require_project(project_id: str) -> None:
    project = await project_store.get(project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="El proyecto no existe.",
        )


@router.get(
    "",
    response_model=list[KnowledgeResponse],
)
async def list_knowledge(
    project_id: str,
) -> list[KnowledgeResponse]:
    try:
        await _require_project(project_id)
        sources = await knowledge_store.list_sources(project_id)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo cargar el conocimiento.",
        ) from exc

    return [
        KnowledgeResponse(
            id=source.id,
            project_id=source.project_id,
            title=source.title,
            chunk_count=chunk_count,
            created_at=source.created_at,
        )
        for source, chunk_count in sources
    ]


@router.post(
    "",
    response_model=KnowledgeResponse,
    status_code=201,
)
async def add_knowledge(
    project_id: str,
    request: KnowledgeCreate,
) -> KnowledgeResponse:
    try:
        await _require_project(project_id)

        source = await knowledge_store.add_text(
            project_id=project_id,
            title=request.title,
            content=request.content,
        )

        sources = await knowledge_store.list_sources(project_id)
        chunk_count = next(
            count
            for item, count in sources
            if item.id == source.id
        )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo guardar el conocimiento.",
        ) from exc

    return KnowledgeResponse(
        id=source.id,
        project_id=source.project_id,
        title=source.title,
        chunk_count=chunk_count,
        created_at=source.created_at,
    )


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_knowledge(
    project_id: str,
    source_id: str,
) -> Response:
    try:
        deleted = await knowledge_store.delete_source(
            project_id,
            source_id,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo eliminar el conocimiento.",
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="La fuente de conocimiento no existe.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
