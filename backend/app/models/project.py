"""Modelos de Datos para Proyectos, Enlaces y Parámetros RF con SQLModel."""

from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON, Text
from sqlalchemy.dialects.mysql import LONGTEXT

if TYPE_CHECKING:
    from backend.app.models.obstacle import ProjectObstacle


class ProjectBase(SQLModel):
    name: str = Field(index=True, unique=True, max_length=150, description="Nombre único del proyecto")
    description: Optional[str] = Field(default=None, description="Descripción del proyecto")
    format: str = Field(default="SAF-Link-Planner-Project", max_length=50)
    version: str = Field(default="V5.5.5", max_length=20)
    elevation_provider: str = Field(default="Open-Meteo (Gratuito / Copernicus DEM)", max_length=100)
    ee_project: str = Field(default="saf-link-planner", max_length=100)


class Project(ProjectBase, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relaciones relacionales
    link: Optional["ProjectLink"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
    rf_settings: Optional["ProjectRFSettings"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
    profile: Optional["ProjectProfile"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
    obstacles: List["ProjectObstacle"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class ProjectLink(SQLModel, table=True):
    __tablename__ = "project_links"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", unique=True, index=True, ondelete="CASCADE")
    site_a_name: str = Field(default="Sitio A", max_length=100)
    lat_a: float = Field(description="Latitud Sitio A")
    lon_a: float = Field(description="Longitud Sitio A")
    height_a_m: float = Field(default=20.0, description="Altura antena sobre terreno A (m)")
    site_b_name: str = Field(default="Sitio B", max_length=100)
    lat_b: float = Field(description="Latitud Sitio B")
    lon_b: float = Field(description="Longitud Sitio B")
    height_b_m: float = Field(default=20.0, description="Altura antena sobre terreno B (m)")
    distance_km: Optional[float] = Field(default=None, description="Distancia geodésica calculada (km)")
    azimuth_ab_deg: Optional[float] = Field(default=None, description="Azimut A -> B")
    azimuth_ba_deg: Optional[float] = Field(default=None, description="Azimut B -> A")

    project: Optional[Project] = Relationship(back_populates="link")


class ProjectRFSettings(SQLModel, table=True):
    __tablename__ = "project_rf_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", unique=True, index=True, ondelete="CASCADE")
    radio_a_id: Optional[int] = Field(default=None, foreign_key="radios.id", ondelete="SET NULL")
    radio_b_id: Optional[int] = Field(default=None, foreign_key="radios.id", ondelete="SET NULL")
    antenna_a_id: Optional[int] = Field(default=None, foreign_key="antennas.id", ondelete="SET NULL")
    antenna_b_id: Optional[int] = Field(default=None, foreign_key="antennas.id", ondelete="SET NULL")
    frequency_ghz: float = Field(default=5.800, description="Frecuencia central (GHz)")
    tx_power_dbm: float = Field(default=24.0, description="Potencia de transmisión TX (dBm)")
    channel_mhz: int = Field(default=80, description="Ancho de canal (MHz)")
    required_capacity_mbps: float = Field(default=500.0, description="Capacidad requerida (Mbps)")
    other_losses_db: float = Field(default=2.0, description="Otras pérdidas adicionales (dB)")
    k_factor: float = Field(default=1.333, description="Factor K refractivo")

    project: Optional[Project] = Relationship(back_populates="rf_settings")


class ProjectProfile(SQLModel, table=True):
    __tablename__ = "project_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", unique=True, index=True, ondelete="CASCADE")
    samples_count: int = Field(default=512)
    profile_df_json: Optional[str] = Field(default=None, sa_column=Column(Text().with_variant(LONGTEXT, "mysql")))
    veg_df_json: Optional[str] = Field(default=None, sa_column=Column(Text().with_variant(LONGTEXT, "mysql")))
    exclusions_json: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    canopy_overrides_json: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    calculated_at: datetime = Field(default_factory=datetime.utcnow)

    project: Optional[Project] = Relationship(back_populates="profile")
