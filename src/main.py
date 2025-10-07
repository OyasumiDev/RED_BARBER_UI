# main.py

import flet as ft
from app.views.window_main_view import window_main

# Modelos en uso actual
from app.models.usuarios_model import UsuariosModel
from app.models.trabajadores_model import TrabajadoresModel

# Verificación directa en INFORMATION_SCHEMA
from app.config.db.database_mysql import DatabaseMysql
from app.core.enums.e_usuarios import E_USUARIOS
from app.core.enums.e_trabajadores import E_TRABAJADORES


def _table_exists(db: DatabaseMysql, table_name: str) -> bool:
    try:
        q = """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """
        row = db.get_data(q, (table_name,), dictionary=True)
        return row is not None
    except Exception:
        return False


def _preflight_verify_tables():
    print("🔍 Verificando tablas en INFORMATION_SCHEMA...")
    db = DatabaseMysql()

    checks = [
        ("usuarios_app", E_USUARIOS.TABLE.value),
        ("trabajadores", E_TRABAJADORES.TABLE.value),
    ]

    for label, tbl in checks:
        if _table_exists(db, tbl):
            print(f"✅ La tabla '{tbl}' ya existe ({label}).")
        else:
            print(f"ℹ️ La tabla '{tbl}' no existe ({label}); se creará en la inicialización del modelo.")


def _safe_create(label: str, cls):
    print(f"🔄 Creando {label}...")
    try:
        obj = cls()  # el __init__ de cada modelo hace check_table/seed interno
        print(f"✔️ {label.capitalize()} ok.")
        return obj
    except Exception as ex:
        print(f"❌ Error verificando/creando {label}: {ex}")
        raise


def bootstrap_db():
    """
    Verifica primero si existen las tablas y luego inicializa modelos
    (que crean/actualizan y seed-ean si es necesario).
    """
    _preflight_verify_tables()
    _safe_create("tabla usuarios_app", UsuariosModel)
    _safe_create("tabla trabajadores", TrabajadoresModel)


def iniciar_aplicacion():
    # Inicializa BD
    bootstrap_db()

    # Lanza Flet
    print("🚀 Lanzando aplicación...")
    ft.app(target=window_main, assets_dir="assets")


if __name__ == "__main__":
    try:
        iniciar_aplicacion()
    except Exception as e:
        print(f"❌ Error al iniciar la aplicación: {e}")
