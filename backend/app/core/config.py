"""Configuración Central del Sistema (Capa Core).
Utiliza Pydantic Settings para cargar variables de entorno y proveer valores por defecto robustos.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SAF Link Planner API"
    VERSION: str = "V5.5.5"
    API_V1_STR: str = "/api/v1"

    # Configuración de Base de Datos
    DB_DRIVER: str = "mysql+pymysql"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "Dios2024"
    DB_NAME: str = "saf_link_planner"
    DATABASE_URL: Optional[str] = None

    # Google Earth Engine / Elevation
    EE_PROJECT: str = "saf-link-planner"
    GOOGLE_MAPS_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"{self.DB_DRIVER}://{self.DB_USER}:{self.DB_PASSWORD}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )


settings = Settings()
