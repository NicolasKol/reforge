"""FastAPI application factory for the Assemblage Bridge."""

from fastapi import FastAPI

from .config import Settings
from .lifecycle import build_lifespan
from .routers import builds, health, debug


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        title="Assemblage Bridge",
        description="HTTP API bridge between n8n and Assemblage build system",
        version="0.0.1",
        lifespan=build_lifespan(settings),
    )

    app.include_router(health.router)
    app.include_router(builds.router)
    app.include_router(debug.router)

    return app
