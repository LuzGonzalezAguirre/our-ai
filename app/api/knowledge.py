import logging

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.core.knowledge import knowledge_store
from app.core.projects import project_store
from app.schemas.projects import (
    KnowledgeCreate,
    KnowledgeResponse,
)


logger = logging.getLogger(__name__)


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


def _database_error_detail(exc: SQLAlchemyError) -> str:
    original = getattr(exc, "orig", None)

    if original is None:
        return exc.__class__.__name__

    detail = str(original).strip()
    if not detail:
        return original.__class__.__name__

    # Avoid sending an excessively large SQL/parameter payload to the UI.
    return detail[:500]


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
        logger.exception("Could not load project knowledge")
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo cargar el conocimiento: "
                + _database_error_detail(exc)
            ),
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

        source, chunk_count = await knowledge_store.add_text(
            project_id=project_id,
            title=request.title,
            content=request.content,
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
        logger.exception("Could not persist project knowledge")
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo guardar el conocimiento en PostgreSQL: "
                + _database_error_detail(exc)
            ),
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
        logger.exception("Could not delete project knowledge")
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo eliminar el conocimiento: "
                + _database_error_detail(exc)
            ),
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="La fuente de conocimiento no existe.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
