from fastapi import APIRouter, HTTPException, Query

from app.analytics.action_tracker import (
    bottlenecks,
    overview,
    trends,
)
from app.connectors.action_tracker import (
    ActionTrackerError,
    action_tracker,
)


router = APIRouter(
    prefix="/v1/integrations/action-tracker",
    tags=["Action Tracker"],
)


def _filters(
    departamento: str | None,
    area: str | None,
    categoria: str | None,
    asignado: str | None,
    estado: str | None,
) -> dict[str, str]:
    return {
        key: value
        for key, value in {
            "departamento": departamento,
            "area": area,
            "categoria": categoria,
            "asignado": asignado,
            "estado": estado,
        }.items()
        if value
    }


@router.get("/health")
async def integration_health():
    if not action_tracker.configured:
        return {
            "status": "not_configured",
            "read_only": True,
        }

    try:
        result = await action_tracker.health()
    except ActionTrackerError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    return {
        "status": "ok",
        "read_only": True,
        "action_tracker": result,
    }


@router.get("/overview")
async def integration_overview(
    stale_days: int = Query(default=7, ge=1, le=90),
    departamento: str | None = None,
    area: str | None = None,
    categoria: str | None = None,
    asignado: str | None = None,
    estado: str | None = None,
):
    try:
        return await overview(
            stale_days=stale_days,
            filters=_filters(
                departamento,
                area,
                categoria,
                asignado,
                estado,
            ),
        )
    except ActionTrackerError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/bottlenecks")
async def integration_bottlenecks(
    stale_days: int = Query(default=7, ge=1, le=90),
    departamento: str | None = None,
    area: str | None = None,
    categoria: str | None = None,
    asignado: str | None = None,
):
    try:
        return await bottlenecks(
            stale_days=stale_days,
            filters=_filters(
                departamento,
                area,
                categoria,
                asignado,
                None,
            ),
        )
    except ActionTrackerError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/trends")
async def integration_trends(
    days: int = Query(default=90, ge=1, le=365),
    departamento: str | None = None,
    area: str | None = None,
    categoria: str | None = None,
    asignado: str | None = None,
):
    try:
        return await trends(
            days=days,
            filters=_filters(
                departamento,
                area,
                categoria,
                asignado,
                None,
            ),
        )
    except ActionTrackerError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/actions/{code}")
async def integration_action_detail(code: str):
    try:
        return await action_tracker.get_action(code)
    except ActionTrackerError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
