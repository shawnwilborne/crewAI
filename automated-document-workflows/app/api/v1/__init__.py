"""
Version 1 API endpoints.
"""

from fastapi import APIRouter

from .documents import router as documents_router
from .jobs import router as jobs_router
from .outputs import router as outputs_router
from .connectors import router as connectors_router
from .baas import router as baas_router
from .routing import router as routing_router

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(outputs_router, prefix="/outputs", tags=["outputs"])
api_router.include_router(connectors_router, prefix="/connectors", tags=["connectors"])
api_router.include_router(baas_router, prefix="/baas", tags=["baas"])
api_router.include_router(routing_router, prefix="/routing", tags=["routing"])