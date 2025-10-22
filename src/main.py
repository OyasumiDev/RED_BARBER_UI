# main.py
import os
import flet as ft
from app.views.window_main_view import window_main

# ================== MODELOS ==================
from app.models.usuarios_model import UsuariosModel
from app.models.trabajadores_model import TrabajadoresModel
from app.models.inventario_model import InventarioModel
from app.models.agenda_model import AgendaModel  # ⬅️ ya estaba
from app.models.servicios_model import ServiciosModel  # ⬅️ NUEVO

# ================== ENUMS Y DB ==================
from app.config.db.database_mysql import DatabaseMysql
from app.core.enums.e_usuarios import E_USUARIOS
from app.core.enums.e_trabajadores import E_TRABAJADORES
from app.core.enums.e_inventario import E_INVENTARIO, E_INV_MOVS, E_INV_ALERTAS
from app.core.enums.e_agenda import E_AGENDA  # ⬅️ ya estaba
from app.core.enums.e_servicios import E_SERV  # ⬅️ NUEVO

# ================== TEMA GLOBAL ==================
from app.config.application.theme_controller import ThemeController


# -------------------------------------------------
# 🔍 Verifica existencia de tablas en INFORMATION_SCHEMA
# -------------------------------------------------
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
    """Verifica en INFORMATION_SCHEMA las tablas esperadas antes del bootstrap."""
    print("🔍 Verificando tablas en INFORMATION_SCHEMA...")
    db = DatabaseMysql()

    checks = [
        ("usuarios_app", E_USUARIOS.TABLE.value),
        ("trabajadores", E_TRABAJADORES.TABLE.value),
        ("inventario", E_INVENTARIO.TABLE.value),
        ("inventario_movimientos", E_INV_MOVS.TABLE.value),
        ("inventario_alertas", E_INV_ALERTAS.TABLE.value),
        ("agenda_citas", E_AGENDA.TABLE.value),
        ("servicios", E_SERV.TABLE.value),  # ⬅️ NUEVO
    ]

    for label, tbl in checks:
        if _table_exists(db, tbl):
            print(f"✅ La tabla '{tbl}' ya existe ({label}).")
        else:
            print(f"ℹ️ La tabla '{tbl}' no existe ({label}); se creará durante la inicialización del modelo.")


# -------------------------------------------------
# 🧱 Constructor seguro para modelos
# -------------------------------------------------
def _safe_create(label: str, cls):
    """
    Instancia el modelo indicado y ejecuta su inicialización interna.
    Si el modelo implementa healthcheck(), se imprime su estado.
    """
    print(f"🔄 Creando/verificando {label}...")
    try:
        obj = cls()  # Cada modelo crea su esquema al inicializarse
        if hasattr(obj, "healthcheck"):
            status = obj.healthcheck()
            if status.get("ok"):
                print(f"✔️ {label.capitalize()} OK.")
            else:
                print(f"⚠️ {label.capitalize()} parcialmente inicializado: {status}")
        else:
            print(f"✔️ {label.capitalize()} OK.")
        return obj
    except Exception as ex:
        print(f"❌ Error creando/verificando {label}: {ex}")
        raise


# -------------------------------------------------
# 🚀 Bootstrap general de base de datos
# -------------------------------------------------
def bootstrap_db():
    """
    Ejecuta la verificación previa de tablas e inicializa los modelos principales.
    Cada modelo se encarga de crear su estructura si falta (tablas, índices, triggers, seeds).
    """
    _preflight_verify_tables()

    # Inicializar modelos principales
    _safe_create("tabla usuarios_app", UsuariosModel)
    _safe_create("tabla trabajadores", TrabajadoresModel)
    _safe_create("tabla inventario", InventarioModel)
    _safe_create("tabla agenda_citas", AgendaModel)

    # ⬅️ NUEVO: Servicios (crea tabla + semillas)
    servicios = _safe_create("tabla servicios", ServiciosModel)
    try:
        servicios.seed_predeterminados()
        print("🌱 Servicios predeterminados asegurados.")
    except Exception as ex:
        print(f"⚠️ No se pudieron sembrar servicios predeterminados: {ex}")

    print("✅ Bootstrap de base de datos completado correctamente.\n")


# -------------------------------------------------
# 🌗 Inicialización del tema + UI principal
# -------------------------------------------------
def _entrypoint(page: ft.Page):
    """Adjunta la Page al controlador de tema y lanza la ventana principal."""
    ThemeController().attach_page(page)
    return window_main(page)


def iniciar_aplicacion():
    """Punto de entrada principal."""
    bootstrap_db()  # Inicializa BD y tablas
    print("🚀 Lanzando aplicación...")
    ft.app(target=_entrypoint, assets_dir="assets")


# -------------------------------------------------
# 🧩 Ejecución directa
# -------------------------------------------------
if __name__ == "__main__":
    try:
        iniciar_aplicacion()
    except Exception as e:
        print(f"❌ Error al iniciar la aplicación: {e}")
