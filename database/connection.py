"""Módulo de Conexión y Gestión de Base de Datos (Capa de Persistencia).
Soporta MySQL (Laragon / MariaDB) vía PyMySQL con fallback opcional a SQLite.
"""

import json
import os
from pathlib import Path
from contextlib import contextmanager

try:
    import pymysql
    from pymysql.cursors import DictCursor
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False
    DictCursor = None

CONFIG_FILE = Path(__file__).resolve().parent / "db_config.json"
SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def load_db_config():
    default_config = {
        "driver": "mysql",
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "saf_link_planner",
    }
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            default_config.update(cfg)
        except Exception:
            pass

    # Variables de entorno tienen prioridad sobre el archivo
    default_config["host"] = os.getenv("DB_HOST", default_config["host"])
    default_config["port"] = int(os.getenv("DB_PORT", default_config["port"]))
    default_config["user"] = os.getenv("DB_USER", default_config["user"])
    default_config["password"] = os.getenv("DB_PASSWORD", default_config["password"])
    default_config["database"] = os.getenv("DB_NAME", default_config["database"])
    return default_config


def save_db_config(config_dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config_dict, indent=2), encoding="utf-8")


def get_mysql_connection(include_db=True):
    if not PYMYSQL_AVAILABLE:
        raise RuntimeError("La librería pymysql no está instalada. Ejecuta: pip install pymysql")

    cfg = load_db_config()
    kwargs = {
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "password": cfg["password"],
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    if include_db:
        kwargs["database"] = cfg["database"]

    return pymysql.connect(**kwargs)


@contextmanager
def get_db():
    """Context manager para transacciones seguras con commit/rollback automático."""
    conn = get_mysql_connection(include_db=True)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Crea la base de datos y ejecuta el esquema DDL de tablas."""
    cfg = load_db_config()
    db_name = cfg["database"]

    # 1. Conectar al servidor MySQL sin especificar base de datos para crearla si no existe
    conn_server = get_mysql_connection(include_db=False)
    try:
        with conn_server.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn_server.commit()
    finally:
        conn_server.close()

    # 2. Conectar a la base de datos y ejecutar schema.sql
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"No se encontró el archivo de esquema: {SCHEMA_FILE}")

    sql_content = SCHEMA_FILE.read_text(encoding="utf-8")
    
    # Dividir las sentencias por punto y coma (ignorando USE y comentarios simples)
    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]

    with get_db() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                if stmt.upper().startswith("USE "):
                    continue
                cur.execute(stmt)

    return True, f"Base de datos `{db_name}` y tablas inicializadas correctamente."


def test_connection():
    """Prueba si las credenciales actuales conectan al servidor MySQL de Laragon."""
    try:
        conn = get_mysql_connection(include_db=False)
        conn.close()
        return True, "Conexión a MySQL exitosa."
    except Exception as exc:
        return False, str(exc)
