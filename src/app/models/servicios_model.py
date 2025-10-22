from __future__ import annotations
"""
app/models/servicios_model.py
-----------------------------

Módulo actualizado para alinear 1:1 con la lógica esperada por ServiciosContainer y
el bootstrap. Corrige los errores de logs:

❌ Unknown column 'duracion_min' in 'field list'
→ Se asegura que la tabla `servicios` tenga SIEMPRE la columna `duracion_min` (INT NULL).
→ También se asegura que la columna de precio sea `precio_base` (renombrando desde `precio` si aplica).

API expuesta (flexible, compatible con el contenedor):
- Lectura:  get_all(), list(), listar(activo: Optional[bool], search: Optional[str])
- Alta:     create(data: dict), add(...), crear_servicio(...)
- Edición:  update(id, patch|**kwargs), edit(...), actualizar_servicio(...)
- Borrado:  delete(id), remove(id), eliminar_servicio(id)

Notas:
- No introduce dependencias nuevas.
- Usa DatabaseMysql para DDL/DML y maneja INFORMATION_SCHEMA para detectar/alterar columnas.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
from decimal import Decimal

from app.config.db.database_mysql import DatabaseMysql

# Enums (opcionales). Si no están, se usan literales seguros.
try:
    from app.core.enums.e_servicios import E_SERV_TIPO  # sólo si lo necesitas externamente
except Exception:
    E_SERV_TIPO = None

try:
    # En algunos proyectos se usa un Enum con nombres/valores de columnas (opcional)
    from app.core.enums.e_servicios import E_SERV
except Exception:
    E_SERV = None


# =============================================================================
# Utilidades internas para nombres de tabla/columnas (compatibles con enums)
# =============================================================================
def _ev(attr: str, default: str) -> str:
    """Obtiene E_SERV.<attr>.value si existe, o default en su defecto."""
    try:
        if E_SERV is not None and hasattr(E_SERV, attr):
            v = getattr(E_SERV, attr)
            return getattr(v, "value", default)
    except Exception:
        pass
    return default


TABLE_SERVICIOS = _ev("TABLE", "servicios")
COL_ID = _ev("ID", "id")
COL_NOMBRE = _ev("NOMBRE", "nombre")
COL_TIPO = _ev("TIPO", "tipo")
# Importante: el contenedor y bootstrap insertan/esperan 'precio_base'
COL_PRECIO_BASE = _ev("PRECIO", "precio_base")
COL_MONTO_LIBRE = _ev("MONTO_LIBRE", "monto_libre")
COL_ACTIVO = _ev("ACTIVO", "activo")
COL_CREATED_AT = _ev("CREATED_AT", "created_at")
COL_UPDATED_AT = _ev("UPDATED_AT", "updated_at")

# Nueva columna que causaba el error en logs
COL_DURACION_MIN = "duracion_min"


class ServiciosModel:
    """
    Modelo de catálogo de servicios con DDL robusto y API flexible.
    """

    def __init__(self) -> None:
        self.db = DatabaseMysql()
        self._ensure_schema()

    # =========================================================================
    # DDL / Schema
    # =========================================================================
    def _ensure_schema(self) -> None:
        """
        Crea la tabla si no existe y asegura que existan:
        - columna de precio: `precio_base` (si existe `precio`, la renombra)
        - columna opcional:  `duracion_min` INT NULL
        - índices básicos por tipo y activo
        """
        self._create_table_if_not_exists()
        # Normalizar columna de precio
        self._ensure_precio_base_column()
        # Asegurar columna duracion_min
        self._ensure_column(COL_DURACION_MIN, "INT NULL")
        # Índices ligeros
        self._ensure_index("idx_servicios_tipo", COL_TIPO)
        self._ensure_index("idx_servicios_activo", COL_ACTIVO)

    def _create_table_if_not_exists(self) -> None:
        # Declaramos con precio_base directamente para evitar renombres en instalaciones nuevas
        sql = f"""
        CREATE TABLE IF NOT EXISTS {TABLE_SERVICIOS} (
            {COL_ID} INT AUTO_INCREMENT PRIMARY KEY,
            {COL_NOMBRE} VARCHAR(150) NOT NULL,
            {COL_TIPO} VARCHAR(64) NOT NULL,
            {COL_PRECIO_BASE} DECIMAL(10,2) NULL,
            {COL_MONTO_LIBRE} TINYINT(1) NOT NULL DEFAULT 0,
            {COL_ACTIVO} TINYINT(1) NOT NULL DEFAULT 1,
            {COL_DURACION_MIN} INT NULL,
            {COL_CREATED_AT} DATETIME DEFAULT CURRENT_TIMESTAMP,
            {COL_UPDATED_AT} DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        self._run(sql)

    # -------------------- helpers de INFORMATION_SCHEMA --------------------
    def _column_exists(self, column: str) -> bool:
        q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            LIMIT 1
        """
        row = self.db.get_data(q, (TABLE_SERVICIOS, column), dictionary=True)
        return row is not None

    def _ensure_column(self, column: str, ddl_type: str) -> None:
        if not self._column_exists(column):
            self._run(f"ALTER TABLE {TABLE_SERVICIOS} ADD COLUMN {column} {ddl_type}")

    def _index_exists(self, index_name: str) -> bool:
        q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            LIMIT 1
        """
        row = self.db.get_data(q, (TABLE_SERVICIOS, index_name), dictionary=True)
        return row is not None

    def _ensure_index(self, index_name: str, column: str, *, unique: bool = False) -> None:
        if not self._index_exists(index_name):
            self._run(f"CREATE {'UNIQUE ' if unique else ''}INDEX {index_name} ON {TABLE_SERVICIOS}({column})")

    def _ensure_precio_base_column(self) -> None:
        """
        Si 'precio_base' no existe y existe 'precio', renombra 'precio' → 'precio_base'.
        Si no existe ninguna, crea 'precio_base'.
        """
        has_precio_base = self._column_exists(COL_PRECIO_BASE)
        if has_precio_base:
            return

        # Intentar detectar una columna 'precio' heredada
        precio_legacy = "precio"
        try:
            if self._column_exists(precio_legacy):
                # Renombrar (preserva tipo a DECIMAL(10,2))
                self._run(
                    f"ALTER TABLE {TABLE_SERVICIOS} CHANGE {precio_legacy} {COL_PRECIO_BASE} DECIMAL(10,2) NULL"
                )
                return
        except Exception:
            # Si falla el rename, caemos a agregar la nueva
            pass

        # Si no había legacy 'precio' o renombrar falló, agregar precio_base
        self._ensure_column(COL_PRECIO_BASE, "DECIMAL(10,2) NULL")

    # =========================================================================
    # CRUD (base) + Aliases compatibles con el contenedor
    # =========================================================================
    def listar(self, *, activo: Optional[bool] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista servicios, opcionalmente filtrando por activo y/o por nombre LIKE.
        """
        conds, params = [], []
        if activo is not None:
            conds.append(f"{COL_ACTIVO}=%s")
            params.append(1 if activo else 0)
        if search:
            conds.append(f"{COL_NOMBRE} LIKE %s")
            params.append(f"%{search}%")
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        q = f"SELECT * FROM {TABLE_SERVICIOS} {where} ORDER BY {COL_NOMBRE} ASC"
        return self.db.get_all(q, tuple(params) if params else None, dictionary=True) or []

    def get_all(self) -> List[Dict[str, Any]]:
        """Alias usado por el contenedor: retorna todos (activos e inactivos)."""
        return self.listar(activo=None)

    def list(self) -> List[Dict[str, Any]]:
        """Alias usado por el contenedor."""
        return self.get_all()

    def get_by_id(self, servicio_id: int) -> Optional[Dict[str, Any]]:
        q = f"SELECT * FROM {TABLE_SERVICIOS} WHERE {COL_ID}=%s"
        return self.db.get_data(q, (servicio_id,), dictionary=True)

    # ------------------------------- Alta --------------------------------
    def crear_servicio(
        self,
        *,
        nombre: str,
        tipo: str,
        precio_base: Optional[float],
        monto_libre: int = 0,
        activo: int = 1,
        duracion_min: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            cols = [COL_NOMBRE, COL_TIPO, COL_PRECIO_BASE, COL_MONTO_LIBRE, COL_ACTIVO]
            vals = [nombre, tipo, precio_base, int(monto_libre), int(activo)]

            # duracion_min es requerida por el contenedor / bootstrap; asegurada por DDL
            if self._column_exists(COL_DURACION_MIN):
                cols.append(COL_DURACION_MIN)
                vals.append(duracion_min)

            placeholders = ",".join(["%s"] * len(cols))
            sql = f"INSERT INTO {TABLE_SERVICIOS} ({','.join(cols)}) VALUES ({placeholders})"
            self._run(sql, tuple(vals))
            return {"status": "success", "message": "Servicio creado"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Acepta dict con:
          nombre, tipo, precio | precio_base, activo (0/1), monto_libre (0/1), duracion_min
        """
        if not isinstance(data, dict):
            return {"status": "error", "message": "Payload inválido"}
        payload = dict(data)
        if "precio_base" not in payload and "precio" in payload:
            payload["precio_base"] = payload.pop("precio")
        return self.crear_servicio(
            nombre=payload.get("nombre"),
            tipo=payload.get("tipo"),
            precio_base=payload.get("precio_base"),
            monto_libre=int(payload.get("monto_libre", 0)),
            activo=int(payload.get("activo", 1)),
            duracion_min=payload.get("duracion_min"),
        )

    def add(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Soporta:
          - add(data: dict)
          - add(nombre=..., tipo=..., precio=..., precio_base=..., activo=..., duracion_min=..., ...)
        """
        if len(args) == 1 and isinstance(args[0], dict):
            return self.create(args[0])
        data = dict(kwargs or {})
        if "precio_base" not in data and "precio" in data:
            data["precio_base"] = data.pop("precio")
        return self.create(data)

    # ------------------------------- Edición ------------------------------
    def actualizar_servicio(
        self,
        servicio_id: int,
        *,
        nombre: Optional[str] = None,
        tipo: Optional[str] = None,
        precio_base: Optional[float] = None,
        monto_libre: Optional[int] = None,
        activo: Optional[int] = None,
        duracion_min: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            sets, params = [], []

            def _set(col: str, val: Any):
                sets.append(f"{col}=%s")
                params.append(val)

            if nombre is not None:
                _set(COL_NOMBRE, nombre)
            if tipo is not None:
                _set(COL_TIPO, tipo)
            if precio_base is not None:
                _set(COL_PRECIO_BASE, precio_base)
            if monto_libre is not None:
                _set(COL_MONTO_LIBRE, int(monto_libre))
            if activo is not None:
                _set(COL_ACTIVO, int(activo))
            if self._column_exists(COL_DURACION_MIN) and (duracion_min is not None):
                _set(COL_DURACION_MIN, duracion_min)

            if not sets:
                return {"status": "success", "message": "Sin cambios"}

            params.append(servicio_id)
            sql = f"UPDATE {TABLE_SERVICIOS} SET {', '.join(sets)} WHERE {COL_ID}=%s"
            self._run(sql, tuple(params))
            return {"status": "success", "message": "Servicio actualizado"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def update(self, servicio_id: int, patch_or_kwargs: Union[Dict[str, Any], None] = None, **kwargs) -> Dict[str, Any]:
        """
        Soporta:
          - update(id, patch: dict)
          - update(id, nombre=..., tipo=..., precio=..., precio_base=..., activo=..., duracion_min=..., ...)
        """
        data: Dict[str, Any] = {}
        if isinstance(patch_or_kwargs, dict):
            data.update(patch_or_kwargs)
        if kwargs:
            data.update(kwargs)
        if "precio_base" not in data and "precio" in data:
            data["precio_base"] = data.pop("precio")

        return self.actualizar_servicio(
            servicio_id,
            nombre=data.get("nombre"),
            tipo=data.get("tipo"),
            precio_base=data.get("precio_base"),
            monto_libre=data.get("monto_libre"),
            activo=data.get("activo"),
            duracion_min=data.get("duracion_min"),
        )

    def edit(self, servicio_id: int, patch_or_kwargs: Union[Dict[str, Any], None] = None, **kwargs) -> Dict[str, Any]:
        """Alias de update()."""
        return self.update(servicio_id, patch_or_kwargs, **kwargs)

    # ------------------------------- Borrado ------------------------------
    def eliminar_servicio(self, servicio_id: int) -> Dict[str, Any]:
        try:
            sql = f"DELETE FROM {TABLE_SERVICIOS} WHERE {COL_ID}=%s"
            self._run(sql, (servicio_id,))
            return {"status": "success", "message": "Servicio eliminado"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def delete(self, servicio_id: int) -> Dict[str, Any]:
        """Alias de eliminar_servicio()."""
        return self.eliminar_servicio(servicio_id)

    def remove(self, servicio_id: int) -> Dict[str, Any]:
        """Alias de eliminar_servicio()."""
        return self.eliminar_servicio(servicio_id)

    # =========================================================================
    # Helpers internos
    # =========================================================================
    def _run(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        """
        Ejecuta una sentencia SQL con manejo mínimo de logs/errores, para mantener
        el ruido bajo en consola en producción.
        """
        try:
            self.db.run_query(sql, params)
        except Exception as ex:
            # Log claro (similar a los que mostraste) pero sin romper el flujo.
            p = ""
            if params:
                try:
                    p = f"\nParams: {params}"
                except Exception:
                    p = ""
            print(f"❌ Error ejecutando query: {ex}\nSQL: {sql}{p}")
            raise
