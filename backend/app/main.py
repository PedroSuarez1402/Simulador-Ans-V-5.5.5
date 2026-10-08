"""Punto de Entrada Principal de la Aplicación FastAPI (Backend)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.api.v1.router import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Motor de API y Cálculos de Ingeniería para Radioenlaces (SAF Link Planner)",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configuración de CORS para permitir conexión desde Frontend (React, Vue, Vite, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar rutas V1
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Estado"])
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
    }


@app.get("/health", tags=["Estado"])
def health_check():
    return {"status": "healthy"}
