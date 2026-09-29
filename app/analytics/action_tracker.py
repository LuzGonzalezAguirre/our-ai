from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import re
from typing import Iterable

from app.connectors.action_tracker import action_tracker


BU_RE = re.compile(r"\\bBU:\\s*([^|\\n]+)", re.IGNORECASE)
WC_RE = re.compile(r"\\bWC:\\s*([^|\\n]+)", re.IGNORECASE)
REASON_RE = re.compile(r"^Razón:\\s*([^|\\n]+)", re.IGNORECASE | re.MULTILINE)


def _extract(pattern: re.Pattern, value: str | None) -> str | None:
    if not value:
        return None

    match = pattern.search(str(value))
    if not match:
        return None

    result = match.group(1).strip()
    return result or None


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
    description = str(action.get("descripcion") or "")
    business_unit = _extract(BU_RE, description)
    workcenter = _extract(WC_RE, description)
    scrap_reason = _extract(REASON_RE, description)

    result.update({
        "business_unit": business_unit,
        "workcenter": workcenter,
        "scrap_reason": scrap_reason,
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


def infer_filters(
    question: str,
    actions: Iterable[dict],
) -> dict[str, str]:
    question_folded = question.casefold()
    filters = {}

    dimensions = (
        "departamento",
        "area",
        "categoria",
        "asignado",
        "estado",
        "business_unit",
    )

    for field in dimensions:
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
                filters[field] = value
                break

    return filters


def apply_filters(
    actions: Iterable[dict],
    filters: dict[str, str],
) -> list[dict]:
    aliases = {
        "asignado": ("asignado", "responsable"),
        "departamento": ("departamento",),
        "area": ("area",),
        "categoria": ("categoria",),
        "estado": ("estado",),
        "business_unit": ("business_unit",),
    }

    result = []

    for action in actions:
        keep = True

        for field, expected in filters.items():
            candidates = aliases.get(field, (field,))
            values = [
                str(action.get(candidate) or "").casefold()
                for candidate in candidates
            ]

            if not any(
                expected.casefold() in value
                for value in values
            ):
                keep = False
                break

        if keep:
            result.append(action)

    return result


async def select_actions(
    *,
    filters: dict[str, str] | None = None,
    overdue_only: bool = False,
    stale_only: bool = False,
    due_within_days: int | None = None,
    due_this_week: bool = False,
    auto_only: bool = False,
    created_within_days: int | None = None,
    created_this_week: bool = False,
    open_only: bool = True,
    stale_days: int = 7,
) -> list[dict]:
    raw = await action_tracker.list_actions(
        open_only=False,
    )
    actions = [
        enrich_action(item, stale_days=stale_days)
        for item in raw
    ]

    if filters:
        actions = apply_filters(actions, filters)

    today = date.today()
    selected = []

    for action in actions:
        if open_only and not action["is_open"]:
            continue

        if overdue_only and not action["is_overdue"]:
            continue

        if stale_only and not action["is_stale"]:
            continue

        if auto_only and not bool(
            _int(action.get("generado_automaticamente"))
        ):
            continue

        due = _date(
            action.get("fecha_fin")
            or action.get("fecha_fin_base")
        )

        if due_this_week:
            week_end = today + timedelta(
                days=6 - today.weekday()
            )
            if (
                due is None
                or due < today
                or due > week_end
            ):
                continue
        elif due_within_days is not None:
            if (
                due is None
                or due < today
                or due > today + timedelta(days=due_within_days)
            ):
                continue

        if created_this_week:
            created = _date(action.get("creado_en"))
            week_start = today - timedelta(
                days=today.weekday()
            )
            if (
                created is None
                or created < week_start
                or created > today
            ):
                continue
        elif created_within_days is not None:
            created = _date(action.get("creado_en"))
            if (
                created is None
                or created < today - timedelta(days=created_within_days)
            ):
                continue

        selected.append(action)

    if overdue_only:
        selected.sort(
            key=lambda item: item.get("days_overdue") or 0,
            reverse=True,
        )
    elif stale_only:
        selected.sort(
            key=lambda item: item.get("days_since_update") or 0,
            reverse=True,
        )
    elif due_this_week or due_within_days is not None:
        selected.sort(
            key=lambda item: (
                _date(item.get("fecha_fin") or item.get("fecha_fin_base"))
                or date.max
            )
        )
    else:
        selected.sort(
            key=lambda item: str(item.get("actualizado_en") or ""),
            reverse=True,
        )

    return selected


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

    signals = {
        "overdue_stale": sum(
            1 for action in overdue
            if action["is_stale"]
        ),
        "open_children": sum(
            1 for action in open_actions
            if _int(action.get("hijos_abiertos")) > 0
        ),
        "reprogrammed_multiple": sum(
            1 for action in open_actions
            if _int(action.get("reprogramaciones")) >= 2
        ),
        "pending_approval": len(pending),
    }

    return {
        "filters": filters or {},
        "total": len(actions),
        "open": len(open_actions),
        "overdue": len(overdue),
        "stale": len(stale),
        "pending_approval": len(pending),
        "signals": signals,
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
        "actions": open_actions,
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
        approval_filters = {
            key: value
            for key, value in filters.items()
            if key in {
                "departamento",
                "area",
                "asignado",
            }
        }
        approvals = apply_filters(
            approvals,
            approval_filters,
        )

        allowed_codes = {
            action.get("codigo")
            for action in data["actions"]
        }
        approvals = [
            approval for approval in approvals
            if approval.get("codigo") in allowed_codes
        ]

    reasons = Counter({
        "vencida": data["overdue"],
        "vencida_sin_update": data["signals"]["overdue_stale"],
        "subactividades_abiertas": data["signals"]["open_children"],
        "reprogramaciones_repetidas": data["signals"]["reprogrammed_multiple"],
        "esperando_aprobacion": len(approvals),
    })

    return {
        "summary": {
            "open": data["open"],
            "overdue": data["overdue"],
            "stale": data["stale"],
            "pending_approvals": len(approvals),
        },
        "signals": [
            (name, count)
            for name, count in reasons.most_common()
            if count > 0
        ],
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
    start = today - timedelta(days=days)

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
