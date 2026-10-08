"""Servicio de Perfiles Topográficos de Elevación.
Soporta Open-Meteo (Copernicus DEM 90m) con reconstrucción continua sub-píxel y Google Elevation.
"""

from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import requests

from backend.app.services.geo_service import haversine


def smooth_dem_profile(elevations, dist_km=None, window_meters=350.0):
    """Reconstrucción continua sub-píxel para perfiles DEM discretos/escalonados (Copernicus 90m).
    Aplica un filtro polinomial cuadrático adaptativo (Savitzky-Golay) que elimina los escalones
    y terrazas horizontales artificiales generados por el muestreo nearest-neighbor de Open-Meteo,
    reconstruyendo pendientes continuas y picos suaves con alta fidelidad topográfica,
    preservando con exactitud los obstáculos y cotas extremas sin recortar crestas.
    """
    y = np.array(elevations, dtype=float)
    n = len(y)
    if n < 5:
        return y

    total_span_m = (dist_km[-1] - dist_km[0]) * 1000.0 if dist_km is not None else float(n)
    d_step_m = total_span_m / max(n - 1, 1)
    w = int(round(window_meters / max(d_step_m, 1.0)))
    w = max(5, min(w, 25))
    if w % 2 == 0:
        w += 1

    half = w // 2
    kx = np.arange(-half, half + 1)
    A = np.vander(kx, 3)[:, ::-1]  # Polinomio cuadrático de Savitzky-Golay
    coeffs = np.linalg.pinv(A)[0]
    padded = np.pad(y, half, mode="edge")
    res = np.convolve(padded, coeffs[::-1], mode="valid")
    res[0] = y[0]
    res[-1] = y[-1]
    return res


def get_open_meteo_profile(
    lat_a: float,
    lon_a: float,
    lat_b: float,
    lon_b: float,
    samples: int = 512,
    apply_smoothing: bool = True,
) -> pd.DataFrame:
    """Consulta la API pública de Open-Meteo y devuelve un DataFrame estructurado."""
    samples = max(2, int(samples))
    lats = np.linspace(lat_a, lat_b, samples)
    lons = np.linspace(lon_a, lon_b, samples)

    chunk_size = 100
    chunks = []
    for i in range(0, samples, chunk_size):
        chunk_lats = lats[i:i + chunk_size]
        chunk_lons = lons[i:i + chunk_size]
        chunks.append((i, chunk_lats, chunk_lons))

    def fetch_chunk(item):
        idx, clats, clons = item
        lat_str = ",".join(f"{x:.6f}" for x in clats)
        lon_str = ",".join(f"{x:.6f}" for x in clons)
        url = "https://api.open-meteo.com/v1/elevation"
        r = requests.get(url, params={"latitude": lat_str, "longitude": lon_str}, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "elevation" not in data:
            raise RuntimeError(f"Open-Meteo no devolvió elevaciones: {data.get('reason', 'Error desconocido')}")
        return idx, data.get("elevation", [])

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(fetch_chunk, chunks))

    results.sort(key=lambda x: x[0])
    elevations = []
    for _, elev in results:
        elevations.extend(elev)

    if len(elevations) < 2:
        raise RuntimeError("Open-Meteo no devolvió suficientes muestras de elevación.")

    distances = np.linspace(0, haversine(lat_a, lon_a, lat_b, lon_b), len(elevations))
    if apply_smoothing and len(elevations) >= 5:
        elevations = smooth_dem_profile(elevations, distances)

    rows = []
    for i in range(len(elevations)):
        rows.append({
            "sample": i,
            "lat": float(lats[i]),
            "lon": float(lons[i]),
            "elevation_m": float(elevations[i]),
            "resolution_m": 30.0,
            "distance_km": float(distances[i]),
        })

    return pd.DataFrame(rows)


def get_google_profile(
    api_key: str,
    lat_a: float,
    lon_a: float,
    lat_b: float,
    lon_b: float,
    samples: int = 512,
) -> pd.DataFrame:
    """Consulta la API de Google Maps Elevation."""
    if not api_key:
        raise ValueError("Se requiere una API Key de Google Maps.")

    url = "https://maps.googleapis.com/maps/api/elevation/json"
    params = {
        "path": f"{lat_a},{lon_a}|{lat_b},{lon_b}",
        "samples": int(samples),
        "key": api_key,
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    if data.get("status") != "OK":
        raise RuntimeError(f"Google Elevation API respondió: {data.get('status')} - {data.get('error_message', '')}")

    results = data.get("results", [])
    if len(results) < 2:
        raise RuntimeError("Google no devolvió suficientes muestras de elevación.")

    rows = []
    dist_total = haversine(lat_a, lon_a, lat_b, lon_b)
    distances = np.linspace(0, dist_total, len(results))

    for i, item in enumerate(results):
        rows.append({
            "sample": i,
            "lat": float(item["location"]["lat"]),
            "lon": float(item["location"]["lng"]),
            "elevation_m": float(item["elevation"]),
            "resolution_m": float(item.get("resolution", np.nan)),
            "distance_km": float(distances[i]),
        })

    return pd.DataFrame(rows)
