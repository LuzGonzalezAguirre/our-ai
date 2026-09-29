import httpx

from app.core.config import settings
from app.providers.base import ModelProvider


class OllamaProvider(ModelProvider):

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    async def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": settings.ollama_think,
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "num_predict": settings.ollama_num_predict,
                "num_ctx": settings.ollama_num_ctx,
            },
        }

        try:
            async with httpx.AsyncClient(
                timeout=settings.ollama_timeout_seconds
            ) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()

        except httpx.ConnectError as exc:
            raise RuntimeError(
                "No se pudo conectar con Ollama. "
                "Verifica que Ollama esté ejecutándose."
            ) from exc

        except httpx.TimeoutException as exc:
            raise RuntimeError(
                "Ollama tardó demasiado en responder. "
                "La consulta excedió el tiempo máximo del modelo local."
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama respondió con error "
                f"{exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc

        data = response.json()

        try:
            return data["message"]["content"]

        except KeyError as exc:
            raise RuntimeError(
                f"Respuesta inesperada de Ollama: {data}"
            ) from exc
