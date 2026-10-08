"""Repositorio de Radios (Capa de Persistencia).
Maneja operaciones CRUD sobre la tabla 'radios' en MySQL con fallback automático a JSON.
"""

import json
from pathlib import Path
from database.connection import get_db

DATA_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "radios.json"


class RadioRepository:
    @staticmethod
    def get_all():
        """Obtiene todos los radios de la base de datos SQL. Si la BD no está disponible, lee de JSON."""
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM radios ORDER BY manufacturer ASC, model ASC;")
                    rows = cur.fetchall()
                    for r in rows:
                        if isinstance(r.get("bandwidths_mhz"), str):
                            try:
                                r["bandwidths_mhz"] = json.loads(r["bandwidths_mhz"])
                            except Exception:
                                pass
                        if isinstance(r.get("rx_sensitivity_dbm"), str):
                            try:
                                r["rx_sensitivity_dbm"] = json.loads(r["rx_sensitivity_dbm"])
                            except Exception:
                                pass
                    return rows
        except Exception:
            # Fallback a JSON si no hay conexión a base de datos
            if DATA_JSON.exists():
                try:
                    return json.loads(DATA_JSON.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return []

    @staticmethod
    def get_by_id(radio_id):
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM radios WHERE id = %s;", (radio_id,))
                    row = cur.fetchone()
                    if row and isinstance(row.get("bandwidths_mhz"), str):
                        row["bandwidths_mhz"] = json.loads(row["bandwidths_mhz"])
                    if row and isinstance(row.get("rx_sensitivity_dbm"), str):
                        row["rx_sensitivity_dbm"] = json.loads(row["rx_sensitivity_dbm"])
                    return row
        except Exception:
            return None

    @staticmethod
    def save(radio_data):
        """Inserta o actualiza un radio en la base de datos."""
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
        params = dict(radio_data)
        if isinstance(params.get("bandwidths_mhz"), (list, tuple)):
            params["bandwidths_mhz"] = json.dumps(params["bandwidths_mhz"])
        if isinstance(params.get("rx_sensitivity_dbm"), dict):
            params["rx_sensitivity_dbm"] = json.dumps(params["rx_sensitivity_dbm"])

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.lastrowid
