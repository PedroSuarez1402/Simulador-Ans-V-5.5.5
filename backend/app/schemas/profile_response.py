"""Esquemas DTO para respuestas de perfil topográfico y cálculos RF."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ProfilePointResponse(BaseModel):
    sample: int
    lat: float
    lon: float
    distance_km: float
    elevation_m: float
    los_m: Optional[float] = None
    los_worst_m: Optional[float] = None
    fresnel_upper_m: Optional[float] = None
    fresnel_lower_m: Optional[float] = None
    fresnel_60_m: Optional[float] = None
    canopy_height_m: Optional[float] = None
    canopy_top_m: Optional[float] = None
    vegetation_detected: bool = False
    status: Optional[str] = None


class ProfileSummaryResponse(BaseModel):
    distance_km: float
    azimuth_ab_deg: float
    azimuth_ba_deg: float
    fspl_db: float
    min_clearance_los_m: Optional[float] = None
    min_clearance_fresnel_m: Optional[float] = None
    is_line_of_sight_clear: bool = True
    total_samples: int
    elevation_provider: str
    points: List[ProfilePointResponse] = Field(default_factory=list)
