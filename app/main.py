"""
Reforge API - Main Application
Unified FastAPI interface for the entire reverse engineering pipeline.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import builder, ghidra, llm, oracle


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

# CORS middleware for n8n integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(ghidra.router, prefix="/ghidra", tags=["ghidra"])
app.include_router(llm.router, prefix="/llm", tags=["llm"])
app.include_router(oracle.router, prefix="/oracle", tags=["oracle"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True  # For development
    )
