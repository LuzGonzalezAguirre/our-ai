from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Self-hosted AI Core API",
)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": settings.ollama_model,
        "provider": "ollama",
    }


app.include_router(chat_router)
