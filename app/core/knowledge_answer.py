import re
import unicodedata


LOOKUP_PREFIXES = (
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
    "qué quiere decir",
    "que quiere decir",
)

STOPWORDS = {
    "que", "qué", "como", "cómo", "cual", "cuál",
    "cuales", "cuáles", "para", "por", "una", "uno",
    "unos", "unas", "del", "las", "los", "con", "sin",
    "dentro", "debe", "ser", "esta", "este", "estos",
    "estas", "esto", "se", "en", "de", "la", "el", "y",
    "o", "es", "son", "un", "al", "lo", "su", "sus",
    "me", "mi", "hay", "más", "mas", "significa",
    "funciona", "decide", "evita", "explicame", "explícame",
}

SYNONYMS = {
    "costo": {"cost"},
    "costos": {"cost"},
    "piezas": {"pieces", "piece"},
    "pieza": {"piece", "pieces"},
    "roja": {"rojo", "rojos", "red"},
    "rojas": {"rojo", "rojos", "red"},
    "vencida": {"vencido", "vencidas", "overdue"},
    "vencidas": {"vencida", "vencido", "overdue"},
    "responsable": {"responsabilidad", "responsible"},
    "aprobador": {"aprobación", "aprobacion", "approver"},
    "duplicadas": {"duplicado", "duplicados"},
    "actualización": {"actualizacion", "update"},
    "actualizacion": {"actualización", "update"},
    "offender": {"offenders", "ofensor", "ofensores"},
    "offenders": {"offender", "ofensor", "ofensores"},
    "genera": {"generar", "generacion", "generación"},
    "targets": {"target", "meta", "metas"},
}


def _normalize(value: str) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )
    return text.casefold()


def _clean_question(question: str) -> str:
    return (
        str(question or "")
        .casefold()
        .strip()
        .lstrip("¿¡-*• ")
        .strip()
    )


def _terms(question: str) -> set[str]:
    words = {
        word.casefold()
        for word in re.findall(
            r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9_-]+",
            question,
        )
        if len(word) >= 3
        and word.casefold() not in STOPWORDS
    }

    expanded = set(words)

    for word in list(words):
        expanded.update(
            SYNONYMS.get(word, set())
        )

    return {
        _normalize(word)
        for word in expanded
    }


def is_knowledge_lookup(question: str) -> bool:
    folded = _clean_question(question)
    return any(
        folded.startswith(prefix)
        for prefix in LOOKUP_PREFIXES
    )


def _split_sections(content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []

    def flush() -> None:
        nonlocal body

        text = "\n".join(body).strip()

        if heading or text:
            sections.append(
                (
                    heading.strip(),
                    text,
                )
            )

        body = []

    for raw_line in str(content or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if re.match(r"^#{1,6}\s+", stripped):
            flush()
            heading = stripped
            continue

        if stripped:
            body.append(line)

    flush()
    return sections


def _intent_heading_hints(
    question: str,
) -> tuple[str, ...]:
    folded = _normalize(question)

    if (
        "scrap" in folded
        and any(
            token in folded
            for token in (
                "roja",
                "rojo",
                "rojas",
                "rojos",
                "red",
            )
        )
    ):
        return ("seleccion de offenders",)

    if (
        "offender" in folded
        and any(
            token in folded
            for token in (
                "genera",
                "generar",
                "decide",
            )
        )
    ):
        return ("seleccion de offenders",)

    if (
        "target" in folded
        or "meta" in folded
    ):
        return ("targets",)

    if (
        "accion" in folded
        and "vencid" in folded
    ):
        return ("accion vencida",)

    return ()


def _section_score(
    heading: str,
    body: str,
    terms: set[str],
    heading_hints: tuple[str, ...] = (),
) -> int:
    heading_text = _normalize(heading)
    body_text = _normalize(body)

    score = 0

    for hint in heading_hints:
        if hint in heading_text:
            score += 50

    for term in terms:
        if term in heading_text:
            score += 8

        if term in body_text:
            score += 3

        if len(term) >= 5:
            root = term[:5]

            if root in heading_text:
                score += 3

            if root in body_text:
                score += 1

    return score


def _section_text(
    heading: str,
    body: str,
) -> str:
    if heading and body:
        return heading + "\n\n" + body

    return heading or body


def build_knowledge_answer(
    question: str,
    sources: list[object],
) -> str:
    if not sources:
        return (
            "No encontré conocimiento guardado en este proyecto "
            "que pueda responder esa pregunta."
        )

    terms = _terms(question)
    heading_hints = _intent_heading_hints(
        question
    )
    candidates: list[tuple[int, int, str]] = []
    order = 0

    for source in sources:
        content = str(
            getattr(source, "content", "")
            or ""
        )

        for heading, body in _split_sections(content):
            score = _section_score(
                heading,
                body,
                terms,
                heading_hints,
            )

            if score <= 0:
                order += 1
                continue

            text = _section_text(
                heading,
                body,
            ).strip()

            if text:
                candidates.append(
                    (
                        score,
                        -order,
                        text,
                    )
                )

            order += 1

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )

    selected: list[str] = []

    if candidates:
        best_score, _order, best_text = candidates[0]

        if best_score >= 3:
            selected.append(best_text)

    if not selected:
        return (
            "No encontré una sección suficientemente relacionada "
            "en el conocimiento guardado del proyecto."
        )

    return (
        "**Según el conocimiento guardado del proyecto:**\n\n"
        + "\n\n".join(selected)
    )
