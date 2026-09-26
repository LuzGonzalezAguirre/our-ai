from abc import ABC, abstractmethod


class ModelProvider(ABC):

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """
        Envía una conversación completa al modelo
        y devuelve el texto generado.
        """
        raise NotImplementedError
