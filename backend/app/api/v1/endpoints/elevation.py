"""Endpoints REST para cálculo de perfil de elevación y despeje topográfico."""

from fastapi import APIRouter, HTTPException, Depends
from backend.app.schemas.link_request import ProfileRequest
from backend.app.schemas.profile_response import ProfileSummaryResponse, ProfilePointResponse
from backend.app.services.geo_service import haversine, bearing, fspl_km_ghz, calculate_link_geometry
from backend.app.services.elevation_service import get_open_meteo_profile, get_google_profile
from backend.app.core.config import settings

router = APIRouter()


@router.post("/profile", response_model=ProfileSummaryResponse, summary="Generar perfil topográfico del enlace")
def generate_profile(req: ProfileRequest):
    # 1. Distancia geodésica y azimuts
    dist_km = haversine(req.lat_a, req.lon_a, req.lat_b, req.lon_b)
    az_ab = bearing(req.lat_a, req.lon_a, req.lat_b, req.lon_b)
    az_ba = bearing(req.lat_b, req.lon_b, req.lat_a, req.lon_a)
    fspl = fspl_km_ghz(dist_km, req.frequency_ghz)

    # 2. Consultar elevación según el proveedor seleccionado
    try:
        if req.elevation_provider.lower().startswith("google"):
            if not settings.GOOGLE_MAPS_API_KEY:
                raise HTTPException(status_code=400, detail="Falta la Google Maps API Key configurada.")
            df = get_google_profile(
                settings.GOOGLE_MAPS_API_KEY,
                req.lat_a, req.lon_a, req.lat_b, req.lon_b, req.samples
            )
        else:
            df = get_open_meteo_profile(
                req.lat_a, req.lon_a, req.lat_b, req.lon_b,
                samples=req.samples, apply_smoothing=req.apply_smoothing
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error consultando proveedor de elevación: {exc}")

    # 3. Calcular geometría (LOS, Fresnel, Curvatura)
    calc_df = calculate_link_geometry(
        df,
        height_a=req.height_a,
        height_b=req.height_b,
        distance_km=dist_km,
        freq_ghz=req.frequency_ghz,
        k_factor=req.k_factor,
    )

    # 4. Formatear puntos de respuesta
    points = []
    for row in calc_df.itertuples(index=False):
        points.append(ProfilePointResponse(
            sample=int(row.sample),
            lat=float(row.lat),
            lon=float(row.lon),
            distance_km=float(row.distance_km),
            elevation_m=float(row.elevation_m),
            los_m=float(getattr(row, "los_m", 0.0)),
            los_worst_m=float(getattr(row, "los_worst_m", 0.0)),
            fresnel_upper_m=float(getattr(row, "fresnel_upper_m", 0.0)),
            fresnel_lower_m=float(getattr(row, "fresnel_lower_m", 0.0)),
            fresnel_60_m=float(getattr(row, "fresnel_60_m", 0.0)),
            canopy_height_m=None,
            canopy_top_m=None,
            vegetation_detected=False,
            status="Despejado",
        ))

    min_los = float(calc_df["clearance_terrain_m"].min()) if "clearance_terrain_m" in calc_df.columns else None

    return ProfileSummaryResponse(
        distance_km=round(dist_km, 3),
        azimuth_ab_deg=round(az_ab, 2),
        azimuth_ba_deg=round(az_ba, 2),
        fspl_db=round(fspl, 2),
        min_clearance_los_m=round(min_los, 2) if min_los is not None else None,
        min_clearance_fresnel_m=None,
        is_line_of_sight_clear=bool(min_los is not None and min_los >= 0),
        total_samples=len(points),
        elevation_provider=req.elevation_provider,
        points=points,
    )
