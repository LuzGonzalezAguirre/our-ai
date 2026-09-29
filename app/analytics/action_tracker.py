from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Iterable

from app.connectors.action_tracker import action_tracker


def _date(value) -> date | None:
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _int(value, default=0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def enrich_action(
    action: dict,
    *,
    stale_days: int = 7,
) -> dict:
    today = date.today()
    created = _date(action.get("creado_en"))
    due = _date(
        action.get("fecha_fin")
        or action.get("fecha_fin_base")
    )
    updated = _date(
        action.get("ultimo_update")
        or action.get("actualizado_en")
        or action.get("creado_en")
    )

    is_closed = bool(_int(action.get("es_cerrado")))
    is_cancelled = bool(_int(action.get("es_cancelado")))
    is_open = not is_closed and not is_cancelled

    days_open = (
        (today - created).days
        if created
        else None
    )
    days_overdue = (
        max((today - due).days, 0)
        if due and is_open
        else 0
    )
    days_since_update = (
        max((today - updated).days, 0)
        if updated
        else None
    )

    result = dict(action)
    result.update({
        "is_open": is_open,
        "is_overdue": bool(
            is_open and due and due < today
        ),
        "is_stale": bool(
            is_open
            and days_since_update is not None
            and days_since_update >= stale_days
        ),
        "days_open": days_open,
        "days_overdue": days_overdue,
        "days_since_update": days_since_update,
        "pending_approvals": (
            _int(action.get("solicitudes_fecha_pendientes"))
            + _int(action.get("solicitudes_cierre_pendientes"))
        ),
    })
    return result


def _contains(value, query: str) -> bool:
    if not value:
        return False
    return str(value).casefold() in query.casefold()


def infer_filters(
    question: str,
    actions: Iterable[dict],
) -> dict[str, str]:
    question_folded = question.casefold()
    filters = {}

    dimensions = {
        "departamento": "departamento",
        "area": "area",
        "categoria": "categoria",
        "asignado": "asignado",
        "estado": "estado",
    }

    for output_key, field in dimensions.items():
        values = sorted(
            {
                str(action.get(field)).strip()
                for action in actions
                if action.get(field)
            },
            key=len,
            reverse=True,
        )

        for value in values:
            if value.casefold() in question_folded:
                filters[output_key] = value
                break

    return filters


def apply_filters(
    actions: Iterable[dict],
    filters: dict[str, str],
) -> list[dict]:
    result = []

    for action in actions:
        keep = True
        for field, expected in filters.items():
            if not _contains(
                expected,
                str(action.get(field) or "")
            ) and not _contains(
                action.get(field),
                expected,
            ):
                keep = False
                break

        if keep:
            result.append(action)

    return result


async def overview(
    *,
    stale_days: int = 7,
    filters: dict[str, str] | None = None,
) -> dict:
    raw = await action_tracker.list_actions(
        open_only=False,
    )
    actions = [
        enrich_action(item, stale_days=stale_days)
        for item in raw
    ]

    if filters:
        actions = apply_filters(actions, filters)

    open_actions = [
        action for action in actions
        if action["is_open"]
    ]
    overdue = [
        action for action in open_actions
        if action["is_overdue"]
    ]
    stale = [
        action for action in open_actions
        if action["is_stale"]
    ]
    pending = [
        action for action in open_actions
        if action["pending_approvals"] > 0
    ]

    by_department = Counter(
        action.get("departamento") or "Sin departamento"
        for action in open_actions
    )
    by_category = Counter(
        action.get("categoria") or "Sin categoría"
        for action in open_actions
    )
    by_assignee = Counter(
        action.get("asignado") or "Sin responsable"
        for action in overdue
    )

    return {
        "filters": filters or {},
        "total": len(actions),
        "open": len(open_actions),
        "overdue": len(overdue),
        "stale": len(stale),
        "pending_approval": len(pending),
        "by_department": by_department.most_common(10),
        "by_category": by_category.most_common(10),
        "overdue_by_assignee": by_assignee.most_common(10),
        "top_overdue": sorted(
            overdue,
            key=lambda item: (
                item.get("days_overdue") or 0,
                item.get("days_since_update") or 0,
            ),
            reverse=True,
        )[:15],
        "top_stale": sorted(
            stale,
            key=lambda item: item.get("days_since_update") or 0,
            reverse=True,
        )[:15],
        "actions": open_actions[:100],
    }


async def bottlenecks(
    *,
    stale_days: int = 7,
    filters: dict[str, str] | None = None,
) -> dict:
    data = await overview(
        stale_days=stale_days,
        filters=filters,
    )
    approvals = await action_tracker.pending_approvals()

    if filters:
        approvals = apply_filters(
            approvals,
            {
                key: value
                for key, value in filters.items()
                if key in {
                    "departamento",
                    "area",
                    "asignado",
                }
            },
        )

    reasons = Counter()
    for action in data["top_overdue"]:
        reasons["vencida"] += 1
        if action["is_stale"]:
            reasons["vencida_sin_update"] += 1
        if _int(action.get("hijos_abiertos")):
            reasons["subactividades_abiertas"] += 1
        if _int(action.get("reprogramaciones")) >= 2:
            reasons["reprogramaciones_repetidas"] += 1

    if approvals:
        reasons["esperando_aprobacion"] += len(approvals)

    return {
        "summary": {
            "open": data["open"],
            "overdue": data["overdue"],
            "stale": data["stale"],
            "pending_approvals": len(approvals),
        },
        "signals": reasons.most_common(),
        "overdue_by_assignee": data["overdue_by_assignee"],
        "top_overdue": data["top_overdue"][:10],
        "top_stale": data["top_stale"][:10],
        "pending_approvals": approvals[:20],
    }


async def trends(
    days: int = 90,
    *,
    filters: dict[str, str] | None = None,
) -> dict:
    days = min(max(int(days), 1), 365)
    raw = await action_tracker.list_actions(
        open_only=False,
    )
    actions = [enrich_action(item) for item in raw]

    if filters:
        actions = apply_filters(actions, filters)

    events = await action_tracker.events(days=days)
    codes = {
        action.get("codigo")
        for action in actions
        if action.get("codigo")
    }

    if filters:
        events = [
            event for event in events
            if event.get("codigo") in codes
        ]

    today = date.today()
    start = today.fromordinal(today.toordinal() - days)

    created = [
        action for action in actions
        if (
            (created_at := _date(action.get("creado_en")))
            and created_at >= start
        )
    ]
    closed = [
        action for action in actions
        if (
            (closed_at := _date(action.get("cerrado_en")))
            and closed_at >= start
        )
    ]

    event_types = Counter(
        event.get("tipo") or "otro"
        for event in events
    )

    weekly = defaultdict(
        lambda: {
            "created": 0,
            "closed": 0,
            "date_changes": 0,
            "updates": 0,
        }
    )

    def week_key(value):
        parsed = _date(value)
        if not parsed:
            return None
        iso_year, iso_week, _ = parsed.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    for action in created:
        key = week_key(action.get("creado_en"))
        if key:
            weekly[key]["created"] += 1

    for action in closed:
        key = week_key(action.get("cerrado_en"))
        if key:
            weekly[key]["closed"] += 1

    for event in events:
        key = week_key(event.get("creado_en"))
        if not key:
            continue
        if event.get("tipo") == "fecha":
            weekly[key]["date_changes"] += 1
        elif event.get("tipo") == "update":
            weekly[key]["updates"] += 1

    return {
        "days": days,
        "filters": filters or {},
        "created": len(created),
        "closed": len(closed),
        "events": len(events),
        "event_types": dict(event_types),
        "weekly": [
            {
                "week": week,
                **values,
            }
            for week, values in sorted(weekly.items())
        ],
    }
