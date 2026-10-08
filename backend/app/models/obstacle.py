"""Modelo de Datos para Obstáculos Manuales con SQLModel."""

from typing import Optional, TYPE_CHECKING
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from backend.app.models.project import Project


class ObstacleBase(SQLModel):
    dist_km: float = Field(description="Distancia desde Sitio A en km")
    height_m: float = Field(description="Altura del obstáculo sobre el terreno en metros")
    tipo: str = Field(default="Árbol", max_length=50, description="Tipo de obstáculo")
    nombre: str = Field(default="Obstáculo", max_length=100, description="Nombre identificador")
    activo: bool = Field(default=True, description="Si está activo en el cálculo de despeje")


class ProjectObstacle(ObstacleBase, table=True):
    __tablename__ = "project_obstacles"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relación inversa al proyecto
    project: Optional["Project"] = Relationship(back_populates="obstacles")
