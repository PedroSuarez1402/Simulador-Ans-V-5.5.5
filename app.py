import math
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from pdf_catalog import load_json, save_json, parse_radio_pdf, parse_antenna_pdf, RADIOS_FILE, ANTENNAS_FILE
from project_manager import DEFAULT_PROJECTS_DIR, get_projects_dir, set_projects_dir, list_projects, save_project, load_project, df_from, create_kmz, rich_kml

try:
    import ee
    EE_AVAILABLE = True
except Exception:
    EE_AVAILABLE = False

VERSION = "V5.5.5"
EARTH_RADIUS_KM = 6371.0088
ETH_CANOPY_ASSET = "users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1"
ETH_SD_ASSET = "users/nlang/ETH_GlobalCanopyHeightSD_2020_10m_v1"
GEDI_MONTHLY_ASSET = "LARSE/GEDI/GEDI02_A_002_MONTHLY"

st.set_page_config(page_title="SAF Link Planner V5", page_icon="📡", layout="wide")


def choose_folder_dialog(initial=None):
    """Open a native Windows folder picker when the app is running locally."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        selected=filedialog.askdirectory(initialdir=str(initial or Path.home()), title="Seleccionar carpeta para proyectos SAF Link Planner")
        root.destroy()
        return selected
    except Exception:
        return ""

def choose_project_file_dialog(initial=None):
    """Open a native Windows file picker so projects remain accessible even after changing the projects folder."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        selected=filedialog.askopenfilename(
            initialdir=str(initial or Path.home()),
            title="Abrir proyecto SAF Link Planner",
            filetypes=[("Proyecto SAF Link Planner", "*.slp.json"), ("Todos los archivos", "*.*")],
        )
        root.destroy()
        return selected
    except Exception:
        return ""

st.markdown("""
<style>
.block-container {padding-top: 1.25rem; padding-bottom: 2rem;}
[data-testid="stSidebar"] {min-width: 340px; max-width: 340px;}
.small-note {font-size: 0.86rem; color: #666;}
</style>
""", unsafe_allow_html=True)


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def fspl_km_ghz(distance_km, freq_ghz):
    return 92.45 + 20 * math.log10(max(distance_km, 0.001)) + 20 * math.log10(freq_ghz)


def fresnel_radius_m(d1_km, d2_km, freq_ghz):
    D = d1_km + d2_km
    if D <= 0:
        return 0.0
    return 17.32 * math.sqrt((d1_km * d2_km) / (freq_ghz * D))


def antenna_gain(freq_ghz):
    if freq_ghz < 5.2:
        return 30.0, "4.9–5.2 GHz"
    if freq_ghz < 5.9:
        return 32.5, "5.2–5.9 GHz"
    return 33.2, "5.9–6.425 GHz"


def curvature_bulge_m(d1_km, d2_km, k=1.333):
    r_eff = EARTH_RADIUS_KM * k
    return (d1_km * d2_km) / (2 * r_eff) * 1000


def sample_count(distance_km):
    # Google Elevation API supports up to 512 samples. V4 uses the maximum
    # available density for long links so the vegetation envelope is not sparse.
    return int(min(512, max(151, round(distance_km * 1000 / 25) + 1)))


def google_elevation_profile(api_key, lat_a, lon_a, lat_b, lon_b, samples):
    if not api_key:
        raise ValueError("Falta la Google Maps API Key.")
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
        raise RuntimeError(
            f"Google Elevation API respondió: {data.get('status')} — {data.get('error_message', '')}"
        )
    results = data.get("results", [])
    if len(results) < 2:
        raise RuntimeError("Google no devolvió suficientes muestras de elevación.")
    rows = []
    for i, item in enumerate(results):
        rows.append({
            "sample": i,
            "lat": item["location"]["lat"],
            "lon": item["location"]["lng"],
            "elevation_m": float(item["elevation"]),
            "resolution_m": float(item.get("resolution", np.nan)),
        })
    df = pd.DataFrame(rows)
    df["distance_km"] = np.linspace(0, haversine(lat_a, lon_a, lat_b, lon_b), len(df))
    return df


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
    # Selecciona una ventana adaptativa que abarca ~3 a 4 celdas DEM de 90m (~350 m)
    w = int(round(window_meters / max(d_step_m, 1.0)))
    w = max(5, min(w, 25))
    if w % 2 == 0:
        w += 1

    half = w // 2
    kx = np.arange(-half, half + 1)
    A = np.vander(kx, 3)[:, ::-1]  # Polinomio cuadrático Savitzky-Golay
    coeffs = np.linalg.pinv(A)[0]
    padded = np.pad(y, half, mode='edge')
    res = np.convolve(padded, coeffs[::-1], mode='valid')
    # Preservar exactamente las cotas de los puntos extremos (torre A y torre B)
    res[0] = y[0]
    res[-1] = y[-1]
    return res


def open_meteo_elevation_profile(lat_a, lon_a, lat_b, lon_b, samples, smooth=True):
    """Fetch elevation profile from Open-Meteo Elevation API (Copernicus DEM 30m/90m).
    Free, requires no API key and no billing/credit card.
    Optionally applies adaptive sub-pixel continuous reconstruction to eliminate staircase artifacts.
    """
    samples = int(samples)
    if samples < 2:
        samples = 2
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
            raise RuntimeError(f"Open-Meteo no devolvió elevaciones: {data.get('reason', 'Respuesta desconocida')}")
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
    if smooth and len(elevations) >= 5:
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
    df = pd.DataFrame(rows)
    return df


def ee_initialize(project_id=None):
    if not EE_AVAILABLE:
        return False, "La librería earthengine-api no está instalada."
    try:
        if project_id:
            ee.Initialize(project=project_id)
        else:
            ee.Initialize()
        return True, "Google Earth Engine autenticado."
    except Exception as exc:
        return False, str(exc)


def _sample_image_along_points(image, latitudes, longitudes, scale=10):
    points = [
        ee.Feature(ee.Geometry.Point([float(lon), float(lat)]), {"idx": int(i)})
        for i, (lat, lon) in enumerate(zip(latitudes, longitudes))
    ]
    fc = ee.FeatureCollection(points)
    sampled = image.sampleRegions(collection=fc, scale=scale, geometries=False)
    info = sampled.getInfo()
    values = {}
    for f in info.get("features", []):
        props = f.get("properties", {})
        idx = props.get("idx")
        if idx is not None:
            values[int(idx)] = props
    return values


def eth_canopy_profile(latitudes, longitudes, project_id=None, include_uncertainty=True):
    """Dense 10 m canopy-height profile from the ETH 2020 Sentinel-2 + GEDI model."""
    ok, msg = ee_initialize(project_id)
    if not ok:
        raise RuntimeError(
            "No fue posible inicializar Google Earth Engine. "
            "Verifica earthengine authenticate y el proyecto configurado. "
            f"Detalle: {msg}"
        )

    # The public ETH asset is a global 10 m canopy-top-height model.
    # Rename its first band so the app is independent of the internal band name.
    canopy = ee.Image(ETH_CANOPY_ASSET).select([0], ["canopy_height_m"])
    values = _sample_image_along_points(canopy, latitudes, longitudes, scale=10)

    sd_values = {}
    if include_uncertainty:
        try:
            sd = ee.Image(ETH_SD_ASSET).select([0], ["canopy_sd_m"])
            sd_values = _sample_image_along_points(sd, latitudes, longitudes, scale=10)
        except Exception:
            # Uncertainty is optional; the main canopy surface remains usable.
            sd_values = {}

    rows = []
    for i in range(len(latitudes)):
        p = values.get(i, {})
        raw_h = p.get("canopy_height_m")
        raw_sd = sd_values.get(i, {}).get("canopy_sd_m")
        try:
            h = float(raw_h) if raw_h is not None else np.nan
        except Exception:
            h = np.nan
        try:
            sdv = float(raw_sd) if raw_sd is not None else np.nan
        except Exception:
            sdv = np.nan

        # ETH uses 255 as a no-data sentinel in its uint8 representation.
        if np.isfinite(h) and h >= 250:
            h = np.nan
        if np.isfinite(sdv) and sdv >= 250:
            sdv = np.nan
        rows.append({
            "canopy_height_m": h,
            "canopy_sd_m": sdv,
            "vegetation_detected": bool(np.isfinite(h) and h >= 1.0),
        })
    return pd.DataFrame(rows)


def gedi_fallback_profile(latitudes, longitudes, project_id=None):
    """Fallback to sparse GEDI RH98 where ETH asset access is unavailable."""
    ok, msg = ee_initialize(project_id)
    if not ok:
        raise RuntimeError(msg)

    points = [
        ee.Feature(ee.Geometry.Point([float(lon), float(lat)]), {"idx": int(i)})
        for i, (lat, lon) in enumerate(zip(latitudes, longitudes))
    ]
    fc = ee.FeatureCollection(points)

    def quality_mask(im):
        return im.updateMask(im.select("quality_flag").eq(1)).updateMask(im.select("degrade_flag").eq(0))

    dataset = (
        ee.ImageCollection(GEDI_MONTHLY_ASSET)
        .filterDate("2019-03-25", "2025-07-01")
        .map(quality_mask)
        .select("rh98")
    )
    image = dataset.median().select([0], ["canopy_height_m"])
    sampled = image.sampleRegions(collection=fc, scale=25, geometries=False).getInfo()
    values = {}
    for f in sampled.get("features", []):
        props = f.get("properties", {})
        if props.get("idx") is not None:
            values[int(props["idx"])] = props.get("canopy_height_m")
    rows = []
    for i in range(len(latitudes)):
        h = values.get(i)
        try:
            h = float(h) if h is not None else np.nan
        except Exception:
            h = np.nan
        rows.append({
            "canopy_height_m": h,
            "canopy_sd_m": np.nan,
            "vegetation_detected": bool(np.isfinite(h) and h >= 2.0),
        })
    return pd.DataFrame(rows)


def calculate_profile_geometry(prof, cfg, distance_km, freq_ghz, k_factor):
    terrain = prof["elevation_m"].to_numpy(dtype=float)
    x = prof["distance_km"].to_numpy(dtype=float)
    endpoint_a = terrain[0] + cfg["height_a"]
    endpoint_b = terrain[-1] + cfg["height_b"]
    los = np.linspace(endpoint_a, endpoint_b, len(terrain))
    curvature = np.array([
        curvature_bulge_m(xx, distance_km - xx, k_factor)
        if 0 < xx < distance_km else 0.0
        for xx in x
    ])
    los_worst = los - curvature
    f1 = np.array([
        fresnel_radius_m(xx, distance_km - xx, freq_ghz)
        if 0 < xx < distance_km else 0.0
        for xx in x
    ])
    f60 = 0.60 * f1
    out = prof.copy()
    out["los_m"] = los
    out["curvature_m"] = curvature
    out["los_worst_m"] = los_worst
    out["f1_radius_m"] = f1
    out["fresnel_60_m"] = f60
    out["fresnel_upper_m"] = los_worst + f60
    out["fresnel_lower_m"] = los_worst - f60
    out["clearance_terrain_m"] = out["fresnel_lower_m"] - terrain
    return out


