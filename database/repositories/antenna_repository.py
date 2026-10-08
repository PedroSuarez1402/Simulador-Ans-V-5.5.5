"""Repositorio de Antenas (Capa de Persistencia).
Maneja operaciones CRUD sobre la tabla 'antennas' en MySQL con fallback automático a JSON.
"""

import json
from pathlib import Path
from database.connection import get_db

DATA_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "antennas.json"


class AntennaRepository:
    @staticmethod
    def get_all():
        """Obtiene todas las antenas de la base de datos SQL. Si la BD no está disponible, lee de JSON."""
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM antennas ORDER BY manufacturer ASC, model ASC;")
                    return cur.fetchall()
        except Exception:
            if DATA_JSON.exists():
                try:
                    return json.loads(DATA_JSON.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return []

    @staticmethod
    def get_by_id(antenna_id):
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM antennas WHERE id = %s;", (antenna_id,))
                    return cur.fetchone()
        except Exception:
            return None

    @staticmethod
    def save(antenna_data):
        sql = """
        INSERT INTO antennas (
            manufacturer, model, gain_dbi, gain_low_dbi, gain_mid_dbi, gain_high_dbi,
            frequency_min_ghz, frequency_max_ghz, beamwidth_deg, polarization,
            front_to_back_ratio_db, xpd_db, diameter_m, weight_kg, packed_weight_kg,
            wind_area_m2, operational_wind_kmh, survival_wind_kmh, vswr, port_isolation_db,
            connector, material, mast_mount, elevation_adjustment, azimuth_adjustment,
            polarization_adjustment, dimension_a_mm, dimension_b_mm, dimension_c_mm,
            source_file, notes
        ) VALUES (
            %(manufacturer)s, %(model)s, %(gain_dbi)s, %(gain_low_dbi)s, %(gain_mid_dbi)s, %(gain_high_dbi)s,
            %(frequency_min_ghz)s, %(frequency_max_ghz)s, %(beamwidth_deg)s, %(polarization)s,
            %(front_to_back_ratio_db)s, %(xpd_db)s, %(diameter_m)s, %(weight_kg)s, %(packed_weight_kg)s,
            %(wind_area_m2)s, %(operational_wind_kmh)s, %(survival_wind_kmh)s, %(vswr)s, %(port_isolation_db)s,
            %(connector)s, %(material)s, %(mast_mount)s, %(elevation_adjustment)s, %(azimuth_adjustment)s,
            %(polarization_adjustment)s, %(dimension_a_mm)s, %(dimension_b_mm)s, %(dimension_c_mm)s,
            %(source_file)s, %(notes)s
        ) ON DUPLICATE KEY UPDATE
            manufacturer = VALUES(manufacturer),
            gain_dbi = VALUES(gain_dbi),
            gain_low_dbi = VALUES(gain_low_dbi),
            gain_mid_dbi = VALUES(gain_mid_dbi),
            gain_high_dbi = VALUES(gain_high_dbi),
            frequency_min_ghz = VALUES(frequency_min_ghz),
            frequency_max_ghz = VALUES(frequency_max_ghz),
            beamwidth_deg = VALUES(beamwidth_deg),
            polarization = VALUES(polarization),
            front_to_back_ratio_db = VALUES(front_to_back_ratio_db),
            xpd_db = VALUES(xpd_db),
            diameter_m = VALUES(diameter_m),
            weight_kg = VALUES(weight_kg),
            packed_weight_kg = VALUES(packed_weight_kg),
            wind_area_m2 = VALUES(wind_area_m2),
            operational_wind_kmh = VALUES(operational_wind_kmh),
            survival_wind_kmh = VALUES(survival_wind_kmh),
            vswr = VALUES(vswr),
            port_isolation_db = VALUES(port_isolation_db),
            connector = VALUES(connector),
            material = VALUES(material),
            mast_mount = VALUES(mast_mount),
            elevation_adjustment = VALUES(elevation_adjustment),
            azimuth_adjustment = VALUES(azimuth_adjustment),
            polarization_adjustment = VALUES(polarization_adjustment),
            dimension_a_mm = VALUES(dimension_a_mm),
            dimension_b_mm = VALUES(dimension_b_mm),
            dimension_c_mm = VALUES(dimension_c_mm),
            source_file = VALUES(source_file),
            notes = VALUES(notes);
        """
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, antenna_data)
                return cur.lastrowid
