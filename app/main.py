import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.action_tracker import router as action_tracker_router
from app.api.chat import router as chat_router
from app.api.knowledge import router as knowledge_router
from app.api.projects import router as projects_router
from app.connectors.action_tracker import action_tracker
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

    warm_task = None

    if action_tracker.configured:
        warm_task = asyncio.create_task(
            action_tracker.warm_cache()
        )

    yield

    if warm_task and not warm_task.done():
        warm_task.cancel()
        with suppress(asyncio.CancelledError):
            await warm_task

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
        "embedding_model": settings.ollama_embedding_model,
        "provider": "ollama",
        "database": (
            "connected"
            if database_ok
            else "disconnected"
        ),
        "database_error": database_error,
        "action_tracker": (
            "configured"
            if (
                settings.action_tracker_enabled
                and settings.action_tracker_token
            )
            else "disabled"
        ),
    }


app.include_router(chat_router)
app.include_router(projects_router)
app.include_router(knowledge_router)
app.include_router(action_tracker_router)
