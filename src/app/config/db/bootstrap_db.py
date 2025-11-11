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
from app.models.promos_model import PromosModel  # ← PROMOS

# Cortes es opcional: import flexible (no romper si aún no está)
try:
    from app.models.cortes_model import CortesModel   # ← CORTES (opcional)
except Exception:
    CortesModel = None  # type: ignore

# ---------- NUEVO: Contabilidad (Nómina / Ganancias) ----------
# Import tolerante: prioriza el módulo nomina_model que creamos, y acepta alternativas.
NominaModel = None
GananciasModel = None
try:
    from app.models.contabilidad_model import NominaModel as _NominaModel  # ← nuestro modelo
    NominaModel = _NominaModel
except Exception:
    try:
        # si tu proyecto tuviera estos nombres
        from app.models.contabilidad_model import NominaModel as _NominaModel
        NominaModel = _NominaModel
    except Exception:
        pass
try:
    # si tuvieras un modelo separado para reportes de ganancias
    from app.models.contabilidad_model import GananciasModel as _GananciasModel
    GananciasModel = _GananciasModel
except Exception:
    pass

# ENUMS (para preflight y logs con nombres reales de tablas)
from app.core.enums.e_usuarios import E_USUARIOS
from app.core.enums.e_trabajadores import E_TRABAJADORES
from app.core.enums.e_inventario import E_INVENTARIO, E_INV_MOVS, E_INV_ALERTAS
from app.core.enums.e_agenda import E_AGENDA
from app.core.enums.e_servicios import E_SERV
from app.core.enums.e_promos import E_PROMO  # ← PROMOS

# Enum de Cortes opcional
try:
    from app.core.enums.e_cortes import E_CORTE # ← CORTES (opcional)
except Exception:
    class _ECORTES_FALLBACK:
        TABLE = type("T", (), {"value": "cortes"})
    E_CORTES = _ECORTES_FALLBACK()  # type: ignore

# ---------- Enums de Contabilidad (opcionales con fallback antiguo) ----------
# Si existen en tu proyecto, los usamos; si no, no estorban.
try:
    from app.core.enums.e_contabilidad import E_NOMINA, E_NOMINA_ITEM
except Exception:
    class _ENOMINA_FALLBACK:
        TABLE = type("T", (), {"value": "nominas"})
    class _ENOMINA_ITEM_FALLBACK:
        TABLE = type("T", (), {"value": "nomina_items"})
    E_NOMINA = _ENOMINA_FALLBACK()           # type: ignore
    E_NOMINA_ITEM = _ENOMINA_ITEM_FALLBACK() # type: ignore


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

    checks: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(label: str, tbl: str | None):
        name = (tbl or "").strip()
        if not name:
            return
        if name in seen:
            return
        checks.append((label, name))
        seen.add(name)

    # Base
    _add("usuarios_app", E_USUARIOS.TABLE.value)
    _add("trabajadores", E_TRABAJADORES.TABLE.value)
    _add("inventario", E_INVENTARIO.TABLE.value)
    _add("inventario_movimientos", E_INV_MOVS.TABLE.value)
    _add("inventario_alertas", E_INV_ALERTAS.TABLE.value)
    _add("servicios", E_SERV.TABLE.value)
    _add("promos", E_PROMO.TABLE.value)
    _add("agenda_citas", E_AGENDA.TABLE.value)

    # Cortes
    try:
        cortes_tbl = getattr(E_CORTES, "TABLE", None)
        cortes_tbl_name = getattr(cortes_tbl, "value", "cortes")
        _add("cortes", cortes_tbl_name)
    except Exception:
        _add("cortes", "cortes")

    # Contabilidad (preferimos el nombre real del modelo si existe)
    # 1) Tabla de nómina real (nuestro NominaModel usa TABLE="nomina_pagos")
    try:
        if NominaModel and hasattr(NominaModel, "TABLE"):
            _add("nomina", str(getattr(NominaModel, "TABLE")))
        else:
            _add("nomina", "nomina_pagos")  # fallback sensato
    except Exception:
        _add("nomina", "nomina_pagos")

    # 2) Si tienes enums antiguos (nominas / nomina_items), también los listamos sin duplicar
    try:
        _add("nominas", getattr(E_NOMINA.TABLE, "value", "nominas"))
    except Exception:
        pass
    try:
        _add("nomina_items", getattr(E_NOMINA_ITEM.TABLE, "value", "nomina_items"))
    except Exception:
        pass

    # Reporte de existencia
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

        # ⚠️ ORDEN IMPORTA
        # 1) Usuarios (independiente)
        _safe_create("tabla usuarios_app", UsuariosModel, logger)

        # 2) Trabajadores y Servicios (referenciadas por 'agenda', 'promos' y 'cortes')
        _safe_create("tabla trabajadores", TrabajadoresModel, logger)
        servicios = _safe_create("tabla servicios", ServiciosModel, logger)

        # 3) Promos (FK a servicios)
        _safe_create("tabla promos", PromosModel, logger)

        # 4) Agenda (FK a trabajadores/servicios)
        _safe_create("tabla agenda_citas", AgendaModel, logger)

        # 5) Cortes (si está el modelo)
        if CortesModel:
            _safe_create("tabla cortes", CortesModel, logger)

        # 6) Contabilidad (Nómina crea sus propias tablas; Ganancias suele ser de reportes)
        if NominaModel:
            _safe_create("tabla nomina (pagos)", NominaModel, logger)
        if GananciasModel:
            _safe_create("módulo ganancias (reportes)", GananciasModel, logger)

        # 7) Inventario y dependientes
        _safe_create("tabla inventario", InventarioModel, logger)

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