def apply_exclusions(vdf, exclusions):
    out = vdf.copy()
    if exclusions is None or exclusions.empty:
        return out
    mask = np.ones(len(out), dtype=bool)
    for row in exclusions.itertuples(index=False):
        try:
            a = float(row.inicio_km)
            b = float(row.fin_km)
        except Exception:
            continue
        if b < a:
            a, b = b, a
        mask &= ~out["distance_km"].between(a, b)
    out["auto_excluded"] = ~mask
    out.loc[~mask, "vegetation_detected"] = False
    out.loc[~mask, "canopy_height_m"] = np.nan
    out.loc[~mask, "canopy_sd_m"] = np.nan
    return out


def apply_canopy_height_overrides(vdf, overrides):
    """Apply manual canopy-height overrides by distance ranges.

    Each active row replaces the automatic canopy height for all profile samples
    inside [inicio_km, fin_km]. Height is measured above local terrain. Setting
    height to 0 effectively removes the automatic canopy in that range.
    """
    out = vdf.copy()
    if overrides is None or overrides.empty:
        return out
    x = out["distance_km"].to_numpy(dtype=float)
    for row in overrides.itertuples(index=False):
        try:
            a = float(row.inicio_km)
            b = float(row.fin_km)
            h = max(0.0, float(row.altura_m))
            enabled = bool(row.activo)
        except Exception:
            continue
        if not enabled:
            continue
        if b < a:
            a, b = b, a
        hit = (x >= a) & (x <= b)
        if not hit.any():
            continue
        out.loc[hit, "canopy_height_m"] = h
        out.loc[hit, "vegetation_detected"] = h >= 1.0
        if "canopy_sd_m" in out.columns:
            out.loc[hit, "canopy_sd_m"] = np.nan
        if "canopy_top_m" in out.columns:
            out.loc[hit, "canopy_top_m"] = out.loc[hit, "elevation_m"] + h
    out["canopy_top_m"] = out["elevation_m"] + out["canopy_height_m"].clip(lower=0)
    out.loc[~out["vegetation_detected"].fillna(False), "canopy_top_m"] = np.nan
    if "los_worst_m" in out.columns:
        out["los_clearance_m"] = out["los_worst_m"] - out["canopy_top_m"]
    if "fresnel_lower_m" in out.columns:
        out["fresnel_clearance_m"] = out["fresnel_lower_m"] - out["canopy_top_m"]
    out["status"] = np.select(
        [
            ~out["vegetation_detected"].fillna(False),
            out["los_clearance_m"] < 0,
            out["fresnel_clearance_m"] < 0,
        ],
        ["Sin vegetación", "🔴 Obstruye LOS", "🟠 Invade Fresnel 60%"],
        default="🟢 Despejado",
    )
    return out



def apply_canopy_point_overrides(vdf, overrides):
    """Apply manual heights edited directly in the affected-vegetation table."""
    out=vdf.copy()
    if overrides is None or overrides.empty or 'distance_km' not in out.columns:
        return out
    x=out['distance_km'].to_numpy(dtype=float)
    for row in overrides.itertuples(index=False):
        try:
            d=float(row.distance_km); h=max(0.0,float(row.altura_m)); active=bool(row.activo)
        except Exception:
            continue
        if not active:
            continue
        idx=int(np.argmin(np.abs(x-d)))
        # Use a small neighborhood around the sample so the edit is visible
        # in the profile and not reduced to a single 10 m pixel.
        step=float(np.nanmedian(np.diff(x))) if len(x)>1 else 0.01
        hit=np.abs(x-d)<=max(step*1.5,0.005)
        out.loc[hit,'canopy_height_m']=h
        out.loc[hit,'vegetation_detected']=h>=1.0
        if 'canopy_sd_m' in out.columns: out.loc[hit,'canopy_sd_m']=np.nan
    out['canopy_top_m']=out['elevation_m']+out['canopy_height_m'].clip(lower=0)
    out.loc[~out['vegetation_detected'].fillna(False),'canopy_top_m']=np.nan
    if 'los_worst_m' in out.columns: out['los_clearance_m']=out['los_worst_m']-out['canopy_top_m']
    if 'fresnel_lower_m' in out.columns: out['fresnel_clearance_m']=out['fresnel_lower_m']-out['canopy_top_m']
    out['status']=np.select([~out['vegetation_detected'].fillna(False),out['los_clearance_m']<0,out['fresnel_clearance_m']<0],['Sin vegetación','🔴 Obstruye LOS','🟠 Invade Fresnel 60%'],default='🟢 Despejado')
    return out

def build_vegetation_profile(prof, vraw, profile_calc, exclusions=None):
    out = pd.concat([prof.reset_index(drop=True), vraw.reset_index(drop=True)], axis=1)
    calc_cols = [
        "los_m", "los_worst_m", "f1_radius_m", "fresnel_60_m",
        "fresnel_upper_m", "fresnel_lower_m", "clearance_terrain_m"
    ]
    out = pd.concat([out, profile_calc[calc_cols].reset_index(drop=True)], axis=1)
    out["canopy_top_m"] = out["elevation_m"] + out["canopy_height_m"].clip(lower=0)
    out.loc[~out["vegetation_detected"].fillna(False), "canopy_top_m"] = np.nan
    out["auto_excluded"] = False
    out = apply_exclusions(out, exclusions)
    out["los_clearance_m"] = out["los_worst_m"] - out["canopy_top_m"]
    out["fresnel_clearance_m"] = out["fresnel_lower_m"] - out["canopy_top_m"]
    out["status"] = np.select(
        [
            ~out["vegetation_detected"].fillna(False),
            out["los_clearance_m"] < 0,
            out["fresnel_clearance_m"] < 0,
        ],
        ["Sin vegetación", "🔴 Obstruye LOS", "🟠 Invade Fresnel 60%"],
        default="🟢 Despejado",
    )
    return out


def add_manual_obstacles(vdf, obstacles):
    out = vdf.copy()
    out["manual_obstacle_top_m"] = np.nan
    out["manual_obstacle_name"] = ""
    if obstacles is None or obstacles.empty:
        out["final_obstruction_top_m"] = out["canopy_top_m"]
        return out

    x = out["distance_km"].to_numpy(dtype=float)
    terrain = out["elevation_m"].to_numpy(dtype=float)
    manual_top = np.full(len(out), np.nan)
    names = np.array([""] * len(out), dtype=object)

    for row in obstacles.itertuples(index=False):
        try:
            center = float(row.distancia_km)
            width = max(0.01, float(row.ancho_m))
            height = max(0.0, float(row.altura_m))
            enabled = bool(row.activo)
        except Exception:
            continue
        if not enabled:
            continue
        left = center - width / 2000.0
        right = center + width / 2000.0
        hit = (x >= left) & (x <= right)
        if not hit.any():
            # Always show a manual obstacle at the nearest sampled point.
            idx = int(np.argmin(np.abs(x - center)))
            hit[idx] = True
        tops = np.interp(x[hit], x, terrain) + height
        replace = np.isnan(manual_top[hit]) | (tops > manual_top[hit])
        idxs = np.where(hit)[0]
        manual_top[idxs[replace]] = tops[replace]
        names[idxs[replace]] = str(row.nombre)

    out["manual_obstacle_top_m"] = manual_top
    out["manual_obstacle_name"] = names
    out["final_obstruction_top_m"] = np.nanmax(
        np.vstack([
            out["canopy_top_m"].to_numpy(dtype=float),
            manual_top,
        ]), axis=0
    )
    return out


def contiguous_segments(mask):
    mask = np.asarray(mask, dtype=bool)
    if len(mask) == 0:
        return []
    changes = np.diff(mask.astype(int))
    starts = list(np.where(changes == 1)[0] + 1)
    ends = list(np.where(changes == -1)[0] + 1)
    if mask[0]:
        starts.insert(0, 0)
    if mask[-1]:
        ends.append(len(mask))
    return list(zip(starts, ends))


def add_profile_layers(fig, df, show_vegetation=True, show_fresnel=True, show_uncertainty=False):
    x = df["distance_km"].to_numpy(dtype=float)
    terrain = df["elevation_m"].to_numpy(dtype=float)

    fig.add_trace(go.Scatter(
        x=x, y=terrain, name="Terreno", mode="lines",
        line=dict(color="#7a4b21", width=2),
        fill="tozeroy", fillcolor="rgba(122,75,33,0.72)",
        hovertemplate="Distancia: %{x:.3f} km<br>Terreno: %{y:.1f} m<extra></extra>",
    ))

    if show_vegetation and "final_obstruction_top_m" in df.columns:
        top = df["final_obstruction_top_m"].to_numpy(dtype=float)
        valid = np.isfinite(top) & (top > terrain + 0.5)
        # Draw each continuous patch separately. This prevents the V3 triangular
        # artifact caused by Plotly fill-to-next-trace across missing data.
        for n, (a, b) in enumerate(contiguous_segments(valid)):
            xs = x[a:b]
            ys_top = top[a:b]
            ys_ground = terrain[a:b]
            poly_x = np.concatenate([xs, xs[::-1]])
            poly_y = np.concatenate([ys_top, ys_ground[::-1]])
            fig.add_trace(go.Scatter(
                x=poly_x, y=poly_y, name="Arborización" if n == 0 else None,
                mode="lines", line=dict(color="#38c83a", width=1),
                fill="toself", fillcolor="rgba(65,205,60,0.78)",
                hoverinfo="skip", showlegend=(n == 0),
            ))
            fig.add_trace(go.Scatter(
                x=xs, y=ys_top, name="Copa / obstáculo" if n == 0 else None,
                mode="lines", line=dict(color="#25a62a", width=1.2),
                showlegend=(n == 0),
                hovertemplate="Distancia: %{x:.3f} km<br>Cota superior: %{y:.1f} m<extra></extra>",
            ))

    if show_uncertainty and "canopy_sd_m" in df.columns and "canopy_top_m" in df.columns:
        upper = df["canopy_top_m"] + df["canopy_sd_m"]
        valid = np.isfinite(upper) & np.isfinite(df["canopy_top_m"])
        if valid.any():
            fig.add_trace(go.Scatter(
                x=x[valid], y=upper.to_numpy(dtype=float)[valid],
                name="Incertidumbre canopy", mode="lines",
                line=dict(color="#9ad39a", width=1, dash="dot"),
                hovertemplate="Cota superior +σ: %{y:.1f} m<extra></extra>",
            ))

    if show_fresnel:
        xu = np.concatenate([x, x[::-1]])
        yu = np.concatenate([
            df["fresnel_upper_m"].to_numpy(dtype=float),
            df["fresnel_lower_m"].to_numpy(dtype=float)[::-1],
        ])
        fig.add_trace(go.Scatter(
            x=xu, y=yu, name="Fresnel 60%", mode="lines",
            line=dict(color="rgba(0,120,255,0.55)", width=1),
            fill="toself", fillcolor="rgba(0,120,255,0.12)", hoverinfo="skip",
        ))

    fig.add_trace(go.Scatter(
        x=x, y=df["los_worst_m"], name="Peor caso / K", mode="lines",
        line=dict(color="#777777", width=1.5, dash="dot"),
        hovertemplate="Peor caso: %{y:.1f} m<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["los_m"], name="LOS", mode="lines",
        line=dict(color="#e31a1c", width=2.6),
        hovertemplate="LOS: %{y:.1f} m<extra></extra>",
    ))


