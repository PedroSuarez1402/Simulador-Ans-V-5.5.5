"""Enrutador Central de la API V1."""

from fastapi import APIRouter
from backend.app.api.v1.endpoints import catalog, projects, elevation

api_router = APIRouter()

api_router.include_router(catalog.router, prefix="/catalog", tags=["Catálogo de Equipos"])
api_router.include_router(projects.router, prefix="/projects", tags=["Proyectos"])
api_router.include_router(elevation.router, prefix="/elevation", tags=["Elevación y Terreno"])
