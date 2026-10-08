"""Modelo de Datos para Radios con SQLModel."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class RadioBase(SQLModel):
    manufacturer: str = Field(index=True, max_length=100, description="Fabricante del equipo")
    model: str = Field(index=True, unique=True, max_length=100, description="Modelo del radio")
    frequency_min_ghz: Optional[float] = Field(default=None, description="Frecuencia mínima en GHz")
    frequency_max_ghz: Optional[float] = Field(default=None, description="Frecuencia máxima en GHz")
    max_output_power_dbm: Optional[float] = Field(default=None, description="Potencia TX máxima (dBm)")
    integrated_antenna_gain_dbi: Optional[float] = Field(default=0.0, description="Ganancia de antena integrada si tiene (dBi)")
    throughput_gbps: Optional[float] = Field(default=None, description="Throughput máximo (Gbps)")
    bandwidths_mhz: Optional[List[int]] = Field(default=None, sa_column=Column(JSON), description="Canalizaciones soportadas en MHz")
    mimo: Optional[str] = Field(default=None, max_length=50, description="Esquema MIMO (2x2, 4x4, etc.)")
    modulation: Optional[str] = Field(default=None, max_length=100, description="Modulación máxima")
    rx_sensitivity_dbm: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON), description="Sensibilidad RX por canal")
    source_file: Optional[str] = Field(default=None, max_length=255, description="Nombre de archivo datasheet")
    notes: Optional[str] = Field(default=None, description="Notas técnicas")


class Radio(RadioBase, table=True):
    __tablename__ = "radios"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
