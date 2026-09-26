from collections import defaultdict


class ConversationStore:
    """
    Almacenamiento temporal de conversaciones en memoria.

    Más adelante esta implementación podrá reemplazarse
    por PostgreSQL sin cambiar la API pública.
    """

    def __init__(self) -> None:
        self._conversations: dict[str, list[dict[str, str]]] = defaultdict(list)

    def get_messages(
        self,
        conversation_id: str,
    ) -> list[dict[str, str]]:
        return self._conversations[conversation_id].copy()

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        self._conversations[conversation_id].append(
            {
                "role": role,
                "content": content,
            }
        )

    def clear(
        self,
        conversation_id: str,
    ) -> None:
        self._conversations.pop(conversation_id, None)


conversation_store = ConversationStore()
