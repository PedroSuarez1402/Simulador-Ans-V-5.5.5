"""Pruebas unitarias para fórmulas geodésicas y de radiofrecuencia."""

import math
from backend.app.services.geo_service import haversine, bearing, fspl_km_ghz, fresnel_radius_m


def test_haversine_known_distance():
    # Coordenadas conocidas: Bogotá a Medellín (~240 km)
    dist = haversine(4.7110, -74.0721, 6.2442, -75.5812)
    assert 235.0 < dist < 250.0


def test_bearing_cardinal_directions():
    # Punto A hacia el Norte exacto
    az_north = bearing(0.0, 0.0, 1.0, 0.0)
    assert math.isclose(az_north, 0.0, abs_tol=0.1)

    # Punto A hacia el Este exacto
    az_east = bearing(0.0, 0.0, 0.0, 1.0)
    assert math.isclose(az_east, 90.0, abs_tol=0.1)


def test_fspl_calculation():
    # FSPL a 1 km y 1 GHz = 92.45 dB
    fspl = fspl_km_ghz(1.0, 1.0)
    assert math.isclose(fspl, 92.45, abs_tol=0.1)


def test_fresnel_radius_symmetry():
    # El radio de Fresnel es máximo en el punto medio (d1 == d2)
    f_mid = fresnel_radius_m(5.0, 5.0, 5.8)
    f_edge = fresnel_radius_m(1.0, 9.0, 5.8)
    assert f_mid > f_edge
    assert f_mid > 0.0
