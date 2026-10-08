"""Repositorio de Proyectos (Capa de Persistencia).
Maneja operaciones de lectura, guardado y listado de proyectos sobre las tablas relacionales SQL.
"""

import json
from pathlib import Path
from database.connection import get_db

PROJECTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "projects"


class ProjectRepository:
    @staticmethod
    def list_all():
        """Lista proyectos desde SQL o fallback a archivos locales .slp.json."""
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT p.id, p.name, p.updated_at, l.site_a_name, l.site_b_name, l.distance_km
                        FROM projects p
                        LEFT JOIN project_links l ON p.id = l.project_id
                        ORDER BY p.updated_at DESC;
                    """)
                    rows = cur.fetchall()
                    if rows:
                        return [{
                            "id": r["id"],
                            "name": r["name"],
                            "modified": str(r["updated_at"]),
                            "site_a": r["site_a_name"] or "",
                            "site_b": r["site_b_name"] or "",
                            "distance_km": float(r["distance_km"]) if r["distance_km"] else None
                        } for r in rows]
        except Exception:
            pass

        # Fallback a archivos .slp.json
        items = []
        if PROJECTS_DIR.exists():
            for p in sorted(PROJECTS_DIR.glob("*.slp.json"), key=lambda x: x.stat().st_mtime, reverse=True):
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                    m = d.get("meta", {})
                    c = d.get("link_config", {})
                    items.append({
                        "name": m.get("name", p.stem),
                        "file": p.name,
                        "modified": m.get("modified", ""),
                        "site_a": c.get("name_a", ""),
                        "site_b": c.get("name_b", "")
                    })
                except Exception:
                    pass
        return items

    @staticmethod
    def load_by_name(name):
        """Carga el estado completo de un proyecto desde la base de datos SQL."""
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM projects WHERE name = %s;", (name,))
                    proj = cur.fetchone()
                    if not proj:
                        return None

                    p_id = proj["id"]
                    cur.execute("SELECT * FROM project_links WHERE project_id = %s;", (p_id,))
                    link = cur.fetchone() or {}

                    cur.execute("SELECT * FROM project_rf_settings WHERE project_id = %s;", (p_id,))
                    rf = cur.fetchone() or {}

                    cur.execute("SELECT * FROM project_obstacles WHERE project_id = %s ORDER BY dist_km ASC;", (p_id,))
                    obstacles = cur.fetchall()

                    cur.execute("SELECT * FROM project_profiles WHERE project_id = %s;", (p_id,))
                    prof = cur.fetchone() or {}

                    profile_df = json.loads(prof["profile_df_json"]) if prof.get("profile_df_json") else None
                    veg_df = json.loads(prof["veg_df_json"]) if prof.get("veg_df_json") else None

                    return {
                        "meta": {"name": proj["name"], "modified": str(proj["updated_at"])},
                        "format": proj["format"],
                        "version": proj["version"],
                        "elevation_provider": proj["elevation_provider"],
                        "ee_project": proj["ee_project"],
                        "link_config": {
                            "name_a": link.get("site_a_name", "Sitio A"),
                            "lat_a": float(link.get("lat_a", 0.0)),
                            "lon_a": float(link.get("lon_a", 0.0)),
                            "height_a": float(link.get("height_a_m", 20.0)),
                            "name_b": link.get("site_b_name", "Sitio B"),
                            "lat_b": float(link.get("lat_b", 0.0)),
                            "lon_b": float(link.get("lon_b", 0.0)),
                            "height_b": float(link.get("height_b_m", 20.0)),
                        },
                        "rf_settings": {
                            "frequency_ghz": float(rf.get("frequency_ghz", 5.8)),
                            "tx_power_dbm": float(rf.get("tx_power_dbm", 24.0)),
                            "channel_mhz": int(rf.get("channel_mhz", 80)),
                            "required_capacity_mbps": float(rf.get("required_capacity_mbps", 500.0)),
                            "other_losses_db": float(rf.get("other_losses_db", 2.0)),
                            "k_factor": float(rf.get("k_factor", 1.333)),
                        },
                        "manual_obstacles": [{
                            "dist_km": float(o["dist_km"]),
                            "height_m": float(o["height_m"]),
                            "tipo": o["tipo"],
                            "nombre": o["nombre"],
                            "activo": bool(o["activo"])
                        } for o in obstacles],
                        "profile_df": profile_df,
                        "veg_df": veg_df,
                    }
        except Exception:
            return None
