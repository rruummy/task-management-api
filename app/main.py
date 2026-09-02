import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.background.task_canceller import run_overdue_tasks_worker

# Configure application-level logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager:
    - Starts the periodic background worker on startup to check and cancel overdue tasks[cite: 1].
    - Gracefully stops and cancels the background task on application shutdown.
    """
    logger.info("Starting up background task workers...")
    worker_task = asyncio.create_task(run_overdue_tasks_worker())

    try:
        yield
    finally:
        logger.info("Shutting down background task workers...")
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            logger.info("Background task worker has been cleanly cancelled.")
        except Exception as exc:
            logger.error("Error encountered while stopping background worker: %s", exc)


app = FastAPI(
    title="Task Management API",
    version="1.0.0",
    description="REST API for task management with role workflows, comments, and background workers.",
    lifespan=lifespan,
)

# Register v1 API endpoints under /api/v1
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"], summary="Health check probe")
async def health_check() -> dict[str, str]:
    """Basic health check endpoint for container orchestrators and monitoring."""
    return {"status": "ok"}