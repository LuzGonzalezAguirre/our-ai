from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.core.config import settings
from app.db.database import (
    check_database,
    close_database,
    init_database,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_database()
        app.state.database_startup_error = None
    except Exception as exc:
        app.state.database_startup_error = str(exc)

    yield

    await close_database()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Self-hosted AI Core API",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


@app.get(
    "/",
    include_in_schema=False,
)
async def web_chat():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    database_ok, database_error = await check_database()

    return {
        "status": "ok" if database_ok else "degraded",
        "model": settings.ollama_model,
        "provider": "ollama",
        "database": (
            "connected"
            if database_ok
            else "disconnected"
        ),
        "database_error": database_error,
    }


app.include_router(chat_router)
