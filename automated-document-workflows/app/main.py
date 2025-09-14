"""
FastAPI application factory and main entry point.
"""

import os
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.settings import settings
from app.db.database import create_tables
from app.api.v1 import api_router
from app.utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    setup_logging()
    logging.info("Starting Automated Document Workflows API")
    
    # Create database tables
    create_tables()
    
    # Ensure directories exist
    os.makedirs(settings.temp_upload_dir, exist_ok=True)
    os.makedirs(settings.output_dir, exist_ok=True)
    os.makedirs(settings.quarantine_dir, exist_ok=True)
    
    logging.info("Application startup complete")
    
    yield
    
    # Shutdown
    logging.info("Application shutting down")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title="Automated Document Workflows",
        description="Production-ready document processing, conversion, and routing system",
        version=settings.version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )
    
    # Add middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # Include routers
    app.include_router(api_router, prefix="/api/v1")
    
    # Static files (for serving outputs)
    if os.path.exists(settings.output_dir):
        app.mount("/outputs", StaticFiles(directory=settings.output_dir), name="outputs")
    
    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.version,
            "environment": settings.environment,
            "baas_enabled": settings.baas_enabled,
        }
    
    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint with API information."""
        return {
            "app": "Automated Document Workflows",
            "version": settings.version,
            "docs": "/docs" if settings.debug else "Documentation disabled in production",
            "health": "/health",
            "api": "/api/v1",
        }
    
    # Global exception handler
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Global HTTP exception handler."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "message": exc.detail,
                "status_code": exc.status_code,
                "path": str(request.url.path),
            }
        )
    
    # Global error handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler for unhandled errors."""
        logging.error(f"Unhandled error: {exc}", exc_info=True)
        
        if settings.debug:
            return JSONResponse(
                status_code=500,
                content={
                    "error": True,
                    "message": str(exc),
                    "type": type(exc).__name__,
                    "path": str(request.url.path),
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": True,
                    "message": "Internal server error",
                    "path": str(request.url.path),
                }
            )
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    """Run the application directly."""
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        workers=1,  # Use 1 worker for development
        log_level=settings.log_level.lower(),
        access_log=True,
    )