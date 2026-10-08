"""Esquemas DTO (Data Transfer Objects) para solicitudes de cálculo de enlace."""

from typing import Optional
from pydantic import BaseModel, Field


class LinkCoordinatesRequest(BaseModel):
    name_a: str = Field(default="Sitio A", description="Nombre del Sitio A")
    lat_a: float = Field(..., description="Latitud Sitio A (-90 a 90)")
    lon_a: float = Field(..., description="Longitud Sitio A (-180 a 180)")
    height_a: float = Field(default=20.0, ge=0.0, le=500.0, description="Altura antena sobre terreno A (m)")

    name_b: str = Field(default="Sitio B", description="Nombre del Sitio B")
    lat_b: float = Field(..., description="Latitud Sitio B (-90 a 90)")
    lon_b: float = Field(..., description="Longitud Sitio B (-180 a 180)")
    height_b: float = Field(default=20.0, ge=0.0, le=500.0, description="Altura antena sobre terreno B (m)")

    frequency_ghz: float = Field(default=5.8, ge=0.1, le=100.0, description="Frecuencia central en GHz")
    k_factor: float = Field(default=1.333, ge=0.5, le=3.0, description="Factor refractivo K")
    samples: int = Field(default=512, ge=50, le=1024, description="Número de puntos a muestrear")


class ProfileRequest(LinkCoordinatesRequest):
    elevation_provider: str = Field(
        default="Open-Meteo",
        description="Proveedor de elevación: 'Open-Meteo' o 'Google'"
    )
    apply_smoothing: bool = Field(
        default=True,
        description="Aplica reconstrucción continua sub-píxel en Open-Meteo"
    )
