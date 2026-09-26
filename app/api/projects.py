from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.projects import project_store
from app.schemas.projects import (
    ProjectCreate,
    ProjectResponse,
)


router = APIRouter(
    prefix="/v1/projects",
    tags=["Projects"],
)


@router.get(
    "",
    response_model=list[ProjectResponse],
)
async def list_projects() -> list[ProjectResponse]:
    try:
        projects = await project_store.list_projects()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudieron cargar los proyectos.",
        ) from exc

    return [
        ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        for project in projects
    ]


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=201,
)
async def create_project(
    request: ProjectCreate,
) -> ProjectResponse:
    try:
        project = await project_store.create(
            name=request.name,
            description=request.description,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un proyecto con ese nombre.",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo crear el proyecto.",
        ) from exc

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
