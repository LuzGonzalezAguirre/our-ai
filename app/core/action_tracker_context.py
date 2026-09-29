import json
import re

from app.analytics.action_tracker import (
    bottlenecks,
    enrich_action,
    infer_filters,
    overview,
    trends,
)
from app.connectors.action_tracker import (
    ActionTrackerError,
    action_tracker,
)
from app.core.config import settings


ACTION_CODE_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*-\d+(?:-\d+)*\b",
    re.IGNORECASE,
)

ACTION_TRACKER_TERMS = (
    "accion",
    "acciones",
    "action tracker",
    "npi",
    "scrap",
    "mantenimiento",
    "maintenance",
    "manufacturing",
    "manufactura",
    "quality",
    "calidad",
    "materiales",
    "produccion",
    "producción",
    "aprobacion",
    "aprobación",
    "vencid",
    "atras",
    "pendiente",
    "cuello",
    "deten",
    "actualizacion",
    "actualización",
    "reprogram",
)

BOTTLENECK_TERMS = (
    "deten",
    "cuello",
    "atras",
    "vencid",
    "sin actualiz",
    "estanc",
    "esperando aprob",
    "mas acciones atras",
    "más acciones atras",
)

TREND_TERMS = (
    "tendencia",
    "tendencias",
    "ultimos 3 meses",
    "últimos 3 meses",
    "90 dias",
    "90 días",
    "historico",
    "histórico",
)


def _compact_action(action: dict) -> dict:
    fields = (
        "codigo",
        "actividad_padre",
        "titulo",
        "categoria",
        "departamento",
        "area",
        "estado",
        "asignado",
        "gerente",
        "prioridad",
        "avance",
        "fecha_fin",
        "fecha_fin_base",
        "ultimo_update",
        "reprogramaciones",
        "hijos_abiertos",
        "days_open",
        "days_overdue",
        "days_since_update",
        "pending_approvals",
    )
    return {
        field: action.get(field)
        for field in fields
        if action.get(field) is not None
    }


def _compact_detail(data: dict) -> dict:
    action = enrich_action(data.get("action") or {})

    return {
        "action": _compact_action(action),
        "children": [
            _compact_action(enrich_action(child))
            for child in data.get("children", [])[:30]
        ],
        "updates": data.get("updates", [])[:15],
        "date_changes": data.get("date_changes", [])[:15],
        "approvals": data.get("approvals", [])[:15],
        "audit": data.get("audit", [])[:20],
    }


def _days_from_question(question: str) -> int:
    text = question.casefold()

    if "3 meses" in text or "90" in text:
        return 90
    if "mes" in text or "30" in text:
        return 30
    if "semana" in text or "7 " in text:
        return 7
    return 90


def _uses_action_tracker(question: str) -> bool:
    folded = question.casefold()

    if ACTION_CODE_RE.search(question):
        return True

    return any(
        term in folded
        for term in ACTION_TRACKER_TERMS
    )


async def build_action_tracker_context(
    question: str,
) -> str | None:
    if not action_tracker.configured:
        return None

    if not _uses_action_tracker(question):
        return None

    code_match = ACTION_CODE_RE.search(question)

    try:
        if code_match:
            code = code_match.group(0).upper()
            detail = await action_tracker.get_action(code)

            payload = {
                "source": "Action Tracker live",
                "mode": "action_detail",
                "code": code,
                "data": _compact_detail(detail),
            }
            return json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )

        raw = await action_tracker.list_actions(
            open_only=False,
        )
        filters = infer_filters(question, raw)

        folded = question.casefold()
        if (
            settings.action_tracker_default_user
            and any(
                phrase in folded
                for phrase in (
                    "mis acciones",
                    "que tengo",
                    "qué tengo",
                    "tengo pendiente",
                )
            )
        ):
            filters["asignado"] = (
                settings.action_tracker_default_user
            )

        if any(term in folded for term in TREND_TERMS):
            data = await trends(
                days=_days_from_question(question),
                filters=filters,
            )
            payload = {
                "source": "Action Tracker live",
                "mode": "trends",
                "data": data,
            }

        elif any(
            term in folded
            for term in BOTTLENECK_TERMS
        ) or "aprob" in folded:
            data = await bottlenecks(
                stale_days=7,
                filters=filters,
            )
            payload = {
                "source": "Action Tracker live",
                "mode": "bottlenecks",
                "filters": filters,
                "data": {
                    **data,
                    "top_overdue": [
                        _compact_action(item)
                        for item in data["top_overdue"]
                    ],
                    "top_stale": [
                        _compact_action(item)
                        for item in data["top_stale"]
                    ],
                },
            }

        else:
            data = await overview(
                stale_days=7,
                filters=filters,
            )
            payload = {
                "source": "Action Tracker live",
                "mode": "overview",
                "filters": filters,
                "data": {
                    key: value
                    for key, value in data.items()
                    if key != "actions"
                },
                "actions": [
                    _compact_action(item)
                    for item in data["actions"][:30]
                ],
            }

        return json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )

    except ActionTrackerError:
        raise
