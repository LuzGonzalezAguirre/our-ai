import httpx

from app.core.config import settings


class OllamaEmbeddingProvider:
    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_embedding_model

    async def embed(
        self,
        texts: str | list[str],
    ) -> list[list[float]]:
        payload = {
            "model": self.model,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json=payload,
                )
                response.raise_for_status()

        except httpx.ConnectError as exc:
            raise RuntimeError(
                "No se pudo conectar con Ollama para generar embeddings."
            ) from exc

        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            raise RuntimeError(
                "Ollama no pudo generar embeddings. "
                f"Modelo: {self.model}. Detalle: {detail}"
            ) from exc

        data = response.json()
        embeddings = data.get("embeddings")

        if not embeddings:
            raise RuntimeError(
                "Ollama respondió sin embeddings."
            )

        return embeddings


embedding_provider = OllamaEmbeddingProvider()
