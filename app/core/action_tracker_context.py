import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from app.analytics.action_tracker import (
    apply_filters,
    bottlenecks,
    enrich_action,
    infer_filters,
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
NPI_PROJECT_RE = re.compile(
    r"\bNPI-\d{4}\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\b(\d{1,2})\b")

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

CONCEPTUAL_PREFIXES = (
    "qué significa",
    "que significa",
    "qué es",
    "que es",
    "para qué se usa",
    "para que se usa",
    "cómo funciona",
    "como funciona",
    "cómo se decide",
    "como se decide",
    "cómo se evita",
    "como se evita",
    "cuál es la diferencia",
    "cual es la diferencia",
    "cuáles son los targets",
    "cuales son los targets",
    "quién debe ser",
    "quien debe ser",
    "explícame por qué",
    "explicame por que",
    "explícame cómo",
    "explicame como",
)

FOLLOWUP_HINTS = (
    "de esas",
    "de esos",
    "esas",
    "esos",
    "cuáles siguen",
    "cuales siguen",
    "cuáles están",
    "cuales estan",
    "quién es responsable",
    "quien es responsable",
    "quién concentra",
    "quien concentra",
    "alguna está",
    "alguna esta",
    "resúmelo",
    "resumelo",
    "resúmeme",
    "resumeme",
    "toma el proyecto",
    "más tiempo",
    "mas tiempo",
    "recurrencia",
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

DOMAIN_ALIASES = {
    "scrap": ("scrap",),
    "maintenance": ("maintenance", "mantenimiento", "mtto"),
    "npi": ("npi",),
}


@dataclass
class ActionTrackerChatResult:
    context: str | None = None
    direct_answer: str | None = None
    mode: str | None = None


def _fold(value: str | None) -> str:
    return str(value or "").casefold().strip()


def _value(value, fallback="—"):
    if value is None or value == "":
        return fallback
    return str(value)


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_date(value) -> date | None:
    if not value:
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _is_conceptual(question: str) -> bool:
    if ACTION_CODE_RE.search(question):
        return False

    folded = _fold(question)

    if any(folded.startswith(prefix) for prefix in CONCEPTUAL_PREFIXES):
        return True

    conceptual_phrases = (
        "qué quiere decir",
        "que quiere decir",
        "qué representa",
        "que representa",
        "regla de negocio",
        "reglas de negocio",
    )
    return any(phrase in folded for phrase in conceptual_phrases)


def _is_followup(question: str) -> bool:
    folded = _fold(question)
    return any(hint in folded for hint in FOLLOWUP_HINTS)


def _history_messages(history: list[dict] | None) -> list[dict]:
    if not history:
        return []
    return history[-12:]


def _recent_project_code(
    question: str,
    history: list[dict] | None,
) -> str | None:
    current = NPI_PROJECT_RE.search(question)
    if current:
        return current.group(0).upper()

    for message in reversed(_history_messages(history)):
        content = str(message.get("content") or "")

        if message.get("role") == "user":
            domain = _detect_domain(content)
            if domain in {"scrap", "maintenance"}:
                return None

        match = NPI_PROJECT_RE.search(content)
        if match:
            return match.group(0).upper()

    return None


def _detect_domain(text: str) -> str | None:
    folded = _fold(text)

    for domain, aliases in DOMAIN_ALIASES.items():
        if any(alias in folded for alias in aliases):
            return domain

    return None


def _history_scope_text(
    history: list[dict] | None,
) -> str:
    for message in reversed(_history_messages(history)):
        if message.get("role") != "user":
            continue

        text = str(message.get("content") or "")
        if (
            _detect_domain(text)
            or any(
                token in _fold(text)
                for token in (
                    "volvo",
                    "cummins",
                    "eaton",
                    "john deere",
                    "tulc",
                    "harley",
                    "manufactura",
                    "manufacturing",
                    "calidad",
                    "quality",
                )
            )
            or "vencid" in _fold(text)
            or "atras" in _fold(text)
        ):
            return text

    return ""


def _history_mentions_overdue(
    history: list[dict] | None,
) -> bool:
    for message in reversed(_history_messages(history)):
        if message.get("role") != "user":
            continue

        folded = _fold(message.get("content"))
        if "vencid" in folded or "atrasad" in folded:
            return True

        if any(
            reset in folded
            for reset in (
                "muéstrame",
                "muestrame",
                "qué acciones",
                "que acciones",
                "qué proyectos",
                "que proyectos",
            )
        ):
            break

    return False


def _question_uses_action_tracker(
    question: str,
    history: list[dict] | None,
) -> bool:
    if ACTION_CODE_RE.search(question):
        return True

    folded = _fold(question)
    if any(term in folded for term in ACTION_TRACKER_TERMS):
        return True

    return bool(
        _is_followup(question)
        and _history_scope_text(history)
    )


def _domain_filter(
    actions: list[dict],
    domain: str | None,
) -> list[dict]:
    if not domain:
        return actions

    filtered = []

    for action in actions:
        code = _fold(action.get("codigo"))
        category = _fold(action.get("categoria"))
        title = _fold(action.get("titulo"))

        if domain == "scrap":
            keep = (
                code.startswith("scrap-")
                or "scrap" in category
                or "scrap" in title
            )
        elif domain == "maintenance":
            keep = (
                code.startswith("mtto-")
                or "maintenance" in category
                or "mantenimiento" in category
                or "maintenance" in title
                or "mantenimiento" in title
            )
        elif domain == "npi":
            keep = code.startswith("npi-")
        else:
            keep = True

        if keep:
            filtered.append(action)

    return filtered


def _combined_filters(
    question: str,
    history: list[dict] | None,
    actions: list[dict],
) -> tuple[dict[str, str], str | None]:
    current_filters = infer_filters(question, actions)
    current_domain = _detect_domain(question)

    if current_filters and current_domain:
        return current_filters, current_domain

    history_text = _history_scope_text(history)
    history_filters = (
        infer_filters(history_text, actions)
        if history_text
        else {}
    )
    history_domain = _detect_domain(history_text)

    if _is_followup(question):
        inherited = dict(history_filters)
        inherited.update(current_filters)
        return (
            inherited,
            current_domain or history_domain,
        )

    return current_filters, current_domain


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


def _action_line(action: dict) -> str:
    action = enrich_action(action)
    line = (
        f"**{_value(action.get('codigo'))}** — "
        f"{_value(action.get('titulo'))}"
    )

    details = []

    if action.get("business_unit"):
        details.append(
            f"BU: {action['business_unit']}"
        )

    if action.get("asignado"):
        details.append(
            f"Responsable: {action['asignado']}"
        )

    if action.get("estado"):
        details.append(
            f"Estado: {action['estado']}"
        )

    if action.get("avance") is not None:
        details.append(
            f"Avance: {action['avance']}%"
        )

    if action.get("fecha_fin"):
        details.append(
            f"Vence: {action['fecha_fin']}"
        )

    if action.get("is_overdue"):
        details.append(
            f"{action.get('days_overdue', 0)} días vencida"
        )
    elif action.get("is_stale"):
        details.append(
            f"{action.get('days_since_update', 0)} días sin update"
        )

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


def _owners_answer(
    title: str,
    actions: list[dict],
    limit: int = 10,
) -> str:
    if not actions:
        return "No encontré acciones para ese alcance."

    counts = Counter(
        action.get("asignado") or "Sin responsable"
        for action in actions
    )

    lines = [
        f"**{title}**",
        "",
    ]

    for owner, count in counts.most_common(limit):
        lines.append(f"- {owner}: **{count}**")

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

    children = data.get("children") or []
    open_children = [
        enrich_action(child)
        for child in children
        if enrich_action(child).get("is_open")
    ]
    lines.append(
        f"- Subactividades abiertas: {len(open_children)}"
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

    return "\n".join(lines)


def _npi_pending_items(data: dict) -> list[dict]:
    return [
        item
        for item in data.get("items", [])
        if _fold(item.get("resultado")) == "no"
    ]


def _npi_blocked_items(data: dict) -> list[dict]:
    return [
        item
        for item in _npi_pending_items(data)
        if _to_int(item.get("bloqueada")) == 1
    ]


def _npi_overdue_items(data: dict) -> list[dict]:
    today = date.today()
    overdue = []

    for item in _npi_pending_items(data):
        due = _parse_date(
            item.get("fecha_compromiso_actual")
            or item.get("tracker_fecha_fin")
        )
        if due and due < today:
            item = dict(item)
            item["days_overdue"] = (today - due).days
            overdue.append(item)

    overdue.sort(
        key=lambda item: item.get("days_overdue", 0),
        reverse=True,
    )
    return overdue


def _npi_header(data: dict, code: str) -> list[str]:
    project = data.get("project") or {}
    summary = data.get("summary") or {}
    parts = [
        row.get("numero_parte")
        for row in data.get("parts", [])
        if row.get("numero_parte")
    ]

    return [
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


def _npi_item_line(item: dict) -> str:
    details = [
        f"Responsable: {_value(item.get('responsable'))}",
        f"Área: {_value(item.get('departamento'))}",
    ]

    due = (
        item.get("fecha_compromiso_actual")
        or item.get("tracker_fecha_fin")
    )
    if due:
        details.append(f"Compromiso: {due}")

    if _to_int(item.get("bloqueada")) == 1:
        details.append("Bloqueada")

    if item.get("days_overdue"):
        details.append(
            f"{item['days_overdue']} días vencida"
        )

    return (
        "- **"
        + _value(item.get("numero"))
        + ". "
        + _value(item.get("actividad"))
        + "** · "
        + " · ".join(details)
    )


def _npi_items_answer(
    data: dict,
    code: str,
    *,
    mode: str,
    limit: int = 15,
) -> str:
    if mode == "blocked":
        items = _npi_blocked_items(data)
        label = "Actividades bloqueadas"
    elif mode == "overdue":
        items = _npi_overdue_items(data)
        label = "Actividades vencidas"
    else:
        items = _npi_pending_items(data)
        label = "Actividades pendientes"

    lines = _npi_header(data, code)
    lines.extend(["", f"**{label}: {len(items)}**"])

    if not items:
        lines.append("")
        lines.append(
            f"No hay {label.casefold()} en este proyecto."
        )
        return "\n".join(lines)

    lines.append("")
    lines.extend(
        _npi_item_line(item)
        for item in items[:limit]
    )

    if len(items) > limit:
        lines.extend([
            "",
            f"Mostrando {limit} de {len(items)}.",
        ])

    return "\n".join(lines)


def _npi_owners_answer(
    data: dict,
    code: str,
) -> str:
    pending = _npi_pending_items(data)
    counts = Counter(
        item.get("responsable") or "Sin responsable"
        for item in pending
    )

    lines = _npi_header(data, code)
    lines.extend([
        "",
        "**Pendientes por responsable**",
        "",
    ])

    if not counts:
        lines.append("- No hay actividades pendientes.")
    else:
        for owner, count in counts.most_common():
            lines.append(f"- {owner}: **{count}**")

    return "\n".join(lines)


def _npi_status_answer(
    data: dict,
    code: str,
) -> str:
    pending = _npi_pending_items(data)
    blocked = _npi_blocked_items(data)
    overdue = _npi_overdue_items(data)
    owners = Counter(
        item.get("responsable") or "Sin responsable"
        for item in pending
    )

    lines = _npi_header(data, code)
    lines.extend([
        "",
        "**Status**",
        f"- Pendientes: {len(pending)}",
        f"- Vencidas: {len(overdue)}",
        f"- Bloqueadas: {len(blocked)}",
    ])

    if owners:
        owner, count = owners.most_common(1)[0]
        lines.append(
            f"- Mayor concentración de pendientes: {owner} ({count})"
        )

    if overdue:
        lines.extend([
            "",
            "**Vencidas principales**",
        ])
        lines.extend(
            _npi_item_line(item)
            for item in overdue[:5]
        )

    return "\n".join(lines)


def _npi_combined_blocked_overdue(
    data: dict,
    code: str,
) -> str:
    blocked = _npi_blocked_items(data)
    overdue = _npi_overdue_items(data)

    lines = _npi_header(data, code)
    lines.extend([
        "",
        f"**Bloqueadas: {len(blocked)}**",
    ])

    if blocked:
        lines.extend(
            _npi_item_line(item)
            for item in blocked[:10]
        )
    else:
        lines.append("- Ninguna.")

    lines.extend([
        "",
        f"**Realmente vencidas: {len(overdue)}**",
    ])

    if overdue:
        lines.extend(
            _npi_item_line(item)
            for item in overdue[:10]
        )
    else:
        lines.append("- Ninguna.")

    return "\n".join(lines)


def _npi_projects_answer(
    projects: list[dict],
    *,
    overdue_only: bool = False,
    pending_only: bool = False,
) -> str:
    filtered = list(projects)

    if overdue_only:
        filtered = [
            project
            for project in filtered
            if _to_int(project.get("overdue_items")) > 0
        ]

    if pending_only:
        filtered = [
            project
            for project in filtered
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

    return "\n".join(lines)


def _scoped_issue_answer(
    actions: list[dict],
) -> str:
    if not actions:
        return "No encontré acciones en el alcance actual."

    relevant = [
        action
        for action in actions
        if _to_int(action.get("pending_approvals")) > 0
        or _to_int(action.get("hijos_abiertos")) > 0
    ]

    if not relevant:
        return (
            "Ninguna de las acciones del alcance actual tiene "
            "aprobaciones pendientes ni subactividades abiertas."
        )

    lines = [
        f"**Acciones con dependencias pendientes: {len(relevant)}**",
        "",
    ]

    for action in relevant[:12]:
        detail = []
        approvals = _to_int(
            action.get("pending_approvals")
        )
        children = _to_int(
            action.get("hijos_abiertos")
        )

        if approvals:
            detail.append(
                f"Aprobaciones pendientes: {approvals}"
            )
        if children:
            detail.append(
                f"Subactividades abiertas: {children}"
            )

        lines.append(
            _action_line(action)
            + " · "
            + " · ".join(detail)
        )

    return "\n".join(lines)


def _summary_answer(
    actions: list[dict],
    *,
    title: str = "Resumen del alcance actual",
) -> str:
    if not actions:
        return "No encontré acciones para resumir."

    owners = Counter(
        action.get("asignado") or "Sin responsable"
        for action in actions
    )
    states = Counter(
        action.get("estado") or "Sin estado"
        for action in actions
    )
    overdue = [
        action for action in actions
        if action.get("is_overdue")
    ]
    stale = [
        action for action in actions
        if action.get("is_stale")
    ]
    approvals = sum(
        _to_int(action.get("pending_approvals"))
        for action in actions
    )
    children = sum(
        _to_int(action.get("hijos_abiertos"))
        for action in actions
    )

    lines = [
        f"**{title}**",
        "",
        f"- Acciones consideradas: {len(actions)}",
        f"- Vencidas: {len(overdue)}",
        f"- Sin actualización ≥7 días: {len(stale)}",
        f"- Aprobaciones pendientes: {approvals}",
        f"- Subactividades abiertas: {children}",
    ]

    if owners:
        lines.append(
            "- Mayor concentración por responsable: "
            + ", ".join(
                f"{owner} ({count})"
                for owner, count
                in owners.most_common(3)
            )
        )

    if states:
        lines.append(
            "- Estados: "
            + ", ".join(
                f"{state} ({count})"
                for state, count
                in states.most_common()
            )
        )

    if overdue:
        lines.extend([
            "",
            "**Vencidas principales**",
        ])
        ordered = sorted(
            overdue,
            key=lambda item: (
                item.get("days_overdue") or 0,
                item.get("days_since_update") or 0,
            ),
            reverse=True,
        )
        lines.extend(
            _action_line(action)
            for action in ordered[:5]
        )

    return "\n".join(lines)


def _top_n_answer(
    actions: list[dict],
    requested: int,
    *,
    ask_owner: bool,
) -> str:
    ordered = sorted(
        actions,
        key=lambda item: (
            item.get("days_overdue") or 0,
            item.get("days_since_update") or 0,
        ),
        reverse=True,
    )

    selected = ordered[:requested]

    if not selected:
        return "No encontré acciones para ese ranking."

    note = ""
    if len(selected) < requested:
        note = (
            f"Solo hay {len(selected)} acciones que cumplen "
            f"el criterio; no existen {requested}.\n\n"
        )

    if ask_owner:
        return (
            note
            + _owners_answer(
                f"Responsables de las {len(selected)} acciones seleccionadas",
                selected,
            )
        )

    return (
        note
        + _list_answer(
            f"{len(selected)} acciones principales",
            selected,
            "No encontré acciones.",
            limit=requested,
        )
    )


def _longest_without_update_answer(
    actions: list[dict],
) -> str:
    usable = [
        action
        for action in actions
        if action.get("days_since_update") is not None
    ]

    usable.sort(
        key=lambda item: (
            item.get("days_since_update") or 0
        ),
        reverse=True,
    )

    if not usable:
        return "No encontré información de actualización para esas acciones."

    lines = [
        "**Acciones con más tiempo sin update**",
        "",
    ]

    for action in usable[:10]:
        lines.append(
            _action_line(action)
            + f" · Tiempo sin update: "
            + str(action.get("days_since_update") or 0)
            + " días"
        )

    return "\n".join(lines)


def _scrap_reason(action: dict) -> str:
    reason = str(action.get("scrap_reason") or "").strip()
    if reason:
        return reason

    title = str(action.get("titulo") or "").strip()
    folded = title.casefold()

    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()

    if folded.startswith("scrap semanal"):
        return title[len("Scrap semanal"):].strip(" -")

    return title or "Sin razón"


def _scrap_recurrence_answer(
    actions: list[dict],
) -> str:
    scrap_actions = [
        action
        for action in actions
        if action.get("is_open")
    ]

    groups = defaultdict(list)

    for action in scrap_actions:
        reason = _scrap_reason(action)
        bu = (
            action.get("business_unit")
            or "Sin BU"
        )
        key = (
            _fold(reason),
            _fold(bu),
        )
        groups[key].append(action)

    repeated = [
        items
        for items in groups.values()
        if len(items) > 1
    ]
    repeated.sort(
        key=len,
        reverse=True,
    )

    if not repeated:
        return (
            "No encontré razones de Scrap repetidas dentro de la "
            "misma Business Unit en las acciones abiertas actuales."
        )

    lines = [
        f"**Recurrencias de Scrap detectadas: {len(repeated)}**",
        "",
    ]

    for items in repeated[:10]:
        first = items[0]
        reason = _scrap_reason(first)
        bu = first.get("business_unit") or "Sin BU"
        codes = ", ".join(
            str(item.get("codigo"))
            for item in items
            if item.get("codigo")
        )
        lines.append(
            f"- **{reason}** · BU: {bu} · "
            f"{len(items)} acciones · {codes}"
        )

    lines.extend([
        "",
        "La recurrencia anterior se basa únicamente en repetición "
        "de razón + BU; no implica una causa raíz confirmada.",
    ])

    return "\n".join(lines)


def _bottleneck_answer(data: dict) -> str:
    summary = data.get("summary") or {}
    signals = data.get("signals") or []

    lines = [
        "**Señales actuales de cuello de botella**",
        "",
        f"- Acciones abiertas: {_to_int(summary.get('open'))}",
        f"- Vencidas: {_to_int(summary.get('overdue'))}",
        f"- Estancadas: {_to_int(summary.get('stale'))}",
        (
            "- Aprobaciones pendientes: "
            + str(_to_int(summary.get("pending_approvals")))
        ),
    ]

    if signals:
        lines.extend(["", "**Señales detectadas**"])
        for name, count in signals:
            lines.append(
                f"- {str(name).replace('_', ' ').title()}: {count}"
            )

    top_overdue = data.get("top_overdue") or []
    if top_overdue:
        lines.extend([
            "",
            "**Vencidas principales**",
        ])
        lines.extend(
            _action_line(action)
            for action in top_overdue[:5]
        )

    return "\n".join(lines)


def _trends_answer(data: dict) -> str:
    lines = [
        f"**Tendencias de los últimos {_to_int(data.get('days'))} días**",
        "",
        f"- Acciones creadas: {_to_int(data.get('created'))}",
        f"- Acciones cerradas: {_to_int(data.get('closed'))}",
        f"- Eventos registrados: {_to_int(data.get('events'))}",
    ]

    weekly = data.get("weekly") or []
    if weekly:
        lines.extend([
            "",
            "**Semanas recientes**",
        ])
        for row in weekly[-6:]:
            lines.append(
                "- "
                + _value(row.get("week"))
                + ": "
                + f"creadas {_to_int(row.get('created'))}, "
                + f"cerradas {_to_int(row.get('closed'))}, "
                + f"updates {_to_int(row.get('updates'))}, "
                + f"cambios de fecha {_to_int(row.get('date_changes'))}"
            )

    return "\n".join(lines)


def _days_from_question(question: str) -> int:
    folded = _fold(question)

    if "3 meses" in folded or "90" in folded:
        return 90
    if "mes" in folded or "30" in folded:
        return 30
    if "semana" in folded or "7 " in folded:
        return 7

    return 90


async def _answer_npi_project(
    question: str,
    code: str,
) -> ActionTrackerChatResult:
    data = await action_tracker.get_npi(code)
    folded = _fold(question)

    asks_blocked = "bloquead" in folded
    asks_overdue = (
        "vencid" in folded
        or "atrasad" in folded
    )

    if asks_blocked and asks_overdue:
        return ActionTrackerChatResult(
            direct_answer=_npi_combined_blocked_overdue(
                data,
                code,
            ),
            mode="npi_blocked_overdue",
        )

    if asks_blocked:
        return ActionTrackerChatResult(
            direct_answer=_npi_items_answer(
                data,
                code,
                mode="blocked",
            ),
            mode="npi_blocked",
        )

    if asks_overdue:
        return ActionTrackerChatResult(
            direct_answer=_npi_items_answer(
                data,
                code,
                mode="overdue",
            ),
            mode="npi_overdue",
        )

    if (
        "responsable" in folded
        or "concentra" in folded
    ) and (
        "pendiente" in folded
        or "faltan" in folded
        or "actividades" in folded
    ):
        return ActionTrackerChatResult(
            direct_answer=_npi_owners_answer(
                data,
                code,
            ),
            mode="npi_owners",
        )

    if (
        "status" in folded
        or "resúm" in folded
        or "resum" in folded
    ):
        return ActionTrackerChatResult(
            direct_answer=_npi_status_answer(
                data,
                code,
            ),
            mode="npi_status",
        )

    if (
        "faltan" in folded
        or "pendiente" in folded
        or "actividades" in folded
    ):
        return ActionTrackerChatResult(
            direct_answer=_npi_items_answer(
                data,
                code,
                mode="pending",
            ),
            mode="npi_pending",
        )

    return ActionTrackerChatResult(
        direct_answer=_npi_status_answer(
            data,
            code,
        ),
        mode="npi_detail",
    )


async def build_action_tracker_result(
    question: str,
    history: list[dict] | None = None,
) -> ActionTrackerChatResult:
    if not action_tracker.configured:
        return ActionTrackerChatResult()

    if _is_conceptual(question):
        return ActionTrackerChatResult()

    project_code = _recent_project_code(
        question,
        history,
    )
    folded = _fold(question)

    try:
        if (
            project_code
            and (
                NPI_PROJECT_RE.search(question)
                or _is_followup(question)
                or "npi" in folded
                or "actividad" in folded
                or "pendiente" in folded
                or "bloquead" in folded
                or "vencid" in folded
                or "atrasad" in folded
            )
        ):
            return await _answer_npi_project(
                question,
                project_code,
            )

        if (
            "proyecto" in folded
            and "actividades atrasadas" in folded
            and (
                "más" in folded
                or "mas" in folded
            )
        ):
            projects = await action_tracker.list_npi_projects()
            candidates = [
                project
                for project in projects
                if _to_int(project.get("overdue_items")) > 0
            ]

            if not candidates:
                return ActionTrackerChatResult(
                    direct_answer=(
                        "No encontré proyectos NPI con "
                        "actividades atrasadas."
                    ),
                    mode="npi_most_overdue_project",
                )

            project = max(
                candidates,
                key=lambda item: _to_int(
                    item.get("overdue_items")
                ),
            )
            code = str(project.get("codigo") or "")
            data = await action_tracker.get_npi(code)

            return ActionTrackerChatResult(
                direct_answer=_npi_items_answer(
                    data,
                    code,
                    mode="overdue",
                ),
                mode="npi_most_overdue_project",
            )

        if (
            "npi" in folded
            and (
                "proyecto" in folded
                or "proyectos" in folded
            )
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

        code_match = ACTION_CODE_RE.search(question)
        if code_match:
            code = code_match.group(0).upper()

            if NPI_PROJECT_RE.fullmatch(code):
                return await _answer_npi_project(
                    question,
                    code,
                )

            detail = await action_tracker.get_action(code)
            return ActionTrackerChatResult(
                direct_answer=_detail_answer(
                    detail,
                    code,
                ),
                mode="action_detail",
            )

        if not _question_uses_action_tracker(
            question,
            history,
        ):
            return ActionTrackerChatResult()

        raw = await action_tracker.list_actions(
            open_only=False,
        )
        enriched = [
            enrich_action(action)
            for action in raw
        ]

        filters, domain = _combined_filters(
            question,
            history,
            enriched,
        )

        scoped = _domain_filter(
            enriched,
            domain,
        )

        if filters:
            scoped = apply_filters(
                scoped,
                filters,
            )

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
            scoped = apply_filters(
                scoped,
                {
                    "asignado":
                        settings.action_tracker_default_user
                },
            )

        open_scoped = [
            action
            for action in scoped
            if action.get("is_open")
        ]

        inherited_overdue = (
            _history_mentions_overdue(history)
            and _is_followup(question)
        )

        if (
            ("vence" in folded or "vencen" in folded)
            and "semana" in folded
            and "vencid" not in folded
        ):
            actions = select_enriched_actions(
                scoped,
                due_this_week=True,
            )
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones que vencen esta semana",
                    actions,
                    (
                        "No encontré acciones abiertas que "
                        "venzan esta semana."
                    ),
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
                scoped,
                auto_only=True,
                created_this_week=("semana" in folded),
                open_only=False,
            )
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones generadas automáticamente",
                    actions,
                    (
                        "No encontré acciones automáticas "
                        "para ese filtro."
                    ),
                ),
                mode="automatic_actions",
            )

        if (
            domain == "scrap"
            and (
                "repetid" in folded
                or "recurrencia" in folded
            )
        ):
            return ActionTrackerChatResult(
                direct_answer=_scrap_recurrence_answer(
                    scoped
                ),
                mode="scrap_recurrence",
            )

        if (
            "más tiempo sin update" in folded
            or "mas tiempo sin update" in folded
            or "más tiempo sin actualización" in folded
            or "mas tiempo sin actualizacion" in folded
        ):
            actions = open_scoped

            if inherited_overdue:
                actions = [
                    action
                    for action in actions
                    if action.get("is_overdue")
                ]

            return ActionTrackerChatResult(
                direct_answer=_longest_without_update_answer(
                    actions
                ),
                mode="longest_without_update",
            )

        if (
            "sin actualiz" in folded
            or "sin update" in folded
            or "estanc" in folded
        ) and "cuello" not in folded:
            actions = [
                action
                for action in open_scoped
                if action.get("is_stale")
            ]
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones sin actualización",
                    actions,
                    (
                        "No encontré acciones abiertas sin "
                        "actualización."
                    ),
                ),
                mode="stale_actions",
            )

        if "peor" in folded:
            requested_match = NUMBER_RE.search(question)
            requested = (
                int(requested_match.group(1))
                if requested_match
                else 5
            )

            actions = open_scoped
            if (
                inherited_overdue
                or "vencid" in folded
                or "atrasad" in folded
            ):
                actions = [
                    action
                    for action in actions
                    if action.get("is_overdue")
                ]

            return ActionTrackerChatResult(
                direct_answer=_top_n_answer(
                    actions,
                    requested,
                    ask_owner=(
                        "responsable" in folded
                        or "quién" in folded
                        or "quien" in folded
                    ),
                ),
                mode="top_n",
            )

        if (
            ("aprob" in folded and "subactiv" in folded)
            or (
                "alguna" in folded
                and (
                    "aprob" in folded
                    or "subactiv" in folded
                )
            )
        ):
            actions = open_scoped
            if inherited_overdue:
                actions = [
                    action
                    for action in actions
                    if action.get("is_overdue")
                ]

            return ActionTrackerChatResult(
                direct_answer=_scoped_issue_answer(
                    actions
                ),
                mode="scoped_dependencies",
            )

        if (
            "vencid" in folded
            or "atrasad" in folded
        ) and not any(
            term in folded
            for term in ("deten", "cuello")
        ):
            actions = [
                action
                for action in open_scoped
                if action.get("is_overdue")
            ]

            if "quien" in folded or "quién" in folded:
                answer = _owners_answer(
                    "Responsables con acciones vencidas",
                    actions,
                )
            else:
                answer = _list_answer(
                    "Acciones vencidas",
                    actions,
                    (
                        "No encontré acciones abiertas "
                        "vencidas para ese alcance."
                    ),
                )

            return ActionTrackerChatResult(
                direct_answer=answer,
                mode="overdue_actions",
            )

        if (
            "aprob" in folded
            and "subactiv" not in folded
            and not any(
                term in folded
                for term in BOTTLENECK_TERMS
            )
        ):
            approvals = await action_tracker.pending_approvals()

            allowed_codes = {
                action.get("codigo")
                for action in open_scoped
                if action.get("codigo")
            }

            if domain or filters:
                approvals = [
                    approval
                    for approval in approvals
                    if approval.get("codigo") in allowed_codes
                ]

            return ActionTrackerChatResult(
                direct_answer=_approval_answer(
                    approvals
                ),
                mode="pending_approvals",
            )

        if (
            "concentra" in folded
            and "pendiente" in folded
        ):
            return ActionTrackerChatResult(
                direct_answer=_owners_answer(
                    "Pendientes por responsable",
                    open_scoped,
                ),
                mode="pending_concentration",
            )

        if (
            "siguen abiertas" in folded
            or "siguen abierto" in folded
            or (
                "abiertas" in folded
                and _is_followup(question)
            )
        ):
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones abiertas",
                    open_scoped,
                    (
                        "No encontré acciones abiertas "
                        "para ese alcance."
                    ),
                ),
                mode="followup_open",
            )

        if any(
            term in folded
            for term in BOTTLENECK_TERMS
        ):
            data = await bottlenecks(
                stale_days=7,
                filters=filters,
            )

            if domain:
                # El analytics base no conoce dominios por prefijo,
                # por lo que se resume el mismo scope determinístico.
                return ActionTrackerChatResult(
                    direct_answer=_summary_answer(
                        open_scoped,
                        title=(
                            "Señales del alcance "
                            + domain.title()
                        ),
                    ),
                    mode="bottlenecks_scoped",
                )

            return ActionTrackerChatResult(
                direct_answer=_bottleneck_answer(
                    data
                ),
                mode="bottlenecks",
            )

        if any(
            term in folded
            for term in TREND_TERMS
        ):
            data = await trends(
                days=_days_from_question(question),
                filters=filters,
            )
            return ActionTrackerChatResult(
                direct_answer=_trends_answer(data),
                mode="trends",
            )

        if (
            "resúm" in folded
            or "resum" in folded
            or "status report" in folded
        ):
            actions = open_scoped

            if inherited_overdue:
                actions = [
                    action
                    for action in actions
                    if action.get("is_overdue")
                ]

            return ActionTrackerChatResult(
                direct_answer=_summary_answer(
                    actions,
                ),
                mode="scope_summary",
            )

        if (
            domain
            or filters
            or "acciones" in folded
            or "accion" in folded
            or "pendiente" in folded
        ):
            title = "Acciones abiertas"
            labels = []

            if domain:
                labels.append(domain.title())

            labels.extend(
                str(value)
                for value in filters.values()
                if value
            )

            if labels:
                title += " · " + " / ".join(
                    dict.fromkeys(labels)
                )

            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    title,
                    open_scoped,
                    (
                        "No encontré acciones abiertas "
                        "para ese filtro."
                    ),
                ),
                mode="filtered_actions",
            )

        payload = {
            "source": "Action Tracker live",
            "mode": "overview",
            "filters": filters,
            "domain": domain,
            "actions": [
                _compact_action(item)
                for item in open_scoped[:12]
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
        raise    try:
        explicit_code_match = ACTION_CODE_RE.search(question)

        if explicit_code_match:
            explicit_code = explicit_code_match.group(0).upper()

            if NPI_PROJECT_RE.fullmatch(explicit_code):
                return await _answer_npi_project(
                    question,
                    explicit_code,
                )

            detail = await action_tracker.get_action(
                explicit_code
            )
            return ActionTrackerChatResult(
                direct_answer=_detail_answer(
                    detail,
                    explicit_code,
                ),
                mode="action_detail",
            )

        if (
            "proyecto" in folded
            and "actividades atrasadas" in folded
            and (
                "más" in folded
                or "mas" in folded
            )
        ):
            projects = await action_tracker.list_npi_projects()
            candidates = [
                project
                for project in projects
                if _to_int(project.get("overdue_items")) > 0
            ]

            if not candidates:
                return ActionTrackerChatResult(
                    direct_answer=(
                        "No encontré proyectos NPI con "
                        "actividades atrasadas."
                    ),
                    mode="npi_most_overdue_project",
                )

            project = max(
                candidates,
                key=lambda item: _to_int(
                    item.get("overdue_items")
                ),
            )
            code = str(project.get("codigo") or "")
            data = await action_tracker.get_npi(code)

            return ActionTrackerChatResult(
                direct_answer=_npi_items_answer(
                    data,
                    code,
                    mode="overdue",
                ),
                mode="npi_most_overdue_project",
            )

        if (
            "npi" in folded
            and (
                "proyecto" in folded
                or "proyectos" in folded
            )
            and not _is_followup(question)
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

        if (
            project_code
            and (
                _is_followup(question)
                or "npi" in folded
                or "actividad" in folded
                or "pendiente" in folded
                or "bloquead" in folded
                or "vencid" in folded
                or "atrasad" in folded
            )
        ):
            return await _answer_npi_project(
                question,
                project_code,
            )

        raw = await action_tracker.list_actions(
            open_only=False,
        )
        enriched = [
            enrich_action(action)
            for action in raw
        ]

        filters, domain = _combined_filters(
            question,
            history,
            enriched,
        )

        scoped = _domain_filter(
            enriched,
            domain,
        )

        if filters:
            scoped = apply_filters(
                scoped,
                filters,
            )

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
            scoped = apply_filters(
                scoped,
                {
                    "asignado":
                        settings.action_tracker_default_user
                },
            )

        open_scoped = [
            action
            for action in scoped
            if action.get("is_open")
        ]

        inherited_overdue = (
            _history_mentions_overdue(history)
            and _is_followup(question)
        )

        if (
            ("vence" in folded or "vencen" in folded)
            and "semana" in folded
            and "vencid" not in folded
        ):
            actions = select_enriched_actions(
                scoped,
                due_this_week=True,
            )
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones que vencen esta semana",
                    actions,
                    (
                        "No encontré acciones abiertas que "
                        "venzan esta semana."
                    ),
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
                scoped,
                auto_only=True,
                created_this_week=("semana" in folded),
                open_only=False,
            )
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones generadas automáticamente",
                    actions,
                    (
                        "No encontré acciones automáticas "
                        "para ese filtro."
                    ),
                ),
                mode="automatic_actions",
            )

        if (
            domain == "scrap"
            and (
                "repetid" in folded
                or "recurrencia" in folded
            )
        ):
            return ActionTrackerChatResult(
                direct_answer=_scrap_recurrence_answer(
                    scoped
                ),
                mode="scrap_recurrence",
            )

        if (
            "más tiempo sin update" in folded
            or "mas tiempo sin update" in folded
            or "más tiempo sin actualización" in folded
            or "mas tiempo sin actualizacion" in folded
        ):
            actions = open_scoped

            if inherited_overdue:
                actions = [
                    action
                    for action in actions
                    if action.get("is_overdue")
                ]

            return ActionTrackerChatResult(
                direct_answer=_longest_without_update_answer(
                    actions
                ),
                mode="longest_without_update",
            )

        if (
            "sin actualiz" in folded
            or "sin update" in folded
            or "estanc" in folded
        ) and "cuello" not in folded:
            actions = [
                action
                for action in open_scoped
                if action.get("is_stale")
            ]
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones sin actualización",
                    actions,
                    (
                        "No encontré acciones abiertas sin "
                        "actualización."
                    ),
                ),
                mode="stale_actions",
            )

        if "peor" in folded:
            requested_match = NUMBER_RE.search(question)
            requested = (
                int(requested_match.group(1))
                if requested_match
                else 5
            )

            actions = open_scoped
            if (
                inherited_overdue
                or "vencid" in folded
                or "atrasad" in folded
            ):
                actions = [
                    action
                    for action in actions
                    if action.get("is_overdue")
                ]

            return ActionTrackerChatResult(
                direct_answer=_top_n_answer(
                    actions,
                    requested,
                    ask_owner=(
                        "responsable" in folded
                        or "quién" in folded
                        or "quien" in folded
                    ),
                ),
                mode="top_n",
            )

        if (
            ("aprob" in folded and "subactiv" in folded)
            or (
                "alguna" in folded
                and (
                    "aprob" in folded
                    or "subactiv" in folded
                )
            )
        ):
            actions = open_scoped
            if inherited_overdue:
                actions = [
                    action
                    for action in actions
                    if action.get("is_overdue")
                ]

            return ActionTrackerChatResult(
                direct_answer=_scoped_issue_answer(
                    actions
                ),
                mode="scoped_dependencies",
            )

        if (
            "vencid" in folded
            or "atrasad" in folded
        ) and not any(
            term in folded
            for term in ("deten", "cuello")
        ):
            actions = [
                action
                for action in open_scoped
                if action.get("is_overdue")
            ]

            if "quien" in folded or "quién" in folded:
                answer = _owners_answer(
                    "Responsables con acciones vencidas",
                    actions,
                )
            else:
                answer = _list_answer(
                    "Acciones vencidas",
                    actions,
                    (
                        "No encontré acciones abiertas "
                        "vencidas para ese alcance."
                    ),
                )

            return ActionTrackerChatResult(
                direct_answer=answer,
                mode="overdue_actions",
            )

        if (
            "aprob" in folded
            and "subactiv" not in folded
            and not any(
                term in folded
                for term in BOTTLENECK_TERMS
            )
        ):
            approvals = await action_tracker.pending_approvals()

            allowed_codes = {
                action.get("codigo")
                for action in open_scoped
                if action.get("codigo")
            }

            if domain or filters:
                approvals = [
                    approval
                    for approval in approvals
                    if approval.get("codigo") in allowed_codes
                ]

            return ActionTrackerChatResult(
                direct_answer=_approval_answer(
                    approvals
                ),
                mode="pending_approvals",
            )

        if (
            "concentra" in folded
            and "pendiente" in folded
        ):
            return ActionTrackerChatResult(
                direct_answer=_owners_answer(
                    "Pendientes por responsable",
                    open_scoped,
                ),
                mode="pending_concentration",
            )

        if (
            "siguen abiertas" in folded
            or "siguen abierto" in folded
            or (
                "abiertas" in folded
                and _is_followup(question)
            )
        ):
            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    "Acciones abiertas",
                    open_scoped,
                    (
                        "No encontré acciones abiertas "
                        "para ese alcance."
                    ),
                ),
                mode="followup_open",
            )

        if any(
            term in folded
            for term in BOTTLENECK_TERMS
        ):
            data = await bottlenecks(
                stale_days=7,
                filters=filters,
            )

            if domain:
                # El analytics base no conoce dominios por prefijo,
                # por lo que se resume el mismo scope determinístico.
                return ActionTrackerChatResult(
                    direct_answer=_summary_answer(
                        open_scoped,
                        title=(
                            "Señales del alcance "
                            + domain.title()
                        ),
                    ),
                    mode="bottlenecks_scoped",
                )

            return ActionTrackerChatResult(
                direct_answer=_bottleneck_answer(
                    data
                ),
                mode="bottlenecks",
            )

        if any(
            term in folded
            for term in TREND_TERMS
        ):
            data = await trends(
                days=_days_from_question(question),
                filters=filters,
            )
            return ActionTrackerChatResult(
                direct_answer=_trends_answer(data),
                mode="trends",
            )

        if (
            "resúm" in folded
            or "resum" in folded
            or "status report" in folded
        ):
            actions = open_scoped

            if inherited_overdue:
                actions = [
                    action
                    for action in actions
                    if action.get("is_overdue")
                ]

            return ActionTrackerChatResult(
                direct_answer=_summary_answer(
                    actions,
                ),
                mode="scope_summary",
            )

        if (
            domain
            or filters
            or "acciones" in folded
            or "accion" in folded
            or "pendiente" in folded
        ):
            title = "Acciones abiertas"
            labels = []

            if domain:
                labels.append(domain.title())

            labels.extend(
                str(value)
                for value in filters.values()
                if value
            )

            if labels:
                title += " · " + " / ".join(
                    dict.fromkeys(labels)
                )

            return ActionTrackerChatResult(
                direct_answer=_list_answer(
                    title,
                    open_scoped,
                    (
                        "No encontré acciones abiertas "
                        "para ese filtro."
                    ),
                ),
                mode="filtered_actions",
            )

        payload = {
            "source": "Action Tracker live",
            "mode": "overview",
            "filters": filters,
            "domain": domain,
            "actions": [
                _compact_action(item)
                for item in open_scoped[:12]
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
