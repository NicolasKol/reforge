"""
Reforge API - Main Application
Unified FastAPI interface for the entire reverse engineering pipeline.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import builder, data, ghidra, join, join_ghidra, llm, llm_data, oracle, oracle_ts, results

_log = logging.getLogger(__name__)


# =============================================================================
# Lifespan Event Handler
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events"""
    # Startup: Initialize connections
    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    yield
    # Shutdown: Cleanup connections
    # TODO: Close database connections
    # TODO: Close Redis connections


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title=settings.API_TITLE,
    description="Unified API for reverse engineering pipeline: Build → Decompile → Analyze",
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return 422 with structured error details."""
    body = await request.body()
    _log.warning(
        "422 on %s %s  body[:200]=%s  errors=%s",
        request.method, request.url.path, body[:200], exc.errors()[:3],
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "reforge-api",
        "version": settings.API_VERSION
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Reforge API - Reverse Engineering Pipeline",
        "docs": "/docs",
        "health": "/health"
    }


# =============================================================================
# Register Routers
# =============================================================================

app.include_router(builder.router, prefix="/builder", tags=["builder"])
app.include_router(data.router, prefix="/data", tags=["data"])
app.include_router(ghidra.router, prefix="/ghidra", tags=["ghidra"])
app.include_router(llm.router, prefix="/llm-legacy", tags=["llm (deprecated)"])
app.include_router(llm_data.router, prefix="/llm", tags=["llm-data"])
app.include_router(oracle.router, prefix="/oracle", tags=["oracle"])
app.include_router(oracle_ts.router, prefix="/oracle-ts", tags=["oracle-ts"])
app.include_router(join.router, prefix="/join", tags=["join"])
app.include_router(join_ghidra.router, prefix="/join-ghidra", tags=["join-ghidra"])
app.include_router(results.router, prefix="/results", tags=["results"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True  # For development
    )
