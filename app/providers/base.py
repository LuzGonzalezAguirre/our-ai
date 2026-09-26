from abc import ABC, abstractmethod


class ModelProvider(ABC):

    @abstractmethod
    async def chat(
        self,
        message: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Envía un mensaje al modelo y devuelve solamente
        el texto generado.
        """
        raise NotImplementedError
