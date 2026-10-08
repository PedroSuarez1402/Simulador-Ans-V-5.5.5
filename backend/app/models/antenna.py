"""Modelo de Datos para Antenas con SQLModel."""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class AntennaBase(SQLModel):
    manufacturer: str = Field(index=True, max_length=100, description="Fabricante")
    model: str = Field(index=True, unique=True, max_length=100, description="Modelo de antena")
    gain_dbi: float = Field(index=True, description="Ganancia nominal (dBi)")
    gain_low_dbi: Optional[float] = Field(default=None, description="Ganancia banda baja")
    gain_mid_dbi: Optional[float] = Field(default=None, description="Ganancia banda media")
    gain_high_dbi: Optional[float] = Field(default=None, description="Ganancia banda alta")
    frequency_min_ghz: Optional[float] = Field(default=None, description="Frecuencia mínima en GHz")
    frequency_max_ghz: Optional[float] = Field(default=None, description="Frecuencia máxima en GHz")
    beamwidth_deg: Optional[float] = Field(default=None, description="Ancho de haz a -3dB en grados")
    polarization: Optional[str] = Field(default=None, max_length=100, description="Polarización")
    front_to_back_ratio_db: Optional[float] = Field(default=None, description="Relación F/B (dB)")
    xpd_db: Optional[float] = Field(default=None, description="Discriminación XPD (dB)")
    diameter_m: Optional[float] = Field(default=None, description="Diámetro de parábola en metros")
    weight_kg: Optional[float] = Field(default=None, description="Peso neto (kg)")
    packed_weight_kg: Optional[float] = Field(default=None, description="Peso empaque (kg)")
    wind_area_m2: Optional[float] = Field(default=None, description="Área de viento (m²)")
    operational_wind_kmh: Optional[float] = Field(default=None, description="Viento operacional (km/h)")
    survival_wind_kmh: Optional[float] = Field(default=None, description="Viento supervivencia (km/h)")
    vswr: Optional[str] = Field(default=None, max_length=50, description="VSWR")
    port_isolation_db: Optional[float] = Field(default=None, description="Aislamiento entre puertos (dB)")
    connector: Optional[str] = Field(default=None, max_length=100, description="Tipo de conector")
    shielding: Optional[str] = Field(default=None, max_length=100, description="Blindaje / Radomo")
    material: Optional[str] = Field(default=None, max_length=100, description="Material")
    mast_mount: Optional[str] = Field(default=None, max_length=150, description="Soporte de mástil")
    elevation_adjustment: Optional[str] = Field(default=None, max_length=100, description="Ajuste elevación")
    azimuth_adjustment: Optional[str] = Field(default=None, max_length=100, description="Ajuste azimut")
    polarization_adjustment: Optional[str] = Field(default=None, max_length=100, description="Ajuste polarización")
    dimension_a_mm: Optional[float] = Field(default=None)
    dimension_b_mm: Optional[float] = Field(default=None)
    dimension_c_mm: Optional[float] = Field(default=None)
    source_file: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = Field(default=None)


class Antenna(AntennaBase, table=True):
    __tablename__ = "antennas"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
