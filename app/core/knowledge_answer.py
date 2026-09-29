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
)

STOPWORDS = {
    "que", "qué", "como", "cómo", "cual", "cuál", "cuales",
    "cuáles", "para", "por", "una", "uno", "unos", "unas",
    "del", "las", "los", "con", "sin", "dentro", "debe", "ser",
    "esta", "este", "estos", "estas", "esto", "se", "en", "de",
    "la", "el", "y", "o", "es", "son", "un", "al", "lo", "su",
    "sus", "me", "mi", "hay", "más", "mas",
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


def _terms(question: str) -> set[str]:
    words = {
        word
        for word in re.findall(
            r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9_-]+",
            question,
        )
        if len(word) >= 3
        and word.casefold() not in STOPWORDS
    }

    expanded = set(words)

    for word in list(words):
        for synonym in SYNONYMS.get(
            word.casefold(),
            set(),
        ):
            expanded.add(synonym)

    return {
        _normalize(word)
        for word in expanded
    }


def is_knowledge_lookup(question: str) -> bool:
    folded = str(question or "").casefold().strip()
    return any(
        folded.startswith(prefix)
        for prefix in LOOKUP_PREFIXES
    )


def _score_line(
    line: str,
    terms: set[str],
) -> int:
    normalized = _normalize(line)

    score = 0
    for term in terms:
        if term in normalized:
            score += 2

        if len(term) >= 5:
            root = term[:5]
            if root in normalized:
                score += 1

    if line.lstrip().startswith(("-", "*")):
        score += 1

    return score


def build_knowledge_answer(
    question: str,
    chunks: list[tuple[object, float]],
) -> str:
    if not chunks:
        return (
            "No encontré conocimiento guardado en este proyecto "
            "que pueda responder esa pregunta."
        )

    terms = _terms(question)
    candidates: list[tuple[int, int, str]] = []
    fallback_lines: list[str] = []

    for chunk_index, (chunk, _score) in enumerate(chunks):
        content = str(getattr(chunk, "content", "") or "")
        lines = [
            line.rstrip()
            for line in content.splitlines()
            if line.strip()
        ]

        fallback_lines.extend(lines)

        current_heading = ""

        for line_index, line in enumerate(lines):
            stripped = line.strip()

            if stripped.startswith("#"):
                current_heading = stripped
                continue

            score = _score_line(
                stripped,
                terms,
            )

            if score <= 0:
                continue

            text = stripped

            if current_heading:
                text = current_heading + "\n" + text

            candidates.append(
                (
                    score,
                    -(chunk_index * 1000 + line_index),
                    text,
                )
            )

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )

    selected: list[str] = []
    seen = set()
    total_chars = 0

    for _score, _order, text in candidates:
        key = _normalize(text)

        if key in seen:
            continue

        if total_chars + len(text) > 1400:
            continue

        seen.add(key)
        selected.append(text)
        total_chars += len(text)

        if len(selected) >= 8:
            break

    if not selected:
        selected = []
        total_chars = 0

        for line in fallback_lines:
            if total_chars + len(line) > 1200:
                break
            selected.append(line)
            total_chars += len(line)

    if not selected:
        return (
            "Encontré una fuente relacionada, pero no pude extraer "
            "contenido textual suficiente para responder."
        )

    return (
        "**Según el conocimiento guardado del proyecto:**\n\n"
        + "\n".join(selected)
    )