def style_profile(fig, title):
    fig.update_layout(
        height=620,
        margin=dict(l=70, r=30, t=65, b=60),
        title=title,
        hovermode="x unified",
        paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14",
        font=dict(color="#e8edf2"),
        xaxis=dict(title="Distancia desde A (km)", gridcolor="rgba(255,255,255,0.12)", zeroline=False),
        yaxis=dict(title="Elevación / cota (m)", gridcolor="rgba(255,255,255,0.12)", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )



def _radio_label(r):
    return f"{r.get('manufacturer','')} {r.get('model','')}"


def _antenna_label(a):
    return f"{a.get('manufacturer','')} {a.get('model','')} — {a.get('gain_dbi','?')} dBi"


def add_obstacle_markers(fig, df, obstacles):
    if obstacles is None or obstacles.empty:
        return
    symbols = {"Árbol":"🌳", "Vegetación":"🌿", "Edificio":"🏢", "Casa":"🏠", "Torre":"🗼", "Poste":"📡", "Muro":"🧱", "Bodega":"🏭", "Estructura":"🏗️", "Otro":"⚠️"}
    xprof = df["distance_km"].to_numpy(dtype=float)
    tprof = df["elevation_m"].to_numpy(dtype=float)
    for row in obstacles.itertuples(index=False):
        if not bool(getattr(row, 'activo', True)):
            continue
        d = float(row.distancia_km); h = float(row.altura_m)
        ground = float(np.interp(d, xprof, tprof))
        typ = str(getattr(row, 'tipo', 'Otro'))
        label = f"{symbols.get(typ,'⚠️')} {getattr(row,'nombre','') or typ}"
        fig.add_trace(go.Scatter(x=[d], y=[ground+h], mode='markers+text', text=[label], textposition='top center',
                                 marker=dict(size=10, symbol='diamond'), name=f"Obstáculo: {typ}",
                                 hovertemplate=f"{label}<br>Distancia: {d:.3f} km<br>Altura: {h:.1f} m<extra></extra>", showlegend=False))


def radio_to_dict(r):
    out = {
        'manufacturer': str(r.get('manufacturer','')), 'model': str(r.get('model','')), 'source_file': str(r.get('source_file','')),
        'frequency_min_ghz': r.get('frequency_min_ghz'), 'frequency_max_ghz': r.get('frequency_max_ghz'),
        'max_output_power_dbm': r.get('max_output_power_dbm'), 'integrated_antenna_gain_dbi': r.get('integrated_antenna_gain_dbi'),
        'throughput_gbps': r.get('throughput_gbps'), 'bandwidths_mhz': r.get('bandwidths_mhz',[]), 'mimo': str(r.get('mimo','')),
        'modulation': str(r.get('modulation','')), 'rx_sensitivity_dbm': r.get('rx_sensitivity_dbm',{}), 'notes': str(r.get('notes',''))
    }
    if r.get('extra_parameters_json'):
        out['extra_parameters_json'] = str(r.get('extra_parameters_json'))
    for k, v in r.items():
        if k not in out and k not in {'extra_parameters_json'}:
            out[k] = v
    return out

def antenna_to_dict(a):
    keys = [
        'manufacturer','model','source_file','frequency_min_ghz','frequency_max_ghz',
        'diameter_m','gain_dbi','gain_low_dbi','gain_mid_dbi','gain_high_dbi',
        'beamwidth_deg','polarization','shielding','front_to_back_ratio_db','xpd_db',
        'vswr','port_isolation_db','connector','elevation_adjustment','azimuth_adjustment',
        'polarization_adjustment','weight_kg','mast_mount','operational_wind_kmh',
        'survival_wind_kmh','wind_area_m2','material','dimension_a_mm','dimension_b_mm',
        'dimension_c_mm','packed_weight_kg','notes'
    ]
    out = {}
    for k in keys:
        v = a.get(k, '')
        if v is None:
            v = ''
        out[k] = v
    for k in ['frequency_min_ghz','frequency_max_ghz','diameter_m','gain_dbi','gain_low_dbi','gain_mid_dbi','gain_high_dbi','beamwidth_deg','weight_kg','operational_wind_kmh','survival_wind_kmh','wind_area_m2','dimension_a_mm','dimension_b_mm','dimension_c_mm','packed_weight_kg']:
        if out.get(k) == '':
            out[k] = None
        else:
            try:
                out[k] = float(out[k])
            except Exception:
                pass
    return out


def _is_shielded(a):
    value = str(a.get('shielding','')).strip().lower()
    return value.startswith('sí') or value.startswith('si') or 'deep dish' in value or 'shield' in value


def obstacle_table(vdf):
    if vdf is None:
        return pd.DataFrame()
    m = vdf["vegetation_detected"].fillna(False) & np.isfinite(vdf["canopy_top_m"])
    cols = [
        "distance_km", "lat", "lon", "elevation_m", "canopy_height_m",
        "canopy_sd_m", "canopy_top_m", "los_clearance_m", "fresnel_clearance_m", "status"
    ]
    return vdf.loc[m, [c for c in cols if c in vdf.columns]].copy()


def df_to_kml(df, name_a, name_b, lat_a, lon_a, lat_b, lon_b, critical, manual):
    def esc(v):
        return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    coords = " ".join(f"{r.lon},{r.lat},0" for r in df.itertuples())
    placemarks = [f"""
<Placemark><name>{esc(name_a)}</name><Point><coordinates>{lon_a},{lat_a},0</coordinates></Point></Placemark>
<Placemark><name>{esc(name_b)}</name><Point><coordinates>{lon_b},{lat_b},0</coordinates></Point></Placemark>
<Placemark><name>Trayectoria del enlace</name><Style><LineStyle><color>ff0000ff</color><width>4</width></LineStyle></Style><LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString></Placemark>
"""]

    for r in critical.itertuples():
        placemarks.append(f"""
<Placemark><name>Vegetación {r.distance_km:.2f} km — {r.canopy_height_m:.1f} m</name>
<description><![CDATA[Distancia: {r.distance_km:.3f} km<br/>Lat: {r.lat:.6f}<br/>Lon: {r.lon:.6f}<br/>Altura copa: {r.canopy_height_m:.1f} m<br/>Margen LOS: {r.los_clearance_m:.1f} m<br/>Fresnel 60%: {r.fresnel_clearance_m:.1f} m]]></description>
<Point><coordinates>{r.lon},{r.lat},0</coordinates></Point></Placemark>
""")

    for row in manual.itertuples(index=False):
        if not bool(row.activo):
            continue
        lat = float(np.interp(float(row.distancia_km), df["distance_km"], df["lat"]))
        lon = float(np.interp(float(row.distancia_km), df["distance_km"], df["lon"]))
        placemarks.append(f"""
<Placemark><name>Manual: {esc(row.nombre)}</name><description><![CDATA[Tipo: {esc(row.tipo)}<br/>Distancia: {float(row.distancia_km):.3f} km<br/>Altura: {float(row.altura_m):.1f} m<br/>Ancho: {float(row.ancho_m):.1f} m]]></description><Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>
""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>SAF Link Planner V5 — Radioenlace</name>{''.join(placemarks)}</Document></kml>""".encode("utf-8")


# ---------------- Session state ----------------
if "link_config" not in st.session_state:
    st.session_state.link_config = {
        "name_a": "ALPINA", "lat_a": 4.917140, "lon_a": -73.942130, "height_a": 24.0,
        "name_b": "NODO ZIPAQUIRÁ", "lat_b": 5.036680, "lon_b": -73.988580, "height_b": 30.0,
        "required_capacity": 500.0,
    }
if "profile_df" not in st.session_state:
    st.session_state.profile_df = None
if "veg_df" not in st.session_state:
    st.session_state.veg_df = None
if "manual_obstacles" not in st.session_state:
    st.session_state.manual_obstacles = pd.DataFrame([
        {"nombre": "", "tipo": "Árbol", "distancia_km": 0.0, "altura_m": 0.0, "ancho_m": 10.0, "activo": True}
    ])
if "exclusions" not in st.session_state:
    st.session_state.exclusions = pd.DataFrame(columns=["inicio_km", "fin_km"])
if "canopy_overrides" not in st.session_state:
    st.session_state.canopy_overrides = pd.DataFrame(columns=["inicio_km", "fin_km", "altura_m", "activo"])
if "canopy_point_overrides" not in st.session_state:
    st.session_state.canopy_point_overrides = pd.DataFrame(columns=["distance_km", "altura_m", "activo"])
if "radios" not in st.session_state:
    st.session_state.radios = load_json(RADIOS_FILE, [])
if "antennas" not in st.session_state:
    st.session_state.antennas = load_json(ANTENNAS_FILE, [])
if "selected_radio_a" not in st.session_state:
    st.session_state.selected_radio_a = 0
if "selected_radio_b" not in st.session_state:
    st.session_state.selected_radio_b = 0
if "selected_ant_a" not in st.session_state:
    st.session_state.selected_ant_a = 0
if "selected_ant_b" not in st.session_state:
    st.session_state.selected_ant_b = 0
if "current_project_name" not in st.session_state:
    st.session_state.current_project_name = "Proyecto sin nombre"
if "project_rf" not in st.session_state:
    st.session_state.project_rf = {}
if "ar_enabled" not in st.session_state:
    st.session_state.ar_enabled = True
if "ee_project" not in st.session_state:
    st.session_state.ee_project = "saf-link-planner"
if "elevation_provider" not in st.session_state:
    st.session_state.elevation_provider = "Open-Meteo (Gratuito / Copernicus DEM)"

def load_project_into_session(data, fallback_name="Proyecto"):
    """Restore a saved project from either the project folder or an arbitrary .slp.json file."""
    st.session_state.link_config = data.get("link_config", st.session_state.link_config)
    st.session_state.project_rf = data.get("rf_settings", {})
    st.session_state.selected_radio_a = int(data.get("selected_radio_a", 0) or 0)
    st.session_state.selected_radio_b = int(data.get("selected_radio_b", 0) or 0)
    st.session_state.selected_ant_a = int(data.get("selected_ant_a", 0) or 0)
    st.session_state.selected_ant_b = int(data.get("selected_ant_b", 0) or 0)
    st.session_state.exclusions = df_from(data.get("exclusions", []), ["inicio_km","fin_km"])
    st.session_state.canopy_overrides = df_from(data.get("canopy_overrides", []), ["inicio_km","fin_km","altura_m","activo"])
    st.session_state.canopy_point_overrides = df_from(data.get("canopy_point_overrides", []), ["distance_km","altura_m","activo"])
    st.session_state.manual_obstacles = df_from(data.get("manual_obstacles", []), ["nombre","tipo","distancia_km","altura_m","ancho_m","activo"])
    st.session_state.profile_df = df_from(data.get("profile_df"))
    st.session_state.veg_df = df_from(data.get("veg_df"))
    st.session_state.current_project_name = data.get("meta",{}).get("name", fallback_name)
    st.session_state.ee_project = data.get("ee_project", "saf-link-planner")
    st.session_state.elevation_provider = data.get("elevation_provider", "Open-Meteo (Gratuito / Copernicus DEM)")
    for k in ["freq_input","tx_input","channel_input","capacity_input","losses_input","kfactor_input","project_name_input"]:
        st.session_state.pop(k, None)

cfg = st.session_state.link_config

distance = haversine(cfg["lat_a"], cfg["lon_a"], cfg["lat_b"], cfg["lon_b"])

# ---------------- Sidebar ----------------
st.sidebar.title("📡 SAF Link Planner V5.5.5")
st.sidebar.caption("Radios + antenas + terreno + canopy + obstáculos + proyectos")

st.sidebar.subheader("📁 Proyectos")
projects_dir = get_projects_dir()
st.sidebar.caption("Carpeta donde se guardan y desde donde se abren los proyectos")
st.sidebar.text_input("Carpeta de proyectos", value=str(projects_dir), key="projects_dir_display", disabled=True)
pd1,pd2 = st.sidebar.columns(2)
if pd1.button("📂 Cambiar carpeta", key="change_projects_dir", width="stretch"):
    chosen=choose_folder_dialog(projects_dir)
    if chosen:
        set_projects_dir(chosen)
        st.rerun()
if pd2.button("↩️ Carpeta predeterminada", key="default_projects_dir", width="stretch"):
    set_projects_dir(DEFAULT_PROJECTS_DIR)
    st.rerun()
project_name = st.sidebar.text_input("Nombre del proyecto", value=st.session_state.current_project_name, key="project_name_input")
st.session_state.current_project_name = project_name
project_rows = list_projects()
project_names = [r["name"] for r in project_rows]
if project_names:
    load_name = st.sidebar.selectbox("Proyectos guardados", project_names, key="project_load_select")
    p1,p2 = st.sidebar.columns(2)
    if p1.button("📂 Abrir", key="open_project_btn", width="stretch"):
        selected = next((r for r in project_rows if r["name"] == load_name), None)
        if selected:
            data = load_project(get_projects_dir() / selected["file"])
            load_project_into_session(data, load_name)
            st.rerun()
    if p2.button("🗑️ Borrar", key="delete_project_btn", width="stretch"):
        selected = next((r for r in project_rows if r["name"] == load_name), None)
        if selected:
            (get_projects_dir() / selected["file"]).unlink(missing_ok=True)
            st.rerun()

    if st.sidebar.button("📂 Abrir proyecto desde archivo...", key="open_project_file", width="stretch"):
        selected_file = choose_project_file_dialog(get_projects_dir())
        if selected_file:
            try:
                data = load_project(selected_file)
                load_project_into_session(data, Path(selected_file).stem.replace('.slp',''))
                st.success(f"Proyecto abierto: {Path(selected_file).name}")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo abrir el proyecto: {exc}")
else:
    st.sidebar.caption("No hay proyectos guardados todavía.")

st.sidebar.subheader("🗺️ Elevación / Terreno")
provider_options = ["Open-Meteo (Gratuito / Copernicus DEM)", "Google Maps Elevation API (Requiere Key)"]
curr_provider = st.session_state.get("elevation_provider", provider_options[0])
provider_idx = provider_options.index(curr_provider) if curr_provider in provider_options else 0
elevation_provider = st.sidebar.selectbox(
    "Proveedor de elevación",
    provider_options,
    index=provider_idx,
    key="elevation_provider_select",
    help="Elige Open-Meteo para usar datos de elevación gratuitos Copernicus 30m sin tarjeta de crédito ni API key, o Google Maps Elevation si cuentas con una clave propia de Google Cloud."
)
st.session_state.elevation_provider = elevation_provider

google_api_key = ""
if elevation_provider == "Google Maps Elevation API (Requiere Key)":
    google_api_key = st.sidebar.text_input("Google Maps API Key", type="password")
    st.sidebar.caption("Requiere tener Elevation API habilitada y facturación activa en Google Cloud.")
else:
    st.sidebar.success("✅ Modo gratuito activo: Copernicus DEM 30m vía Open-Meteo. No requiere tarjeta ni API key.")
    om_smoothing = st.sidebar.checkbox(
        "Suavizado continuo sub-píxel (Anti-escalonado)",
        value=st.session_state.get("om_smoothing", True),
        help="Elimina el efecto de terrazas y escalones del DEM de Open-Meteo mediante reconstrucción polinomial adaptativa, aproximándolo a la fidelidad visual y curvas de Google Maps.",
        key="om_smoothing_checkbox"
    )
    st.session_state.om_smoothing = om_smoothing

st.sidebar.subheader("🌳 Arborización / Árboles")
ee_project = st.sidebar.text_input("Earth Engine Project ID", value=st.session_state.get("ee_project","saf-link-planner"), key="ee_project_input")
st.session_state.ee_project = ee_project

ar_enabled = st.sidebar.checkbox("Usar arborización automática", value=st.session_state.get("ar_enabled",True), key="ar_enabled_input")
st.session_state.ar_enabled = ar_enabled
st.sidebar.info("Fuente principal: ETH Global Canopy Height 2020, 10 m, derivada de Sentinel-2 + GEDI. La fuente es un modelo de altura de copa, no un inventario de cada árbol.")

st.sidebar.subheader("📡 Equipo de radio")
radios = st.session_state.radios
radio_labels = [_radio_label(r) for r in radios] or ["Sin radios cargados"]
ra = st.sidebar.selectbox("Radio A", radio_labels, index=min(st.session_state.selected_radio_a, len(radio_labels)-1), key="radio_a_select")
rb = st.sidebar.selectbox("Radio B", radio_labels, index=min(st.session_state.selected_radio_b, len(radio_labels)-1), key="radio_b_select")
st.session_state.selected_radio_a = radio_labels.index(ra) if ra in radio_labels else 0
st.session_state.selected_radio_b = radio_labels.index(rb) if rb in radio_labels else 0
radio_a = radios[st.session_state.selected_radio_a] if radios else {}
radio_b = radios[st.session_state.selected_radio_b] if radios else {}

def _radio_freq_default(r):
    lo=r.get('frequency_min_ghz'); hi=r.get('frequency_max_ghz')
    if lo is not None and hi is not None: return round((float(lo)+float(hi))/2,3)
    return 5.8

freq_default = _radio_freq_default(radio_a)
lo_freq = float(radio_a.get('frequency_min_ghz') or 4.9)
hi_freq = float(radio_a.get('frequency_max_ghz') or 7.125)
if hi_freq <= lo_freq: hi_freq = lo_freq + 0.1
freq = st.sidebar.number_input("Frecuencia (GHz)", min_value=max(0.1, lo_freq), max_value=hi_freq, value=min(max(float(st.session_state.project_rf.get("frequency_ghz", freq_default)), lo_freq), hi_freq), step=0.001, key="freq_input")
tx_default = float(radio_a.get('max_output_power_dbm') or 24.0)
tx_power = st.sidebar.number_input("Potencia TX (dBm)", 0.0, 40.0, float(st.session_state.project_rf.get("tx_power_dbm",tx_default)), 0.5, key="tx_input")
radio_b_gain = float(radio_b.get('integrated_antenna_gain_dbi') or 0.0)
channel_options = radio_a.get('bandwidths_mhz') or [20,40,80,160]
channel_options = sorted({int(x) for x in channel_options if int(x)>0})
saved_channel = int(st.session_state.project_rf.get("channel_mhz", channel_options[min(2,len(channel_options)-1)]))
channel = st.sidebar.selectbox("Ancho de canal (MHz)", channel_options, index=channel_options.index(saved_channel) if saved_channel in channel_options else min(2,len(channel_options)-1), key="channel_input")
required_capacity = st.sidebar.number_input("Capacidad requerida (Mbps)", 1.0, 10000.0, float(st.session_state.project_rf.get("required_capacity_mbps",cfg["required_capacity"])), 10.0, key="capacity_input")
other_losses = st.sidebar.number_input("Pérdidas adicionales (dB)", 0.0, 30.0, float(st.session_state.project_rf.get("other_losses_db",2.0)), 0.5, key="losses_input")
k_opts=[0.667,1.0,1.333,2.0]
saved_k=float(st.session_state.project_rf.get("k_factor",1.333))
k_factor = st.sidebar.selectbox("Factor K", k_opts, index=k_opts.index(saved_k) if saved_k in k_opts else 2, key="kfactor_input")

st.sidebar.subheader("📡 Antenas")
antennas = st.session_state.antennas
ant_labels = [_antenna_label(a) for a in antennas] or ["Sin antenas cargadas"]
aa = st.sidebar.selectbox("Antena A", ant_labels, index=min(st.session_state.selected_ant_a, len(ant_labels)-1), key="ant_a_select")
ab = st.sidebar.selectbox("Antena B", ant_labels, index=min(st.session_state.selected_ant_b, len(ant_labels)-1), key="ant_b_select")
st.session_state.selected_ant_a = ant_labels.index(aa) if aa in ant_labels else 0
st.session_state.selected_ant_b = ant_labels.index(ab) if ab in ant_labels else 0
ant_a = antennas[st.session_state.selected_ant_a] if antennas else {}
ant_b = antennas[st.session_state.selected_ant_b] if antennas else {}
gain_a = float(ant_a.get('gain_dbi') if ant_a else (radio_a.get('integrated_antenna_gain_dbi') or 0.0))
gain_b = float(ant_b.get('gain_dbi') if ant_b else (radio_b.get('integrated_antenna_gain_dbi') or 0.0))
gain_band = ant_a.get('model','Antena integrada') if ant_a else 'Antena integrada'
st.session_state.radio_a_snapshot = dict(radio_a)
st.session_state.radio_b_snapshot = dict(radio_b)
st.session_state.antenna_a_snapshot = dict(ant_a)
st.session_state.antenna_b_snapshot = dict(ant_b)
st.session_state.project_rf.update({"frequency_ghz":freq,"tx_power_dbm":tx_power,"channel_mhz":channel,"required_capacity_mbps":required_capacity,"other_losses_db":other_losses,"k_factor":k_factor})

st.sidebar.subheader("🌳 Obstáculos")
st.sidebar.caption("La vegetación automática se controla arriba. Los obstáculos manuales pueden ser árboles, edificios, torres, muros y estructuras.")

st.title("📡 SAF Link Planner V5.5.5 — Planificador de radioenlaces")
st.markdown(
    "**Objetivo V5.4:** sustituir la arborización dispersa de la V3 por una superficie de copa mucho más continua, "
    "usando un modelo global de altura de copa de **10 m** y permitiendo **quitar o agregar obstáculos manualmente**."
)

# ---------------- Project controls ----------------
with st.expander("💾 Guardar / administrar proyecto", expanded=False):
    st.caption("Los proyectos se guardan en la carpeta seleccionada. Puedes cambiarla en la barra lateral y trabajar con una carpeta de proyectos independiente.")
    a,b,c=st.columns(3)
    if a.button("💾 Guardar proyecto", key="save_project_main", type="primary", width="stretch"):
        state={"link_config":st.session_state.link_config,"rf_settings":st.session_state.project_rf,"selected_radio_a":st.session_state.selected_radio_a,"selected_radio_b":st.session_state.selected_radio_b,"selected_ant_a":st.session_state.selected_ant_a,"selected_ant_b":st.session_state.selected_ant_b,"exclusions":st.session_state.exclusions,"canopy_overrides":st.session_state.canopy_overrides,"canopy_point_overrides":st.session_state.canopy_point_overrides,"manual_obstacles":st.session_state.manual_obstacles,"profile_df":st.session_state.profile_df,"veg_df":st.session_state.veg_df,"ee_project":st.session_state.ee_project,"elevation_provider":st.session_state.get("elevation_provider","Open-Meteo (Gratuito / Copernicus DEM)")}
        path,_=save_project(st.session_state.current_project_name,state)
        st.success(f"Proyecto guardado: {path.name}")
    if b.button("🆕 Nuevo proyecto", key="new_project_main", width="stretch"):
        st.session_state.current_project_name="Proyecto sin nombre"
        st.session_state.pop("project_name_input", None)
        st.session_state.link_config={"name_a":"ALPINA","lat_a":4.917140,"lon_a":-73.942130,"height_a":24.0,"name_b":"NODO ZIPAQUIRÁ","lat_b":5.036680,"lon_b":-73.988580,"height_b":30.0,"required_capacity":500.0}
        st.session_state.profile_df=None; st.session_state.veg_df=None; st.session_state.project_rf={}
        st.session_state.exclusions=pd.DataFrame(columns=["inicio_km","fin_km"])
        st.session_state.canopy_overrides=pd.DataFrame(columns=["inicio_km","fin_km","altura_m","activo"])
        st.session_state.manual_obstacles=pd.DataFrame(columns=["nombre","tipo","distancia_km","altura_m","ancho_m","activo"])
        st.session_state.elevation_provider="Open-Meteo (Gratuito / Copernicus DEM)"
        for k in ["freq_input","tx_input","channel_input","capacity_input","losses_input","kfactor_input"]: st.session_state.pop(k,None)
        st.rerun()
    if c.button("📋 Actualizar lista", key="refresh_projects", width="stretch"): st.rerun()
    rows=list_projects()
    if rows: st.dataframe(pd.DataFrame(rows)[["name","modified","site_a","site_b"]],width="stretch",hide_index=True)

# ---------------- Tabs ----------------
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "1 · Sitios", "2 · Perfil LINKPlanner", "3 · Arborización / edición", "4 · Presupuesto RF", "5 · Resultado", "6 · Exportar KMZ", "7 · Biblioteca RF"
])

