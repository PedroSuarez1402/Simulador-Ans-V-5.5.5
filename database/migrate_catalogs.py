"""Script de Migración: Catalogo JSON a Base de Datos SQL (Fase 1).
Lee data/radios.json, data/antennas.json y los proyectos .slp.json e inserta los registros en MySQL.
"""

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
try:
    from database.connection import get_db, init_database, test_connection
except ImportError:
    from connection import get_db, init_database, test_connection

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RADIOS_FILE = DATA_DIR / "radios.json"
ANTENNAS_FILE = DATA_DIR / "antennas.json"
PROJECTS_DIR = DATA_DIR / "projects"


import re

def clean_decimal(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(',', '.').strip()
    if not s:
        return None
    m = re.search(r'[-+]?\d*\.?\d+', s)
    if m:
        try:
            return float(m.group(0))
        except Exception:
            return None
    return None


def migrate_radios():
    if not RADIOS_FILE.exists():
        print(f"⚠️ Archivo no encontrado: {RADIOS_FILE}")
        return 0

    radios = json.loads(RADIOS_FILE.read_text(encoding="utf-8"))
    count = 0

    sql = """
    INSERT INTO radios (
        manufacturer, model, frequency_min_ghz, frequency_max_ghz,
        max_output_power_dbm, integrated_antenna_gain_dbi, throughput_gbps,
        bandwidths_mhz, mimo, modulation, rx_sensitivity_dbm, source_file, notes
    ) VALUES (
        %(manufacturer)s, %(model)s, %(frequency_min_ghz)s, %(frequency_max_ghz)s,
        %(max_output_power_dbm)s, %(integrated_antenna_gain_dbi)s, %(throughput_gbps)s,
        %(bandwidths_mhz)s, %(mimo)s, %(modulation)s, %(rx_sensitivity_dbm)s, %(source_file)s, %(notes)s
    ) ON DUPLICATE KEY UPDATE
        manufacturer = VALUES(manufacturer),
        frequency_min_ghz = VALUES(frequency_min_ghz),
        frequency_max_ghz = VALUES(frequency_max_ghz),
        max_output_power_dbm = VALUES(max_output_power_dbm),
        integrated_antenna_gain_dbi = VALUES(integrated_antenna_gain_dbi),
        throughput_gbps = VALUES(throughput_gbps),
        bandwidths_mhz = VALUES(bandwidths_mhz),
        mimo = VALUES(mimo),
        modulation = VALUES(modulation),
        rx_sensitivity_dbm = VALUES(rx_sensitivity_dbm),
        source_file = VALUES(source_file),
        notes = VALUES(notes);
    """

    with get_db() as conn:
        with conn.cursor() as cur:
            for r in radios:
                params = {
                    "manufacturer": r.get("manufacturer") or "Desconocido",
                    "model": r.get("model") or "Sin modelo",
                    "frequency_min_ghz": clean_decimal(r.get("frequency_min_ghz")),
                    "frequency_max_ghz": clean_decimal(r.get("frequency_max_ghz")),
                    "max_output_power_dbm": clean_decimal(r.get("max_output_power_dbm")),
                    "integrated_antenna_gain_dbi": clean_decimal(r.get("integrated_antenna_gain_dbi")) or 0.0,
                    "throughput_gbps": clean_decimal(r.get("throughput_gbps")),
                    "bandwidths_mhz": json.dumps(r.get("bandwidths_mhz")) if r.get("bandwidths_mhz") is not None else None,
                    "mimo": r.get("mimo"),
                    "modulation": r.get("modulation"),
                    "rx_sensitivity_dbm": json.dumps(r.get("rx_sensitivity_dbm")) if r.get("rx_sensitivity_dbm") is not None else None,
                    "source_file": r.get("source_file"),
                    "notes": r.get("notes"),
                }
                cur.execute(sql, params)
                count += 1

    return count


def migrate_antennas():
    if not ANTENNAS_FILE.exists():
        print(f"⚠️ Archivo no encontrado: {ANTENNAS_FILE}")
        return 0

    antennas = json.loads(ANTENNAS_FILE.read_text(encoding="utf-8"))
    count = 0

    sql = """
    INSERT INTO antennas (
        manufacturer, model, gain_dbi, gain_low_dbi, gain_mid_dbi, gain_high_dbi,
        frequency_min_ghz, frequency_max_ghz, beamwidth_deg, polarization,
        front_to_back_ratio_db, xpd_db, diameter_m, weight_kg, packed_weight_kg,
        wind_area_m2, operational_wind_kmh, survival_wind_kmh, vswr, port_isolation_db,
        connector, shielding, material, mast_mount, elevation_adjustment, azimuth_adjustment,
        polarization_adjustment, dimension_a_mm, dimension_b_mm, dimension_c_mm,
        source_file, notes
    ) VALUES (
        %(manufacturer)s, %(model)s, %(gain_dbi)s, %(gain_low_dbi)s, %(gain_mid_dbi)s, %(gain_high_dbi)s,
        %(frequency_min_ghz)s, %(frequency_max_ghz)s, %(beamwidth_deg)s, %(polarization)s,
        %(front_to_back_ratio_db)s, %(xpd_db)s, %(diameter_m)s, %(weight_kg)s, %(packed_weight_kg)s,
        %(wind_area_m2)s, %(operational_wind_kmh)s, %(survival_wind_kmh)s, %(vswr)s, %(port_isolation_db)s,
        %(connector)s, %(shielding)s, %(material)s, %(mast_mount)s, %(elevation_adjustment)s, %(azimuth_adjustment)s,
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
        shielding = VALUES(shielding),
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
            for a in antennas:
                params = {
                    "manufacturer": a.get("manufacturer") or "Desconocido",
                    "model": a.get("model") or "Sin modelo",
                    "gain_dbi": clean_decimal(a.get("gain_dbi")) or 0.0,
                    "gain_low_dbi": clean_decimal(a.get("gain_low_dbi")),
                    "gain_mid_dbi": clean_decimal(a.get("gain_mid_dbi")),
                    "gain_high_dbi": clean_decimal(a.get("gain_high_dbi")),
                    "frequency_min_ghz": clean_decimal(a.get("frequency_min_ghz")),
                    "frequency_max_ghz": clean_decimal(a.get("frequency_max_ghz")),
                    "beamwidth_deg": clean_decimal(a.get("beamwidth_deg")),
                    "polarization": a.get("polarization"),
                    "front_to_back_ratio_db": clean_decimal(a.get("front_to_back_ratio_db")),
                    "xpd_db": clean_decimal(a.get("xpd_db")),
                    "diameter_m": clean_decimal(a.get("diameter_m")),
                    "weight_kg": clean_decimal(a.get("weight_kg")),
                    "packed_weight_kg": clean_decimal(a.get("packed_weight_kg")),
                    "wind_area_m2": clean_decimal(a.get("wind_area_m2")),
                    "operational_wind_kmh": clean_decimal(a.get("operational_wind_kmh")),
                    "survival_wind_kmh": clean_decimal(a.get("survival_wind_kmh")),
                    "vswr": a.get("vswr"),
                    "port_isolation_db": clean_decimal(a.get("port_isolation_db")),
                    "connector": a.get("connector"),
                    "shielding": a.get("shielding"),
                    "material": a.get("material"),
                    "mast_mount": a.get("mast_mount"),
                    "elevation_adjustment": a.get("elevation_adjustment"),
                    "azimuth_adjustment": a.get("azimuth_adjustment"),
                    "polarization_adjustment": a.get("polarization_adjustment"),
                    "dimension_a_mm": clean_decimal(a.get("dimension_a_mm")),
                    "dimension_b_mm": clean_decimal(a.get("dimension_b_mm")),
                    "dimension_c_mm": clean_decimal(a.get("dimension_c_mm")),
                    "source_file": a.get("source_file"),
                    "notes": a.get("notes"),
                }
                cur.execute(sql, params)
                count += 1

    return count


def migrate_projects():
    if not PROJECTS_DIR.exists():
        return 0

    project_files = list(PROJECTS_DIR.glob("*.slp.json"))
    count = 0

    with get_db() as conn:
        with conn.cursor() as cur:
            for pf in project_files:
                try:
                    d = json.loads(pf.read_text(encoding="utf-8"))
                    meta = d.get("meta", {})
                    name = meta.get("name") or pf.stem
                    cfg = d.get("link_config", {})
                    rf = d.get("rf_settings", {})
                    obstacles = d.get("manual_obstacles", [])

                    # 1. Insertar Proyecto
                    cur.execute("""
                        INSERT INTO projects (name, description, format, version, elevation_provider, ee_project)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            format = VALUES(format),
                            version = VALUES(version),
                            elevation_provider = VALUES(elevation_provider),
                            ee_project = VALUES(ee_project);
                    """, (
                        name,
                        d.get("description", ""),
                        d.get("format", "SAF-Link-Planner-Project"),
                        d.get("version", "V5.5.5"),
                        d.get("elevation_provider", "Open-Meteo (Gratuito / Copernicus DEM)"),
                        d.get("ee_project", "saf-link-planner"),
                    ))

                    # Obtener ID del proyecto
                    cur.execute("SELECT id FROM projects WHERE name = %s", (name,))
                    row = cur.fetchone()
                    if not row:
                        continue
                    project_id = row["id"]

                    # 2. Insertar Link Config
                    cur.execute("DELETE FROM project_links WHERE project_id = %s", (project_id,))
                    cur.execute("""
                        INSERT INTO project_links (
                            project_id, site_a_name, lat_a, lon_a, height_a_m,
                            site_b_name, lat_b, lon_b, height_b_m
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        project_id,
                        cfg.get("name_a", "Sitio A"),
                        cfg.get("lat_a", 0.0),
                        cfg.get("lon_a", 0.0),
                        cfg.get("height_a", 20.0),
                        cfg.get("name_b", "Sitio B"),
                        cfg.get("lat_b", 0.0),
                        cfg.get("lon_b", 0.0),
                        cfg.get("height_b", 20.0),
                    ))

                    # 3. Insertar RF Settings
                    cur.execute("DELETE FROM project_rf_settings WHERE project_id = %s", (project_id,))
                    cur.execute("""
                        INSERT INTO project_rf_settings (
                            project_id, frequency_ghz, tx_power_dbm, channel_mhz,
                            required_capacity_mbps, other_losses_db, k_factor
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        project_id,
                        rf.get("frequency_ghz", 5.8),
                        rf.get("tx_power_dbm", 24.0),
                        rf.get("channel_mhz", 80),
                        rf.get("required_capacity_mbps", 500.0),
                        rf.get("other_losses_db", 2.0),
                        rf.get("k_factor", 1.333),
                    ))

                    # 4. Insertar Obstáculos
                    cur.execute("DELETE FROM project_obstacles WHERE project_id = %s", (project_id,))
                    for obs in obstacles:
                        cur.execute("""
                            INSERT INTO project_obstacles (project_id, dist_km, height_m, tipo, nombre, activo)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            project_id,
                            obs.get("dist_km", 0.0),
                            obs.get("height_m", 0.0),
                            obs.get("tipo", "Árbol"),
                            obs.get("nombre", "Obstáculo"),
                            1 if obs.get("activo", True) else 0,
                        ))

                    # 5. Insertar Caché de Perfil si existe
                    if "profile_df" in d or "veg_df" in d:
                        cur.execute("""
                            INSERT INTO project_profiles (project_id, samples_count, profile_df_json, veg_df_json, exclusions_json)
                            VALUES (%s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                samples_count = VALUES(samples_count),
                                profile_df_json = VALUES(profile_df_json),
                                veg_df_json = VALUES(veg_df_json),
                                exclusions_json = VALUES(exclusions_json);
                        """, (
                            project_id,
                            len(d.get("profile_df", [])) or 512,
                            json.dumps(d.get("profile_df")) if "profile_df" in d else None,
                            json.dumps(d.get("veg_df")) if "veg_df" in d else None,
                            json.dumps(d.get("exclusions", [])) if "exclusions" in d else None,
                        ))

                    count += 1
                except Exception as exc:
                    print(f"⚠️ Error migrando proyecto {pf.name}: {exc}")

    return count


