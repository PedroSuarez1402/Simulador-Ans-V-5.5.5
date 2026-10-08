"""Servicio de Cálculos Geodésicos, Curvatura Terrestre y Radiofrecuencia (RF).
Lógica de negocio pura e independiente del framework web.
"""

import math
import numpy as np
import pandas as pd
from backend.app.core.constants import EARTH_RADIUS_KM


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia geodésica del gran círculo entre dos puntos en kilómetros."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula el azimut inicial (ángulo en grados 0-360) de A hacia B."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def fspl_km_ghz(distance_km: float, freq_ghz: float) -> float:
    """Pérdida en el espacio libre (Free Space Path Loss) en dB."""
    return 92.45 + 20 * math.log10(max(distance_km, 0.001)) + 20 * math.log10(max(freq_ghz, 0.1))


def fresnel_radius_m(d1_km: float, d2_km: float, freq_ghz: float) -> float:
    """Calcula el radio de la primera zona de Fresnel (F1) en metros."""
    d_total = d1_km + d2_km
    if d_total <= 0:
        return 0.0
    return 17.32 * math.sqrt((d1_km * d2_km) / (max(freq_ghz, 0.1) * d_total))


def curvature_bulge_m(d1_km: float, d2_km: float, k: float = 1.333) -> float:
    """Calcula la elevación aparente del terreno por curvatura terrestre y refracción K (m)."""
    r_eff = EARTH_RADIUS_KM * k
    return (d1_km * d2_km) / (2 * r_eff) * 1000.0


def calculate_link_geometry(
    df: pd.DataFrame,
    height_a: float,
    height_b: float,
    distance_km: float,
    freq_ghz: float,
    k_factor: float = 1.333,
) -> pd.DataFrame:
    """Calcula la línea de vista (LOS), zona de Fresnel y curvatura terrestre para cada punto del perfil."""
    out = df.copy()
    terrain = out["elevation_m"].to_numpy(dtype=float)
    x = out["distance_km"].to_numpy(dtype=float)

    endpoint_a = terrain[0] + height_a
    endpoint_b = terrain[-1] + height_b
    n_points = len(x)

    # Línea de vista recta geométrica
    los_straight = np.linspace(endpoint_a, endpoint_b, n_points)

    # Curvatura terrestre para factor K estándar (1.333) y peor caso K (ej. 0.667)
    d1 = x
    d2 = np.maximum(distance_km - x, 0.0)

    bulge_k = (d1 * d2) / (2 * EARTH_RADIUS_KM * k_factor) * 1000.0
    bulge_worst = (d1 * d2) / (2 * EARTH_RADIUS_KM * min(k_factor, 0.667)) * 1000.0

    # Línea de vista efectiva ajustada
    out["los_m"] = los_straight - bulge_k
    out["los_worst_m"] = los_straight - bulge_worst

    # Radio de primera zona de Fresnel
    with np.errstate(divide="ignore", invalid="ignore"):
        d_total = np.maximum(distance_km, 1e-6)
        f1 = 17.32 * np.sqrt(np.maximum(d1 * d2, 0.0) / (max(freq_ghz, 0.1) * d_total))
        f1 = np.nan_to_num(f1, nan=0.0)

    out["f1_radius_m"] = f1
    out["fresnel_60_m"] = 0.60 * f1
    out["fresnel_upper_m"] = out["los_m"] + out["fresnel_60_m"]
    out["fresnel_lower_m"] = out["los_m"] - out["fresnel_60_m"]
    out["clearance_terrain_m"] = out["los_worst_m"] - terrain

    return out
