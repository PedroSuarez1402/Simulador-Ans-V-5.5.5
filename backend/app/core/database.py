"""Conexión, motor y sesiones de base de datos con SQLModel."""

from typing import Generator
from sqlmodel import SQLModel, create_engine, Session
from backend.app.core.config import settings

# Engine configurado para MySQL / MariaDB o SQLite
engine = create_engine(
    settings.get_database_url(),
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)


def get_session() -> Generator[Session, None, None]:
    """Generador de sesiones para inyección de dependencias en endpoints FastAPI."""
    with Session(engine) as session:
        yield session


def init_db() -> None:
    """Crea las tablas directamente mediante metadata si no se usa Alembic."""
    SQLModel.metadata.create_all(engine)