def run_full_migration():
    print("==================================================")
    print("🚀 INICIANDO MIGRACIÓN A BASE DE DATOS SQL (FASE 1)")
    print("==================================================")

    ok, msg = test_connection()
    if not ok:
        print(f"❌ Error de conexión con MySQL: {msg}")
        print("\n👉 Revisa el archivo 'database/db_config.json' con el usuario y contraseña correctos de Laragon.")
        return False

    print("✅ Conexión con servidor MySQL exitosa.")

    print("\n📦 1. Creando Base de Datos y Tablas (schema.sql)...")
    ok, msg = init_database()
    print(f"   {msg}")

    print("\n📻 2. Migrando catálogo de Radios...")
    n_radios = migrate_radios()
    print(f"   ✅ {n_radios} radios migrados correctamente a la tabla 'radios'.")

    print("\n📡 3. Migrando catálogo de Antenas...")
    n_antennas = migrate_antennas()
    print(f"   ✅ {n_antennas} antenas migradas correctamente a la tabla 'antennas'.")

    print("\n📁 4. Migrando Proyectos existentes (.slp.json)...")
    n_projects = migrate_projects()
    print(f"   ✅ {n_projects} proyectos migrados a tablas relacionales.")

    print("\n==================================================")
    print("🎉 MIGRACIÓN COMPLETADA CON ÉXITO")
    print("==================================================")
    return True


if __name__ == "__main__":
    run_full_migration()