with tab1:
    st.subheader("Datos de los sitios")
    with st.form("site_parameters_form"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### Sitio A")
            name_a = st.text_input("Nombre A", cfg["name_a"])
            lat_a = st.number_input("Latitud A", value=float(cfg["lat_a"]), format="%.6f")
            lon_a = st.number_input("Longitud A", value=float(cfg["lon_a"]), format="%.6f")
            height_a = st.number_input("Altura antena A sobre terreno (m)", 0.0, 500.0, float(cfg["height_a"]))
        with c2:
            st.markdown("### Sitio B")
            name_b = st.text_input("Nombre B", cfg["name_b"])
            lat_b = st.number_input("Latitud B", value=float(cfg["lat_b"]), format="%.6f")
            lon_b = st.number_input("Longitud B", value=float(cfg["lon_b"]), format="%.6f")
            height_b = st.number_input("Altura antena B sobre terreno (m)", 0.0, 500.0, float(cfg["height_b"]))
        apply = st.form_submit_button("✅ Aplicar cambios", type="primary", width="stretch")

    if apply:
        st.session_state.link_config = {
            "name_a": name_a, "lat_a": lat_a, "lon_a": lon_a, "height_a": height_a,
            "name_b": name_b, "lat_b": lat_b, "lon_b": lon_b, "height_b": height_b,
            "required_capacity": required_capacity,
        }
        st.session_state.profile_df = None
        st.session_state.veg_df = None
        st.rerun()

    distance = haversine(cfg["lat_a"], cfg["lon_a"], cfg["lat_b"], cfg["lon_b"])
    az_ab = bearing(cfg["lat_a"], cfg["lon_a"], cfg["lat_b"], cfg["lon_b"])
    az_ba = bearing(cfg["lat_b"], cfg["lon_b"], cfg["lat_a"], cfg["lon_a"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Distancia", f"{distance:.3f} km")
    m2.metric("Azimut A → B", f"{az_ab:.2f}°")
    m3.metric("Azimut B → A", f"{az_ba:.2f}°")
    m4.metric("Capacidad objetivo", f"{required_capacity:.0f} Mbps")

    st.markdown("### Generar terreno")
    prov_col1, prov_col2 = st.columns([2, 1])
    with prov_col1:
        st.markdown(f"**Fuente de elevación seleccionada:** `{elevation_provider}`")
    with prov_col2:
        if elevation_provider.startswith("Open-Meteo"):
            st.success("🟢 Gratuito (Copernicus DEM 30m)")
        else:
            st.info("🟡 Google Maps Platform")

    if st.button("🚀 GENERAR PERFIL AUTOMÁTICO", type="primary", width="stretch"):
        n_samples = sample_count(distance)
        if elevation_provider == "Google Maps Elevation API (Requiere Key)":
            if not google_api_key:
                st.error("Ingresa la Google Maps API Key en la barra lateral.")
            else:
                try:
                    with st.spinner(f"Consultando Google Elevation ({n_samples} puntos)..."):
                        prof = google_elevation_profile(
                            google_api_key, cfg["lat_a"], cfg["lon_a"], cfg["lat_b"], cfg["lon_b"], n_samples
                        )
                    st.session_state.profile_df = prof
                    st.session_state.veg_df = None
                    st.success(f"Perfil generado exitosamente con {len(prof)} puntos de terreno (Google Elevation).")
                except Exception as exc:
                    st.error(f"No se pudo generar el perfil con Google Elevation: {exc}")
        else:
            try:
                with st.spinner(f"Consultando Open-Meteo Elevation / Copernicus DEM ({n_samples} puntos)..."):
                    prof = open_meteo_elevation_profile(
                        cfg["lat_a"], cfg["lon_a"], cfg["lat_b"], cfg["lon_b"], n_samples,
                        smooth=st.session_state.get("om_smoothing", True)
                    )
                st.session_state.profile_df = prof
                st.session_state.veg_df = None
                smooth_msg = " con reconstrucción sub-píxel" if st.session_state.get("om_smoothing", True) else ""
                st.success(f"Perfil generado exitosamente con {len(prof)} puntos de terreno (Open-Meteo Copernicus DEM{smooth_msg}).")
            except Exception as exc:
                st.error(f"No se pudo generar el perfil con Open-Meteo: {exc}")

with tab2:
    st.subheader("Perfil del enlace — estilo LINKPlanner")
    prof = st.session_state.profile_df
    if prof is None:
        st.warning("Genera primero el perfil en **1 · Sitios**.")
    else:
        calc = calculate_profile_geometry(prof, cfg, distance, freq, k_factor)
        st.session_state.profile_calc = calc
        vdf = st.session_state.veg_df
        chart_df = vdf if vdf is not None else calc.copy()
        if vdf is not None:
            chart_df = add_manual_obstacles(vdf, st.session_state.manual_obstacles)
            st.session_state.veg_df = chart_df

        c1, c2, c3 = st.columns(3)
        show_fresnel = c1.checkbox("Mostrar Fresnel 60%", True)
        show_veg = c2.checkbox("Mostrar arborización / obstáculos", True)
        show_unc = c3.checkbox("Mostrar incertidumbre de canopy", False)

        fig = go.Figure()
        add_profile_layers(fig, chart_df, show_vegetation=show_veg and "final_obstruction_top_m" in chart_df.columns, show_fresnel=show_fresnel, show_uncertainty=show_unc)
        add_obstacle_markers(fig, chart_df, st.session_state.manual_obstacles)
        fig.add_annotation(x=0, y=calc["los_m"].iloc[0], text=f"<b>{cfg['name_a']}</b><br>{cfg['height_a']:.1f} m", showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=12, color="#fff"))
        fig.add_annotation(x=distance, y=calc["los_m"].iloc[-1], text=f"<b>{cfg['name_b']}</b><br>{cfg['height_b']:.1f} m", showarrow=False, xanchor="right", yanchor="bottom", font=dict(size=12, color="#fff"))
        style_profile(fig, "Terreno + arborización real/modelada + LOS + Fresnel 60%")
        ymin = float(np.nanmin(chart_df["elevation_m"])) - 10
        ymax = float(np.nanmax(calc["fresnel_upper_m"])) + 15
        if "final_obstruction_top_m" in chart_df.columns and np.isfinite(chart_df["final_obstruction_top_m"]).any():
            ymax = max(ymax, float(np.nanmax(chart_df["final_obstruction_top_m"])) + 10)
        fig.update_yaxes(range=[ymin, ymax])
        st.plotly_chart(fig, width="stretch")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Distancia", f"{distance:.3f} km")
        c2.metric("Elevación A", f"{calc['elevation_m'].iloc[0]:.1f} m")
        c3.metric("Elevación B", f"{calc['elevation_m'].iloc[-1]:.1f} m")
        c4.metric("F1 máximo", f"{calc['f1_radius_m'].max():.1f} m")
        c5.metric("Fresnel 60% mínimo", f"{calc['clearance_terrain_m'].min():.1f} m")

        st.info("V5 evita el defecto visual de la V3: no rellena un único polígono sobre valores GEDI faltantes. Cada tramo de vegetación se dibuja como un parche independiente, por lo que ya no aparece el gran triángulo amarillo.")

with tab3:
    st.subheader("Arborización / obstáculos — datos automáticos + edición manual")
    prof = st.session_state.profile_df
    if prof is None:
        st.warning("Genera primero el perfil geográfico.")
    else:
        st.markdown("#### 1. Obtener arborización automática")
        st.caption("Fuente principal V5: ETH Global Canopy Height 2020, 10 m, generado a partir de Sentinel-2 y GEDI. Representa altura de copa estimada a nivel de píxel; no significa que el sistema conozca cada árbol individual hoy.")
        if st.button("🌳 ANALIZAR ARBORIZACIÓN 10 m", type="primary", width="stretch", disabled=not ar_enabled):
            try:
                with st.spinner("Consultando Earth Engine y el modelo global de altura de copa 10 m..."):
                    vraw = eth_canopy_profile(prof["lat"].tolist(), prof["lon"].tolist(), ee_project, include_uncertainty=True)
                    calc = st.session_state.get("profile_calc", calculate_profile_geometry(prof, cfg, distance, freq, k_factor))
                    out = build_vegetation_profile(prof, vraw, calc, st.session_state.exclusions)
                    out = apply_canopy_height_overrides(out, st.session_state.canopy_overrides)
                    out = apply_canopy_point_overrides(out, st.session_state.canopy_point_overrides)
                    out = add_manual_obstacles(out, st.session_state.manual_obstacles)
                    st.session_state.veg_df = out
                st.success(f"Canopy 10 m analizado. Puntos con vegetación/copa > 1 m: {int(out['vegetation_detected'].sum())} de {len(out)}.")
            except Exception as exc:
                st.warning(f"No se pudo acceder al modelo ETH 10 m. Se intentará el respaldo GEDI. Detalle: {exc}")
                try:
                    with st.spinner("Consultando GEDI como respaldo..."):
                        vraw = gedi_fallback_profile(prof["lat"].tolist(), prof["lon"].tolist(), ee_project)
                        calc = st.session_state.get("profile_calc", calculate_profile_geometry(prof, cfg, distance, freq, k_factor))
                        out = build_vegetation_profile(prof, vraw, calc, st.session_state.exclusions)
                        out = apply_canopy_height_overrides(out, st.session_state.canopy_overrides)
                        out = apply_canopy_point_overrides(out, st.session_state.canopy_point_overrides)
                        out = add_manual_obstacles(out, st.session_state.manual_obstacles)
                        st.session_state.veg_df = out
                    st.success("Se utilizó GEDI como respaldo. La resolución/continuidad será menor que la fuente ETH 10 m.")
                except Exception as exc2:
                    st.error(f"Tampoco fue posible consultar GEDI: {exc2}")

        st.markdown("#### 2. Quitar vegetación del cálculo")
        st.caption("Esto NO borra datos de Google/Earth Engine. Crea una exclusión local del proyecto, útil cuando verificas en campo que un tramo no tiene árboles o cuando quieres probar una condición alternativa.")
        exclusions = st.data_editor(
            st.session_state.exclusions,
            num_rows="dynamic",
            key="exclusions_editor",
            column_config={
                "inicio_km": st.column_config.NumberColumn("Inicio (km)", min_value=0.0, step=0.01),
                "fin_km": st.column_config.NumberColumn("Fin (km)", min_value=0.0, step=0.01),
            },
            width="stretch",
            hide_index=True,
        )
        if st.button("🧹 Aplicar exclusiones", width="stretch"):
            st.session_state.exclusions = exclusions.copy()
            if st.session_state.veg_df is not None:
                raw = st.session_state.veg_df.copy()
                raw = apply_exclusions(raw, st.session_state.exclusions)
                raw["canopy_top_m"] = raw["elevation_m"] + raw["canopy_height_m"].clip(lower=0)
                raw.loc[~raw["vegetation_detected"].fillna(False), "canopy_top_m"] = np.nan
                raw["los_clearance_m"] = raw["los_worst_m"] - raw["canopy_top_m"]
                raw["fresnel_clearance_m"] = raw["fresnel_lower_m"] - raw["canopy_top_m"]
                raw = apply_canopy_height_overrides(raw, st.session_state.canopy_overrides)
                raw = add_manual_obstacles(raw, st.session_state.manual_obstacles)
                st.session_state.veg_df = raw
            st.success("Exclusiones aplicadas.")

        # Defensive normalization: projects created with older versions can
        # restore `activo` as FLOAT when nulls were present. CheckboxColumn
        # requires boolean dtype.
        if "activo" in st.session_state.canopy_overrides.columns:
            st.session_state.canopy_overrides["activo"] = (
                st.session_state.canopy_overrides["activo"]
                .fillna(False).astype(bool)
            )

        st.markdown("#### 3. Modificar manualmente la altura de la vegetación automática")
        st.caption("Puedes sobrescribir la altura estimada por Earth Engine por tramos. La altura se mide sobre el terreno local. Usa 0 m para eliminar la vegetación automática en un tramo.")
        canopy_ed = st.data_editor(
            st.session_state.canopy_overrides,
            num_rows="dynamic",
            key="canopy_overrides_editor",
            column_config={
                "inicio_km": st.column_config.NumberColumn("Inicio (km)", min_value=0.0, step=0.01),
                "fin_km": st.column_config.NumberColumn("Fin (km)", min_value=0.0, step=0.01),
                "altura_m": st.column_config.NumberColumn("Altura manual sobre terreno (m)", min_value=0.0, step=0.5),
                "activo": st.column_config.CheckboxColumn("Activo"),
            },
            width="stretch", hide_index=True,
        )
        if st.button("🌳 Aplicar alturas manuales", width="stretch"):
            st.session_state.canopy_overrides = canopy_ed.copy()
            if st.session_state.veg_df is not None:
                tmp = apply_canopy_height_overrides(st.session_state.veg_df, st.session_state.canopy_overrides)
                st.session_state.veg_df = add_manual_obstacles(tmp, st.session_state.manual_obstacles)
            st.success("Alturas manuales de vegetación aplicadas al perfil.")

        st.markdown("#### 3. Agregar árboles, edificios, postes u otros obstáculos")
        st.caption("Los obstáculos manuales se superponen a la fuente automática. Puedes agregar, editar o eliminar filas.")
        manual = st.data_editor(
            st.session_state.manual_obstacles,
            num_rows="dynamic",
            key="manual_obstacles_editor",
            column_config={
                "nombre": st.column_config.TextColumn("Nombre"),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Árbol", "Vegetación", "Edificio", "Casa", "Torre", "Poste", "Muro", "Bodega", "Estructura", "Otro"]),
                "distancia_km": st.column_config.NumberColumn("Distancia desde A (km)", min_value=0.0, step=0.01),
                "altura_m": st.column_config.NumberColumn("Altura sobre terreno (m)", min_value=0.0, step=0.5),
                "ancho_m": st.column_config.NumberColumn("Ancho (m)", min_value=0.1, step=1.0),
                "activo": st.column_config.CheckboxColumn("Activo"),
            },
            width="stretch",
            hide_index=True,
        )
        if st.button("➕ Aplicar obstáculos manuales", width="stretch"):
            st.session_state.manual_obstacles = manual.copy()
            if st.session_state.veg_df is not None:
                tmp = apply_canopy_height_overrides(st.session_state.veg_df, st.session_state.canopy_overrides)
                st.session_state.veg_df = add_manual_obstacles(tmp, st.session_state.manual_obstacles)
            st.success("Obstáculos manuales aplicados al perfil.")

        vdf = st.session_state.veg_df
        if vdf is not None:
            chart = add_manual_obstacles(vdf, st.session_state.manual_obstacles)
            st.session_state.veg_df = chart
            fig = go.Figure()
            add_profile_layers(fig, chart, show_vegetation=True, show_fresnel=True, show_uncertainty=False)
            add_obstacle_markers(fig, chart, st.session_state.manual_obstacles)
            style_profile(fig, "Arborización automática + obstáculos manuales")
            ymin = float(np.nanmin(chart["elevation_m"])) - 10
            ymax = float(np.nanmax(chart["fresnel_upper_m"])) + 15
            if np.isfinite(chart["final_obstruction_top_m"]).any():
                ymax = max(ymax, float(np.nanmax(chart["final_obstruction_top_m"])) + 10)
            fig.update_yaxes(range=[ymin, ymax])
            st.plotly_chart(fig, width="stretch")

            detected = obstacle_table(chart)
            if not detected.empty:
                st.markdown("#### Puntos de vegetación que afectan el enlace")
                st.caption("Puedes cambiar directamente la altura de cualquier árbol/punto en la tabla. La altura se mide sobre el terreno local. Después pulsa Aplicar cambios.")
                detected_edit = detected.copy()
                detected_edit["altura_manual_m"] = detected_edit["canopy_height_m"].astype(float)
                detected_edit = detected_edit[["distance_km","lat","lon","elevation_m","canopy_height_m","altura_manual_m","canopy_top_m","los_clearance_m","fresnel_clearance_m","status"]]
                edited = st.data_editor(
                    detected_edit.round(2), num_rows="fixed", hide_index=True, width="stretch", key="affected_vegetation_editor",
                    column_config={
                        "distance_km": st.column_config.NumberColumn("Distancia (km)", disabled=True),
                        "lat": st.column_config.NumberColumn("Lat", disabled=True),
                        "lon": st.column_config.NumberColumn("Lon", disabled=True),
                        "elevation_m": st.column_config.NumberColumn("Terreno (m)", disabled=True),
                        "canopy_height_m": st.column_config.NumberColumn("Altura automática (m)", disabled=True),
                        "altura_manual_m": st.column_config.NumberColumn("ALTURA EDITABLE (m)", min_value=0.0, step=0.5),
                        "canopy_top_m": st.column_config.NumberColumn("Cota superior (m)", disabled=True),
                        "los_clearance_m": st.column_config.NumberColumn("Margen LOS (m)", disabled=True),
                        "fresnel_clearance_m": st.column_config.NumberColumn("Margen Fresnel (m)", disabled=True),
                        "status": st.column_config.TextColumn("Estado", disabled=True),
                    },
                )
                if st.button("🌳 Aplicar cambios de alturas desde esta tabla", key="apply_affected_tree_edits", type="primary", width="stretch"):
                    pov = edited[["distance_km","altura_manual_m"]].copy().rename(columns={"altura_manual_m":"altura_m"})
                    pov["activo"] = True
                    st.session_state.canopy_point_overrides = pov
                    if st.session_state.veg_df is not None:
                        base = st.session_state.veg_df.copy()
                        base = apply_canopy_point_overrides(base, pov)
                        base = add_manual_obstacles(base, st.session_state.manual_obstacles)
                        st.session_state.veg_df = base
                    st.success("Alturas de vegetación actualizadas desde la tabla.")
                    st.rerun()
                detected_now = st.session_state.get("veg_df")
                detected = obstacle_table(detected_now) if detected_now is not None else detected
                worst_los = detected.sort_values("los_clearance_m").iloc[0]
                worst_f = detected.sort_values("fresnel_clearance_m").iloc[0]
                q1, q2, q3, q4 = st.columns(4)
                q1.metric("Crítico LOS", f"{worst_los.distance_km:.3f} km")
                q2.metric("Margen LOS", f"{worst_los.los_clearance_m:.1f} m")
                q3.metric("Crítico Fresnel", f"{worst_f.distance_km:.3f} km")
                q4.metric("Margen Fresnel", f"{worst_f.fresnel_clearance_m:.1f} m")
            else:
                st.info("No hay vegetación automática activa en el perfil. Los obstáculos manuales siguen siendo válidos.")

            kml = df_to_kml(chart, cfg["name_a"], cfg["name_b"], cfg["lat_a"], cfg["lon_a"], cfg["lat_b"], cfg["lon_b"], detected, st.session_state.manual_obstacles)
            st.download_button("🌍 Descargar KML", kml, "SAF_Link_Planner_V5.kml", "application/vnd.google-earth.kml+xml", width="stretch")

            with st.expander("Ver datos completos"):
                st.dataframe(chart.round(3), width="stretch", hide_index=True)

with tab4:
    st.subheader("Presupuesto RF")
    fspl = fspl_km_ghz(distance, freq)
    eirp = tx_power + gain_a
    rx = tx_power + gain_a + gain_b - fspl - other_losses
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("FSPL", f"{fspl:.2f} dB")
    m2.metric("EIRP A", f"{eirp:.2f} dBm")
    m3.metric("RX estimado", f"{rx:.2f} dBm")
    m4.metric("Ganancia antena", f"{gain_a:.1f} dBi / {gain_band}")
    st.info("El cálculo RF sigue siendo de prefactibilidad. V5 no inventa una matriz MCS/throughput que no esté disponible en los datos del equipo.")

with tab5:
    st.subheader("Resultado ejecutivo")
    p = st.session_state.get("profile_calc")
    v = st.session_state.get("veg_df")
    if p is None:
        st.warning("Genera el perfil automático primero.")
    else:
        min_clear = float(p["clearance_terrain_m"].min())
        rf_fspl = fspl_km_ghz(distance, freq)
        rf_rx = tx_power + gain_a + gain_b - rf_fspl - other_losses
        min_los = np.nan
        if v is not None:
            active = np.isfinite(v.get("final_obstruction_top_m", pd.Series(dtype=float)))
            if active.any():
                min_los = float((v.loc[active, "los_worst_m"] - v.loc[active, "final_obstruction_top_m"]).min())
        if np.isfinite(min_los) and min_los < 0:
            status = "🔴 REQUIERE INTERVENCIÓN — obstáculo invade LOS"
        elif min_clear < 0:
            status = "🟠 REQUIERE REVISIÓN — Fresnel 60% comprometida"
        else:
            status = "🟢 GEOMÉTRICAMENTE DESPEJADO"
        st.markdown(f"# {status}")
        a, b, c, d = st.columns(4)
        a.metric("Distancia", f"{distance:.3f} km")
        b.metric("RX estimado", f"{rf_rx:.1f} dBm")
        c.metric("Fresnel 60%", f"{min_clear:.1f} m")
        d.metric("Capacidad objetivo", f"{required_capacity:.0f} Mbps")
        if v is not None and np.isfinite(v.get("final_obstruction_top_m", pd.Series(dtype=float))).any():
            tmp = v[np.isfinite(v["final_obstruction_top_m"])].copy()
            tmp["final_los_clearance_m"] = tmp["los_worst_m"] - tmp["final_obstruction_top_m"]
            worst = tmp.sort_values("final_los_clearance_m").iloc[0]
            st.warning(
                f"Obstáculo crítico: {worst.distance_km:.3f} km desde A, "
                f"cota superior {worst.final_obstruction_top_m:.1f} m, "
                f"margen LOS {worst.final_los_clearance_m:.1f} m."
            )
        st.markdown("### Qué incorpora realmente V5")
        st.write("• Biblioteca de radios y antenas con importación de datasheets PDF.")
        st.write("• Canopy continuo de 10 m y obstáculos manuales de múltiples tipos.")
        st.write("• Edificios, casas, torres, postes, muros, bodegas, estructuras y obstáculos personalizados.")
        st.write("• Selección independiente de radio y antena en cada extremo.")
        st.write("• Los catálogos se guardan localmente y pueden viajar con la versión portable.")


def _parse_bandwidths_text(value):
    vals = []
    for token in re.split(r"[,;\s]+", str(value or "")):
        try:
            n = int(float(token))
            if n > 0:
                vals.append(n)
        except Exception:
            pass
    return sorted(set(vals))


def _format_rx_sensitivity(value):
    if isinstance(value, dict):
        return "; ".join(f"{k}:{v}" for k, v in sorted(value.items(), key=lambda kv: float(kv[0])))
    return str(value or "")


def _parse_rx_sensitivity(value):
    out = {}
    for part in re.split(r"[;,]+", str(value or "")):
        if not part.strip():
            continue
        m = re.match(r"\s*(\d+(?:\.\d+)?)\s*[:=]\s*(-?\d+(?:\.\d+)?)", part.strip())
        if m:
            try:
                out[int(float(m.group(1)))] = float(m.group(2))
            except Exception:
                pass
    return out


def _radio_extra_dict(value):
    if not value or not str(value).strip():
        return {}
    try:
        obj = __import__('json').loads(value)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


with tab6:
    st.subheader("🌍 Exportación KMZ — vista tipo LINKPlanner")
    st.caption("Esta es ahora la única sección de descarga del KMZ. El archivo se genera desde el proyecto actual cada vez que abres esta pestaña.")
    v = st.session_state.get("veg_df")
    if v is None or v.empty:
        st.warning("Primero genera el perfil de arborización/terreno en la pestaña 2. Después vuelve aquí para descargar el KMZ.")
    else:
        crit = obstacle_table(v)
        kml_bytes = rich_kml(v, cfg, radio_a, radio_b, ant_a, ant_b, crit, st.session_state.manual_obstacles, st.session_state.project_rf)
        kmz_data = create_kmz(kml_bytes)
        kmz_name = re.sub(r"[^A-Za-z0-9_-]+", "_", st.session_state.current_project_name.strip()) or "SAF_Link_Planner"
        st.markdown("### Qué contiene este KMZ")
        e1,e2,e3,e4 = st.columns(4)
        e1.metric("LOS", "Magenta")
        e2.metric("Fresnel 60%", "2 vistas")
        e3.metric("Alturas A/B", "Cota absoluta")
        e4.metric("Advertencias", "Máx. 3")
        st.info("La zona Fresnel ya no se exporta como un único polígono gigante. Se divide en paneles para que Google Earth la renderice correctamente: proyección sobre terreno + cortina vertical. Los árboles individuales no se exportan como pines.")
        st.download_button("⬇️ DESCARGAR KMZ CORREGIDO", kmz_data, f"{kmz_name}_LINKPLANNER.kmz", "application/vnd.google-earth.kmz", key="download_kmz_v555", width="stretch", type="primary")
        st.caption("Al abrir el KMZ en Google Earth: 01 Enlace, 03 Fresnel sobre terreno y 04 Fresnel vertical deben estar visibles. 05 Perfil terreno 3D y 07 Obstáculos manuales 3D quedan disponibles como capas.")

with tab7:
    st.subheader("📚 Biblioteca de radios y antenas")
    st.caption("Puedes importar un datasheet PDF y revisar los datos detectados, pero también puedes crear y editar antenas manualmente. Esto es útil cuando el fabricante no publica una tabla fácil de interpretar.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 📡 Importar radio desde PDF")
        pdf_radio = st.file_uploader("Datasheet del radio", type=["pdf"], key="pdf_radio")
        if pdf_radio is not None and st.button("🔎 Analizar datasheet del radio", key="parse_radio", type="primary"):
            try:
                parsed, _ = parse_radio_pdf(pdf_radio.getvalue(), pdf_radio.name)
                st.session_state['parsed_radio'] = parsed
                st.success("Datasheet analizado. Revisa los campos antes de guardarlo.")
            except Exception as exc:
                st.error(f"No se pudo analizar el PDF: {exc}")
        if st.session_state.get('parsed_radio'):
            r = st.session_state['parsed_radio']
            st.markdown("#### Datos detectados")
            r['manufacturer'] = st.text_input("Fabricante", r.get('manufacturer',''), key='pr_man')
            r['model'] = st.text_input("Modelo", r.get('model',''), key='pr_model')
            r['frequency_min_ghz'] = st.number_input("Frecuencia mínima (GHz)", value=float(r.get('frequency_min_ghz') or 0), key='pr_fmin')
            r['frequency_max_ghz'] = st.number_input("Frecuencia máxima (GHz)", value=float(r.get('frequency_max_ghz') or 0), key='pr_fmax')
            r['max_output_power_dbm'] = st.number_input("Potencia TX máxima (dBm)", value=float(r.get('max_output_power_dbm') or 0), key='pr_tx')
            r['integrated_antenna_gain_dbi'] = st.number_input("Ganancia integrada (dBi)", value=float(r.get('integrated_antenna_gain_dbi') or 0), key='pr_gain')
            r['throughput_gbps'] = st.number_input("Throughput PTP (Gbps)", value=float(r.get('throughput_gbps') or 0), key='pr_thr')
            r['mimo'] = st.text_input("MIMO", r.get('mimo',''), key='pr_mimo')
            r['modulation'] = st.text_input("Modulación", r.get('modulation',''), key='pr_mod')
            if st.button("💾 Guardar radio en biblioteca", key='save_radio'):
                data = [x for x in st.session_state.radios if not (_radio_label(x)==_radio_label(r))]
                data.append(radio_to_dict(r)); st.session_state.radios=data; save_json(RADIOS_FILE,data); st.success(f"Guardado: {_radio_label(r)}")

    st.divider()
    st.markdown("## 🛠️ Agregar / editar radio manualmente")
    st.info("Todos los parámetros de la biblioteca de radios pueden modificarse manualmente. Los campos adicionales permiten guardar parámetros propios de cualquier fabricante sin perderlos.")
    radios_now = st.session_state.radios
    radio_action = st.radio("Operación de radio", ["➕ Agregar nuevo radio", "✏️ Editar radio existente"], horizontal=True, key="radio_action")
    if radio_action == "✏️ Editar radio existente" and radios_now:
        radio_edit_labels = [_radio_label(r) for r in radios_now]
        radio_edit_label = st.selectbox("Seleccione el radio", radio_edit_labels, key="radio_edit_select")
        radio_base = dict(radios_now[radio_edit_labels.index(radio_edit_label)])
    elif radio_action == "✏️ Editar radio existente":
        st.warning("No hay radios guardados. Agrega el primero manualmente.")
        radio_base = {}
    else:
        radio_base = {}

    radio_suffix = "new" if radio_action.startswith("➕") else "edit_" + str(radio_base.get('manufacturer','')) + "_" + str(radio_base.get('model',''))
    radio_suffix = re.sub(r"[^A-Za-z0-9_]+", "_", radio_suffix)
    with st.form(f"manual_radio_form_{radio_suffix}"):
        q1,q2,q3 = st.columns(3)
        with q1:
            rmfg = st.text_input("Fabricante *", str(radio_base.get('manufacturer','')))
            rmodel = st.text_input("Modelo / referencia *", str(radio_base.get('model','')))
            rsource = st.text_input("Fuente / datasheet", str(radio_base.get('source_file','Manual')))
            rfmin = st.number_input("Frecuencia mínima (GHz)", min_value=0.0, value=float(radio_base.get('frequency_min_ghz') or 0.0), step=0.01)
            rfmax = st.number_input("Frecuencia máxima (GHz)", min_value=0.0, value=float(radio_base.get('frequency_max_ghz') or 0.0), step=0.01)
        with q2:
            rtx = st.number_input("Potencia TX máxima (dBm)", min_value=-20.0, max_value=100.0, value=float(radio_base.get('max_output_power_dbm') or 0.0), step=0.1)
            rgain = st.number_input("Ganancia de antena integrada (dBi)", min_value=0.0, max_value=60.0, value=float(radio_base.get('integrated_antenna_gain_dbi') or 0.0), step=0.1)
            rthr = st.number_input("Throughput PTP (Gbps)", min_value=0.0, max_value=100.0, value=float(radio_base.get('throughput_gbps') or 0.0), step=0.01)
            rbw = st.text_input("Anchos de canal (MHz)", ", ".join(map(str, radio_base.get('bandwidths_mhz') or [])), help="Ejemplo: 20, 40, 80, 160")
            rmimo = st.text_input("MIMO", str(radio_base.get('mimo','')))
        with q3:
            rmod = st.text_input("Modulación", str(radio_base.get('modulation','')))
            rrx = st.text_input("Sensibilidad RX por canal", _format_rx_sensitivity(radio_base.get('rx_sensitivity_dbm',{})), help="Formato: 20:-87; 40:-84; 80:-81; 160:-77")
            rnotes = st.text_area("Notas", str(radio_base.get('notes','')), height=115)
            rextra = st.text_area("Parámetros adicionales (JSON)", str(radio_base.get('extra_parameters_json','')), height=115, help='Ejemplo: {"EIRP_max_dBm": 36, "polarizacion": "Dual"}')
        radio_submitted = st.form_submit_button("💾 Guardar radio", type="primary", width="stretch")

    if radio_submitted:
        if not rmfg.strip() or not rmodel.strip():
            st.error("Fabricante y modelo/referencia son obligatorios.")
        else:
            extra = _radio_extra_dict(rextra)
            new_radio = radio_to_dict({
                'manufacturer': rmfg.strip(), 'model': rmodel.strip(), 'source_file': rsource.strip() or 'Manual',
                'frequency_min_ghz': rfmin, 'frequency_max_ghz': rfmax, 'max_output_power_dbm': rtx,
                'integrated_antenna_gain_dbi': rgain, 'throughput_gbps': rthr, 'bandwidths_mhz': _parse_bandwidths_text(rbw),
                'mimo': rmimo, 'modulation': rmod, 'rx_sensitivity_dbm': _parse_rx_sensitivity(rrx),
                'notes': rnotes, 'extra_parameters_json': __import__('json').dumps(extra, ensure_ascii=False) if extra else ''
            })
            new_radio.update(extra)
            data = [x for x in st.session_state.radios if _radio_label(x) != _radio_label(new_radio)]
            data.append(new_radio)
            st.session_state.radios = data
            save_json(RADIOS_FILE, data)
            st.success(f"Radio guardado: {_radio_label(new_radio)}")
            st.rerun()

    if radio_action == "✏️ Editar radio existente" and radios_now:
        if st.button("🗑️ Eliminar radio seleccionado", key="delete_radio"):
            data = [x for x in st.session_state.radios if _radio_label(x) != radio_edit_label]
            st.session_state.radios = data
            save_json(RADIOS_FILE, data)
            st.success("Radio eliminado de la biblioteca.")
            st.rerun()

    with col2:
        st.markdown("### 📡 Importar antenas desde PDF")
        pdf_ant = st.file_uploader("Datasheet de antenas", type=["pdf"], key="pdf_ant")
        if pdf_ant is not None and st.button("🔎 Analizar datasheet de antenas", key="parse_ant", type="primary"):
            try:
                parsed, _ = parse_antenna_pdf(pdf_ant.getvalue(), pdf_ant.name)
                st.session_state['parsed_antennas'] = parsed
                st.success(f"Se detectaron {len(parsed)} antenas. Revisa o edita los datos antes de guardarlas.")
            except Exception as exc:
                st.error(f"No se pudo analizar el PDF: {exc}")
        parsed_ants = st.session_state.get('parsed_antennas', [])
        if parsed_ants:
            st.dataframe(pd.DataFrame(parsed_ants), width='stretch', hide_index=True)
            if st.button("💾 Guardar antenas detectadas", key='save_ants'):
                data=list(st.session_state.antennas)
                for a in parsed_ants:
                    aa = antenna_to_dict(a)
                    data=[x for x in data if _antenna_label(x)!=_antenna_label(aa)]
                    data.append(aa)
                st.session_state.antennas=data; save_json(ANTENNAS_FILE,data); st.success(f"Biblioteca actualizada: {len(data)} antenas.")

    st.divider()
    st.markdown("## 🛠️ Agregar / editar antena manualmente")
    st.info("Aquí puedes registrar cualquier antena aunque el PDF no pueda ser interpretado. Los campos importantes para el cálculo son frecuencia, ganancia y ancho de haz; los demás quedan almacenados como información mecánica y de instalación.")

    ants = st.session_state.antennas
    action = st.radio("Operación", ["➕ Agregar nueva antena", "✏️ Editar antena existente"], horizontal=True, key="ant_action")
    if action == "✏️ Editar antena existente" and ants:
        edit_labels = [_antenna_label(a) for a in ants]
        edit_label = st.selectbox("Seleccione la antena", edit_labels, key="ant_edit_select")
        base = dict(ants[edit_labels.index(edit_label)])
    elif action == "✏️ Editar antena existente" and not ants:
        st.warning("No hay antenas guardadas. Agrega la primera manualmente.")
        base = {}
    else:
        base = {}

    form_suffix = "new" if action.startswith("➕") else "edit_" + str(base.get('manufacturer','')) + "_" + str(base.get('model',''))
    form_suffix = re.sub(r"[^A-Za-z0-9_]+", "_", form_suffix)
    with st.form(f"manual_antenna_form_{form_suffix}"):
        c1,c2,c3 = st.columns(3)
        with c1:
            mfg = st.text_input("Fabricante *", str(base.get('manufacturer','')))
            model = st.text_input("Modelo / referencia *", str(base.get('model','')))
            source = st.text_input("Fuente / datasheet", str(base.get('source_file','Manual')))
            fmin = st.number_input("Frecuencia mínima (GHz)", min_value=0.0, value=float(base.get('frequency_min_ghz') or 0.0), step=0.01)
            fmax = st.number_input("Frecuencia máxima (GHz)", min_value=0.0, value=float(base.get('frequency_max_ghz') or 0.0), step=0.01)
        with c2:
            gain = st.number_input("Ganancia usada en cálculo (dBi) *", min_value=0.0, max_value=60.0, value=float(base.get('gain_dbi') or 0.0), step=0.1)
            gain_low = st.number_input("Ganancia banda baja (dBi)", min_value=0.0, max_value=60.0, value=float(base.get('gain_low_dbi') or 0.0), step=0.1)
            gain_mid = st.number_input("Ganancia banda media (dBi)", min_value=0.0, max_value=60.0, value=float(base.get('gain_mid_dbi') or 0.0), step=0.1)
            gain_high = st.number_input("Ganancia banda alta (dBi)", min_value=0.0, max_value=60.0, value=float(base.get('gain_high_dbi') or 0.0), step=0.1)
            beam = st.number_input("Ancho de haz / Beamwidth (°)", min_value=0.0, max_value=180.0, value=float(base.get('beamwidth_deg') or 0.0), step=0.1)
            diameter = st.number_input("Diámetro (m)", min_value=0.0, max_value=20.0, value=float(base.get('diameter_m') or 0.0), step=0.01)
        with c3:
            weight = st.number_input("Peso (kg)", min_value=0.0, max_value=5000.0, value=float(base.get('weight_kg') or 0.0), step=0.1)
            shield = st.checkbox("Antena blindada / Deep Dish", value=_is_shielded(base), key=f"manual_ant_shield_{form_suffix}")
            polarization = st.text_input("Polarización", str(base.get('polarization','')))
            connector = st.text_input("Conector", str(base.get('connector','')))
            mast = st.text_input("Fijación en mástil", str(base.get('mast_mount','')))
            material = st.text_input("Material", str(base.get('material','')))

        st.markdown("#### 📐 Dimensiones y montaje")
        d1,d2,d3,d4 = st.columns(4)
        with d1: dim_a = st.number_input("Dimensión A (mm)", min_value=0.0, value=float(base.get('dimension_a_mm') or 0.0), step=1.0)
        with d2: dim_b = st.number_input("Dimensión B (mm)", min_value=0.0, value=float(base.get('dimension_b_mm') or 0.0), step=1.0)
        with d3: dim_c = st.number_input("Dimensión C (mm)", min_value=0.0, value=float(base.get('dimension_c_mm') or 0.0), step=1.0)
        with d4: packed_weight = st.number_input("Peso embalado (kg)", min_value=0.0, value=float(base.get('packed_weight_kg') or 0.0), step=0.1)

        st.markdown("#### 🧭 Ajustes y características RF")
        e1,e2,e3,e4 = st.columns(4)
        with e1: elev_adj = st.text_input("Ajuste de elevación", str(base.get('elevation_adjustment','')))
        with e2: az_adj = st.text_input("Ajuste de azimut", str(base.get('azimuth_adjustment','')))
        with e3: pol_adj = st.text_input("Ajuste de polarización", str(base.get('polarization_adjustment','')))
        with e4: ftb = st.text_input("Relación frente-dorso", str(base.get('front_to_back_ratio_db','')))
        r1,r2,r3,r4 = st.columns(4)
        with r1: xpd = st.text_input("XPD / polarización cruzada", str(base.get('xpd_db','')))
        with r2: vswr = st.text_input("VSWR", str(base.get('vswr','')))
        with r3: isolation = st.text_input("Aislamiento entre puertos", str(base.get('port_isolation_db','')))
        with r4: wind_area = st.number_input("Área al viento (m²)", min_value=0.0, value=float(base.get('wind_area_m2') or 0.0), step=0.001, format="%.3f")

        st.markdown("#### 🌬️ Resistencia al viento")
        w1,w2 = st.columns(2)
        with w1: op_wind = st.number_input("Viento operativo (km/h)", min_value=0.0, value=float(base.get('operational_wind_kmh') or 0.0), step=1.0)
        with w2: surv_wind = st.number_input("Viento de supervivencia (km/h)", min_value=0.0, value=float(base.get('survival_wind_kmh') or 0.0), step=1.0)
        notes = st.text_area("Notas", str(base.get('notes','')))

        submitted = st.form_submit_button("💾 Guardar antena", type="primary", width="stretch")

    if submitted:
        if not mfg.strip() or not model.strip():
            st.error("Fabricante y modelo/referencia son obligatorios.")
        else:
            new_ant = antenna_to_dict({
                'manufacturer':mfg.strip(), 'model':model.strip(), 'source_file':source.strip() or 'Manual',
                'frequency_min_ghz':fmin, 'frequency_max_ghz':fmax, 'diameter_m':diameter,
                'gain_dbi':gain, 'gain_low_dbi':gain_low, 'gain_mid_dbi':gain_mid, 'gain_high_dbi':gain_high,
                'beamwidth_deg':beam, 'polarization':polarization, 'shielding':'Sí' if shield else 'No',
                'front_to_back_ratio_db':ftb, 'xpd_db':xpd, 'vswr':vswr, 'port_isolation_db':isolation,
                'connector':connector, 'elevation_adjustment':elev_adj, 'azimuth_adjustment':az_adj,
                'polarization_adjustment':pol_adj, 'weight_kg':weight, 'mast_mount':mast,
                'operational_wind_kmh':op_wind, 'survival_wind_kmh':surv_wind, 'wind_area_m2':wind_area,
                'material':material, 'dimension_a_mm':dim_a, 'dimension_b_mm':dim_b, 'dimension_c_mm':dim_c,
                'packed_weight_kg':packed_weight, 'notes':notes
            })
            data = list(st.session_state.antennas)
            data = [x for x in data if _antenna_label(x) != _antenna_label(new_ant)]
            data.append(new_ant)
            st.session_state.antennas = data
            save_json(ANTENNAS_FILE, data)
            st.success(f"Antena guardada: {_antenna_label(new_ant)}")
            st.rerun()

    if action == "✏️ Editar antena existente" and ants:
        st.markdown("### 🗑️ Eliminar antena")
        if st.button("Eliminar la antena seleccionada", key="delete_ant", type="secondary"):
            data = [x for x in st.session_state.antennas if _antenna_label(x) != edit_label]
            st.session_state.antennas = data
            save_json(ANTENNAS_FILE, data)
            st.success("Antena eliminada de la biblioteca.")
            st.rerun()

    st.divider()
    st.markdown("### Radios disponibles")
    if st.session_state.radios:
        st.dataframe(pd.DataFrame(st.session_state.radios), width='stretch', hide_index=True)
    st.markdown("### Antenas disponibles")
    if st.session_state.antennas:
        st.dataframe(pd.DataFrame(st.session_state.antennas), width='stretch', hide_index=True)
    st.info("Los catálogos se guardan localmente en data/. La biblioteca viaja con la versión portable; las credenciales de Google Earth Engine no se copian.")

st.divider()
st.caption(
    "SAF Link Planner V5.5.5 · Terreno: Open-Meteo (Copernicus DEM 30m) / Google Elevation API · Canopy principal: ETH Global Canopy Height 2020 (10 m), "
    "Sentinel-2 + GEDI · Respaldo: NASA GEDI L2A raster · LOS/Fresnel/curvatura: cálculo propio. "
    "La vegetación remota es una estimación y debe validarse en campo para diseño definitivo."
)
