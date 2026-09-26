import httpx

from app.core.config import settings
from app.providers.base import ModelProvider


class OllamaProvider(ModelProvider):

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    async def chat(
        self,
        message: str,
        system_prompt: str | None = None,
    ) -> str:

        messages = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": message,
            }
        )

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": settings.ollama_think,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
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
