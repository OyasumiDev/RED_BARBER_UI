# app/config/db/bootstrap_db.py
from __future__ import annotations

from typing import Optional, Callable, Dict, Any, Type
import traceback

# DB
from app.config.db.database_mysql import DatabaseMysql

# MODELOS (cada uno crea/asegura su propia tabla/esquema al inicializarse)
from app.models.usuarios_model import UsuariosModel
from app.models.trabajadores_model import TrabajadoresModel
from app.models.inventario_model import InventarioModel
from app.models.agenda_model import AgendaModel
from app.models.servicios_model import ServiciosModel

# ENUMS (para preflight y logs con nombres reales de tablas)
from app.core.enums.e_usuarios import E_USUARIOS
from app.core.enums.e_trabajadores import E_TRABAJADORES
from app.core.enums.e_inventario import E_INVENTARIO, E_INV_MOVS, E_INV_ALERTAS
from app.core.enums.e_agenda import E_AGENDA
from app.core.enums.e_servicios import E_SERV


# ------------------------ Utils de log ------------------------
def _log_default(msg: str):
    print(f"[BootstrapDB] {msg}")


def _slog(logger: Optional[Callable[[str], None]], message: str):
    (logger or _log_default)(message)


# ------------------------ Helpers SQL ------------------------
def _table_exists(db: DatabaseMysql, table_name: str) -> bool:
    try:
        q = """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
        LIMIT 1
        """
        row = db.get_data(q, (table_name,), dictionary=False)
        return bool(row)
    except Exception:
        return False


def _preflight_verify_tables(db: DatabaseMysql, logger: Optional[Callable[[str], None]] = None):
    _slog(logger, "🔍 Verificando tablas en INFORMATION_SCHEMA...")

    checks = [
        ("usuarios_app", E_USUARIOS.TABLE.value),
        ("trabajadores", E_TRABAJADORES.TABLE.value),
        ("inventario", E_INVENTARIO.TABLE.value),
        ("inventario_movimientos", E_INV_MOVS.TABLE.value),
        ("inventario_alertas", E_INV_ALERTAS.TABLE.value),
        ("servicios", E_SERV.TABLE.value),
        ("agenda_citas", E_AGENDA.TABLE.value),
    ]

    for label, tbl in checks:
        if _table_exists(db, tbl):
            _slog(logger, f"✅ La tabla '{tbl}' ya existe ({label}).")
        else:
            _slog(logger, f"ℹ️ La tabla '{tbl}' no existe ({label}); el modelo la creará si falta.")


def _safe_create(label: str, cls: Type, logger: Optional[Callable[[str], None]] = None):
    """
    Instancia el modelo indicado. Cada modelo debe crear/asegurar su esquema en __init__.
    Si implementa healthcheck(), se imprime el estado.
    """
    _slog(logger, f"🔄 Creando/verificando {label}...")
    obj = cls()
    try:
        if hasattr(obj, "healthcheck"):
            status = obj.healthcheck()
            if isinstance(status, dict) and status.get("ok"):
                _slog(logger, f"✔️ {label.capitalize()} OK.")
            else:
                _slog(logger, f"⚠️ {label.capitalize()} parcialmente inicializado: {status}")
        else:
            _slog(logger, f"✔️ {label.capitalize()} OK.")
    except Exception as ex:
        _slog(logger, f"⚠️ {label} sin healthcheck(): {ex}")
    return obj


# ------------------------ API principal ------------------------
def bootstrap_db(
    db: Optional[DatabaseMysql] = None,
    *,
    run_seeds: bool = True,
    with_preflight: bool = True,
    logger: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Bootstrap general e idempotente.
    - Puede usarse al iniciar la app o como callback tras 'drop database'.
    - Asegura que las tablas existan en orden seguro (primero referenciadas).
    - Si 'run_seeds' es True, siembra datos mínimos (servicios).

    Devuelve un dict con 'ok', 'errors', 'details'.
    """
    errors: list[str] = []
    details: dict[str, Any] = {}

    _slog(logger, "🚀 Iniciando bootstrap de base de datos...")

    # Usa la DB pasada o crea una nueva
    _db = db or DatabaseMysql()
    _db.ensure_connection()

    try:
        if with_preflight:
            _preflight_verify_tables(_db, logger)

        # ⚠️ ORDEN IMPORTA: crea primero las tablas que serán referenciadas por otras
        # 1) Usuarios (independiente)
        _safe_create("tabla usuarios_app", UsuariosModel, logger)

        # 2) Trabajadores y Servicios (referenciadas por 'agenda_citas')
        _safe_create("tabla trabajadores", TrabajadoresModel, logger)
        servicios = _safe_create("tabla servicios", ServiciosModel, logger)

        # 3) Agenda (puede crear FKs a tablas anteriores)
        _safe_create("tabla agenda_citas", AgendaModel, logger)

        # 4) Inventario + dependientes
        _safe_create("tabla inventario", InventarioModel, logger)
        # Si otros modelos crean inventario_movimientos/alertas, se cubrirán en su init
        # (Si no, podrías añadir aquí modelos auxiliares específicos)

        # Seeds opcionales
        if run_seeds and hasattr(servicios, "seed_predeterminados"):
            try:
                servicios.seed_predeterminados()
                _slog(logger, "🌱 Servicios predeterminados asegurados.")
            except Exception as ex:
                msg = f"No se pudieron sembrar servicios predeterminados: {ex}"
                _slog(logger, f"⚠️ {msg}")
                errors.append(msg)

        _slog(logger, "✅ Bootstrap de base de datos completado correctamente.")
        return {"ok": len(errors) == 0, "errors": errors, "details": details}

    except Exception as ex:
        tb = traceback.format_exc()
        msg = f"❌ Error en bootstrap_db: {ex}\n{tb}"
        errors.append(msg)
        _slog(logger, msg)
        return {"ok": False, "errors": errors, "details": details}


# ------------------------ Callback flexible para drop ------------------------
def bootstrap_after_drop(*args, **kwargs) -> Dict[str, Any]:
    """
    Callback tolerante para pasar a dropear_base_datos(bootstrap_cb=...).

    Acepta opcionalmente un DatabaseMysql en args/kwargs; si no, crea uno.
    También acepta un 'logger' en kwargs para reutilizar el del llamador.
    """
    logger = kwargs.get("logger", None)

    # Buscar una instancia de DatabaseMysql en los args/kwargs
    db: Optional[DatabaseMysql] = kwargs.get("db", None)
    if db is None:
        for a in args:
            if isinstance(a, DatabaseMysql):
                db = a
                break

    _slog(logger, "🧰 Ejecutando bootstrap_after_drop...")
    return bootstrap_db(db=db, run_seeds=True, with_preflight=True, logger=logger)
