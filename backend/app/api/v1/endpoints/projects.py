"""Endpoints REST para administración de Proyectos con SQLModel."""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.app.core.database import get_session
from backend.app.models.project import Project, ProjectBase, ProjectLink, ProjectRFSettings
from backend.app.models.obstacle import ProjectObstacle

router = APIRouter()


@router.get("/", response_model=List[Project], summary="Listar todos los proyectos")
def list_projects(session: Session = Depends(get_session)):
    statement = select(Project).order_by(Project.updated_at.desc())
    return session.exec(statement).all()


@router.get("/{project_id}", summary="Obtener proyecto completo con enlace y equipos")
def get_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "version": project.version,
        "elevation_provider": project.elevation_provider,
        "link": project.link,
        "rf_settings": project.rf_settings,
        "obstacles": project.obstacles,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar proyecto")
def delete_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")

    session.delete(project)
    session.commit()
    return None
