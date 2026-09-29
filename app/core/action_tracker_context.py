import json
import re
from collections import Counter
from dataclasses import dataclass

from app.analytics.action_tracker import (
    apply_filters,
    bottlenecks,
    enrich_action,
    infer_filters,
    overview,
    select_actions,
    select_enriched_actions,
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
    "volvo",
    "cummins",
    "eaton",
    "john deere",
    "harley",
    "harley-davidson",
    "tulc",
)

BOTTLENECK_TERMS = (
    "deten",
    "cuello",
    "sin actualiz",
    "estanc",
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


@dataclass
class ActionTrackerChatResult:
    context: str | None = None
    direct_answer: str | None = None
    mode: str | None = None


def _compact_action(action: dict) -> dict:
    fields = (
        "codigo",
        "actividad_padre",
        "titulo",
        "categoria",
        "departamento",
        "area",
        "business_unit",
        "workcenter",
        "scrap_reason",
        "estado",
        "asignado",
        "gerente",
        "prioridad",
        "avance",
        "fecha_fin",
        "fecha_fin_base",
        "creado_en",
        "ultimo_update",
        "external_source_key",
        "generado_automaticamente",
        "reprogramaciones",
        "hijos_abiertos",
        "days_open",
        "days_overdue",
        "days_since_update",
        "pending_approvals",
        "is_open",
        "is_overdue",
        "is_stale",
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
            for child in data.get("children", [])[:15]
        ],
        "updates": data.get("updates", [])[:8],
        "date_changes": data.get("date_changes", [])[:8],
        "approvals": data.get("approvals", [])[:8],
        "audit": data.get("audit", [])[:10],
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


def _value(value, fallback="—"):
    if value is None or value == "":
        return fallback
    return str(value)


def _action_line(action: dict) -> str:
    action = enrich_action(action)
    pieces = [
        f"**{_value(action.get('codigo'))}**",
        _value(action.get("titulo")),
    ]

    details = []

    if action.get("business_unit"):
        details.append(f"BU: {action['business_unit']}")

    if action.get("asignado"):
        details.append(f"Responsable: {action['asignado']}")

    if action.get("estado"):
        details.append(f"Estado: {action['estado']}")

    if action.get("avance") is not None:
        details.append(f"Avance: {action['avance']}%")

    if action.get("fecha_fin"):
        details.append(f"Vence: {action['fecha_fin']}")

    if action.get("is_overdue"):
        details.append(
            f"{action.get('days_overdue', 0)} días vencida"
        )
    elif action.get("is_stale"):
        details.append(
            f"{action.get('days_since_update', 0)} días sin update"
        )

    line = " — ".join(pieces)
    if details:
        line += " · " + " · ".join(details)

    return "- " + line


def _list_answer(
    title: str,
    actions: list[dict],
    empty_text: str,
    limit: int = 12,
) -> str:
    if not actions:
        return empty_text

    lines = [
        f"**{title}: {len(actions)}**",
        "",
    ]

    lines.extend(
        _action_line(action)
        for action in actions[:limit]
    )

    if len(actions) > limit:
        lines.extend([
            "",
            f"Mostrando {limit} de {len(actions)} acciones.",
        ])

    return "\n".join(lines)


def _detail_answer(data: dict, code: str) -> str:
    action = enrich_action(data.get("action") or {})

    if not action:
        return f"No encontré información para {code}."

    lines = [
        f"**{_value(action.get('codigo'), code)} — {_value(action.get('titulo'))}**",
        "",
        f"- Estado: {_value(action.get('estado'))}",
        f"- Responsable: {_value(action.get('asignado'))}",
        f"- Departamento: {_value(action.get('departamento'))}",
        f"- Área: {_value(action.get('area'))}",
        f"- Categoría: {_value(action.get('categoria'))}",
        f"- Avance: {_value(action.get('avance'))}%",
        f"- Fecha compromiso: {_value(action.get('fecha_fin'))}",
        f"- Días abierta: {_value(action.get('days_open'))}",
    ]

    if action.get("is_overdue"):
        lines.append(
            f"- Vencida: sí, {action.get('days_overdue', 0)} días"
        )
    else:
        lines.append("- Vencida: no")

    if action.get("days_since_update") is not None:
        lines.append(
            "- Días desde último update: "
            + str(action["days_since_update"])
        )

    if action.get("pending_approvals"):
        lines.append(
            "- Aprobaciones pendientes: "
            + str(action["pending_approvals"])
        )

    updates = data.get("updates") or []
    if updates:
        latest = updates[0]
        lines.extend([
            "",
            "**Último update**",
            (
                f"- {_value(latest.get('creado_en'))} · "
                f"{_value(latest.get('autor'))}: "
                f"{_value(latest.get('texto'))}"
            ),
        ])

    children = data.get("children") or []
    if children:
        open_children = [
            enrich_action(child)
            for child in children
            if enrich_action(child).get("is_open")
        ]
        lines.append(
            f"- Subactividades abiertas: {len(open_children)}"
        )

    return "\n".join(lines)


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _npi_detail_answer(data: dict, code: str) -> str:
    project = data.get("project") or {}
    summary = data.get("summary") or {}
    items = data.get("items") or []
    parts = [
        row.get("numero_parte")
        for row in data.get("parts", [])
        if row.get("numero_parte")
    ]

    lines = [
        f"**{_value(project.get('codigo'), code)} — {_value(project.get('nombre'))}**",
        "",
        f"- Cliente: {_value(project.get('cliente'))}",
        f"- Estado: {_value(project.get('estado'))}",
        f"- Fecha PPAP: {_value(project.get('fecha_ppap'))}",
        f"- Partes: {', '.join(parts) if parts else '—'}",
        f"- Actividades totales: {_value(summary.get('total_items'), '0')}",
        f"- Pendientes: {_value(summary.get('pending_items'), '0')}",
        f"- Bloqueadas: {_value(summary.get('blocked_items'), '0')}",
        f"- Completadas: {_value(summary.get('completed_items'), '0')}",
    ]

    pending = [
        item for item in items
        if str(item.get("resultado") or "").upper() == "NO"
    ]

    if pending:
        lines.extend([
            "",
            "**Actividades pendientes**",
        ])

        for item in pending[:15]:
            detail = [
                f"Responsable: {_value(item.get('responsable'))}",
                f"Área: {_value(item.get('departamento'))}",
            ]

            if item.get("fecha_compromiso_actual"):
                detail.append(
                    "Compromiso: "
                    + str(item["fecha_compromiso_actual"])
                )

            if str(item.get("bloqueada") or "0") == "1":
                detail.append("Bloqueada")

            lines.append(
                "- **"
                + _value(item.get("numero"))
                + ". "
                + _value(item.get("actividad"))
                + "** · "
                + " · ".join(detail)
            )

        if len(pending) > 15:
            lines.append(
                f"Mostrando 15 de {len(pending)} pendientes."
            )

    return "\n".join(lines)


def _npi_projects_answer(
    projects: list[dict],
    *,
    overdue_only: bool = False,
    pending_only: bool = False,
) -> str:
    filtered = projects

    if overdue_only:
        filtered = [
            project for project in filtered
            if _to_int(project.get("overdue_items")) > 0
        ]

    if pending_only:
        filtered = [
            project for project in filtered
            if _to_int(project.get("pending_items")) > 0
        ]

    if not filtered:
        if overdue_only:
            return "No encontré proyectos NPI con actividades atrasadas."
        if pending_only:
            return "No encontré proyectos NPI con actividades pendientes."
        return "No encontré proyectos NPI."

    title = "Proyectos NPI"
    if overdue_only:
        title += " con atraso"
    elif pending_only:
        title += " con pendientes"

    lines = [
        f"**{title}: {len(filtered)}**",
        "",
    ]

    for project in filtered[:15]:
        lines.append(
            "- **"
            + _value(project.get("codigo"))
            + " — "
            + _value(project.get("nombre"))
            + "** · Cliente: "
            + _value(project.get("cliente"))
            + " · Estado: "
            + _value(project.get("estado"))
            + " · Pendientes: "
            + str(_to_int(project.get("pending_items")))
            + " · Atrasadas: "
            + str(_to_int(project.get("overdue_items")))
            + " · Bloqueadas: "
            + str(_to_int(project.get("blocked_items")))
            + " · PPAP: "
            + _value(project.get("fecha_ppap"))
        )

    if len(filtered) > 15:
        lines.extend([
            "",
            f"Mostrando 15 de {len(filtered)} proyectos.",
        ])

    return "\n".join(lines)



def _approval_answer(
    approvals: list[dict],
) -> str:
    if not approvals:
        return "No encontré aprobaciones pendientes."

    lines = [
        f"**Aprobaciones pendientes: {len(approvals)}**",
        "",
    ]

    for approval in approvals[:15]:
        lines.append(
            "- **"
            + _value(approval.get("codigo"))
            + "** — "
            + _value(approval.get("titulo"))
            + " · Tipo: "
            + _value(approval.get("tipo"))
            + " · Responsable: "
            + _value(approval.get("responsable"))
            + " · Aprobador: "
            + _value(approval.get("aprobador"))
        )

    if len(approvals) > 15:
        lines.extend([
            "",
            f"Mostrando 15 de {len(approvals)}.",
        ])

    return "\n".join(lines)


def _overdue_owner_answer(actions: list[dict]) -> str:
    counts = Counter(
        action.get("asignado") or "Sin responsable"
        for action in actions
    )

    if not counts:
        return "No encontré acciones vencidas abiertas."

    lines = [
        f"**Acciones vencidas abiertas: {len(actions)}**",
        "",
    ]

    for owner, count in counts.most_common(10):
        lines.append(f"- {owner}: **{count}**")

    return "\n".join(lines)


async def build_action_tracker_result(
    question: str,
) -> ActionTrackerChatResult:
    if not action_tracker.configured:
        return ActionTrackerChatResult()

    if not _uses_action_tracker(question):
        return ActionTrackerChatResult()

    folded = question.casefold()
    code_match = ACTION_CODE_RE.search(question)

    try:
        if code_match:
            code = code_match.group(0).upper()

            if code.startswith("NPI-"):
                detail = await action_tracker.get_npi(code)
                return ActionTrackerChatResult(
                    direct_answer=_npi_detail_answer(
                        detail,
                        code,
                    ),
                    mode="npi_detail",
                )

            detail = await action_tracker.get_action(code)

            return ActionTrackerChatResult(
                direct_answer=_detail_answer(detail, code),
                mode="action_detail",
            )

        if "npi" in folded and (
            "proyecto" in folded
            or "proyectos" in folded
            or "atras" in folded
            or "pendiente" in folded
        ):
            projects = await action_tracker.list_npi_projects()
            return ActionTrackerChatResult(
                direct_answer=_npi_projects_answer(
                    projects,
                    overdue_only=(
                        "atras" in folded
                        or "vencid" in folded
                    ),
                    pending_only=(
                        "pendiente" in folded
                        and "atras" not in folded
                        and "vencid" not in folded
                    ),
                ),
                mode="npi_projects",
            )

        raw = await action_tracker.list_actions(
            open_only=False,
        )
        enriched = [
            enrich_action(action)
            for action in raw
        ]
        filters = infer_filters(question, enriched)

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

        if (
            ("vence" in folded or "vencen" in folded)
            and "semana" in folded
            and "vencid" not in folded
        ):
            actions = select_enriched_actions(
                enriched,
                filters=filters,
                due_this_week=True,
            )
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones que vencen esta semana",
                    actions,
                    "No encontré acciones abiertas que venzan esta semana.",
                ),
                mode="due_this_week",
            )

        if (
            "automatic" in folded
            or "automátic" in folded
            or "generadas por" in folded
            or "generados por" in folded
        ):
            actions = select_enriched_actions(
                enriched,
                filters=filters,
                auto_only=True,
                created_this_week=("semana" in folded),
                open_only=False,
            )
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones generadas automáticamente",
                    actions,
                    "No encontré acciones automáticas para ese filtro.",
                ),
                mode="automatic_actions",
            )

        if (
            "sin actualiz" in folded
            or "sin update" in folded
            or "estanc" in folded
        ) and "cuello" not in folded:
            actions = select_enriched_actions(
                enriched,
                filters=filters,
                stale_only=True,
            )
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones sin actualización",
                    actions,
                    "No encontré acciones abiertas sin actualización.",
                ),
                mode="stale_actions",
            )

        if (
            "vencid" in folded
            or "atrasad" in folded
        ) and not any(
            term in folded
            for term in ("deten", "cuello")
        ):
            actions = select_enriched_actions(
                enriched,
                filters=filters,
                overdue_only=True,
            )

            if "quien" in folded or "quién" in folded:
                answer = _overdue_owner_answer(actions)
            else:
                answer = _list_answer(
                    "Acciones vencidas",
                    actions,
                    "No encontré acciones abiertas vencidas.",
                )

            return ActionTrackerChatResult(
                direct_answer=answer,
                mode="overdue_actions",
            )

        if (
            "aprob" in folded
            and not any(term in folded for term in BOTTLENECK_TERMS)
        ):
            approvals = await action_tracker.pending_approvals()

            if filters:
                action_by_code = {
                    action.get("codigo"): action
                    for action in enriched
                }
                allowed_codes = {
                    code
                    for code, action in action_by_code.items()
                    if code
                    and apply_filters([action], filters)
                }
                approvals = [
                    approval
                    for approval in approvals
                    if approval.get("codigo") in allowed_codes
                ]

            return ActionTrackerChatResult(
                direct_answer=_approval_answer(approvals),
                mode="pending_approvals",
            )

        if any(
            term in folded
            for term in TREND_TERMS
        ):
            data = await trends(
                days=_days_from_question(question),
                filters=filters,
            )
            payload = {
                "source": "Action Tracker live",
                "mode": "trends",
                "data": data,
            }
            return ActionTrackerChatResult(
                context=json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                ),
                mode="trends",
            )

        if any(
            term in folded
            for term in BOTTLENECK_TERMS
        ):
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
                        for item in data["top_overdue"][:8]
                    ],
                    "top_stale": [
                        _compact_action(item)
                        for item in data["top_stale"][:8]
                    ],
                    "pending_approvals": (
                        data["pending_approvals"][:10]
                    ),
                },
            }
            return ActionTrackerChatResult(
                context=json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                ),
                mode="bottlenecks",
            )

        data = await overview(
            stale_days=7,
            filters=filters,
        )

        if (
            filters
            or "pendiente" in folded
            or "acciones" in folded
            or "accion" in folded
        ):
            title = "Acciones abiertas"

            if filters:
                labels = [
                    value
                    for value in filters.values()
                    if value
                ]
                if labels:
                    title += " · " + " / ".join(labels)

            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    title,
                    data["actions"],
                    "No encontré acciones abiertas para ese filtro.",
                ),
                mode="filtered_actions",
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
                for item in data["actions"][:12]
            ],
        }
        return ActionTrackerChatResult(
            context=json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            ),
            mode="overview",
        )

    except ActionTrackerError:
        raise
