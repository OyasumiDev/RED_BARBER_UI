from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime, time
from decimal import Decimal

from app.config.db.database_mysql import DatabaseMysql
from app.core.enums.e_promos import E_PROMO, E_PROMO_ESTADO, E_PROMO_TIPO

# Usamos enums de módulos foráneos si están disponibles (para respetar nombres reales)
try:
    from app.core.enums.e_servicios import E_SERV
except Exception:
    E_SERV = None

try:
    from app.core.enums.e_trabajadores import E_TRABAJADORES
except Exception:
    E_TRABAJADORES = None


def _serv_table() -> str:
    # ServiciosModel crea/espera "servicios" con PK "id" y campo precio_base. :contentReference[oaicite:2]{index=2}
    return getattr(getattr(E_SERV, "TABLE", None), "value", "servicios")

def _serv_id_col() -> str:
    return getattr(getattr(E_SERV, "ID", None), "value", "id")

def _trab_table() -> str:
    # TrabajadoresModel crea/espera tabla definida por E_TRABAJADORES.TABLE con PK E_TRABAJADORES.ID. :contentReference[oaicite:3]{index=3}
    return getattr(getattr(E_TRABAJADORES, "TABLE", None), "value", "trabajadores")

def _trab_id_col() -> str:
    return getattr(getattr(E_TRABAJADORES, "ID", None), "value", "id")


class PromosModel:
    """
    Promociones aplicables a un servicio en días específicos de la semana,
    con vigencia de fechas y ventana horaria opcional.
    - FK estricta hacia servicios(id)
    - Auditoría opcional hacia trabajadores(id) en created_by / updated_by
    """

    def __init__(self) -> None:
        self.db = DatabaseMysql()
        self._ensure_schema()

    # ======================== DDL / SCHEMA ========================
    def _ensure_schema(self) -> None:
        stbl = _serv_table()
        sid  = _serv_id_col()
        ttab = _trab_table()
        tid  = _trab_id_col()

        sql = f"""
        CREATE TABLE IF NOT EXISTS {E_PROMO.TABLE.value} (
            {E_PROMO.ID.value} INT AUTO_INCREMENT PRIMARY KEY,
            {E_PROMO.NOMBRE.value} VARCHAR(150) NOT NULL,

            {E_PROMO.SERVICIO_ID.value} INT NOT NULL,
            {E_PROMO.TIPO_DESC.value} ENUM('{E_PROMO_TIPO.PORCENTAJE.value}','{E_PROMO_TIPO.MONTO.value}') NOT NULL,
            {E_PROMO.VALOR_DESC.value} DECIMAL(10,2) NOT NULL DEFAULT 0.00,

            {E_PROMO.ESTADO.value} ENUM('{E_PROMO_ESTADO.ACTIVA.value}','{E_PROMO_ESTADO.INACTIVA.value}')
                NOT NULL DEFAULT '{E_PROMO_ESTADO.ACTIVA.value}',

            {E_PROMO.FECHA_INI.value} DATE NULL,
            {E_PROMO.FECHA_FIN.value} DATE NULL,

            {E_PROMO.LUN.value} TINYINT(1) NOT NULL DEFAULT 0,
            {E_PROMO.MAR.value} TINYINT(1) NOT NULL DEFAULT 0,
            {E_PROMO.MIE.value} TINYINT(1) NOT NULL DEFAULT 0,
            {E_PROMO.JUE.value} TINYINT(1) NOT NULL DEFAULT 0,
            {E_PROMO.VIE.value} TINYINT(1) NOT NULL DEFAULT 0,
            {E_PROMO.SAB.value} TINYINT(1) NOT NULL DEFAULT 0,
            {E_PROMO.DOM.value} TINYINT(1) NOT NULL DEFAULT 0,

            {E_PROMO.HORA_INI.value} TIME NULL,
            {E_PROMO.HORA_FIN.value} TIME NULL,

            {E_PROMO.CREATED_BY.value} INT NULL,
            {E_PROMO.UPDATED_BY.value} INT NULL,

            {E_PROMO.CREATED_AT.value} DATETIME DEFAULT CURRENT_TIMESTAMP,
            {E_PROMO.UPDATED_AT.value} DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            CONSTRAINT fk_promos_serv
                FOREIGN KEY ({E_PROMO.SERVICIO_ID.value}) REFERENCES {stbl}({sid})
                ON UPDATE CASCADE ON DELETE RESTRICT,

            CONSTRAINT fk_promos_created_by
                FOREIGN KEY ({E_PROMO.CREATED_BY.value}) REFERENCES {ttab}({tid})
                ON UPDATE CASCADE ON DELETE SET NULL,

            CONSTRAINT fk_promos_updated_by
                FOREIGN KEY ({E_PROMO.UPDATED_BY.value}) REFERENCES {ttab}({tid})
                ON UPDATE CASCADE ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        self.db.run_query(sql)

        # Índices útiles
        self._ensure_index("idx_promos_servicio", E_PROMO.SERVICIO_ID.value)
        self._ensure_index("idx_promos_estado",   E_PROMO.ESTADO.value)
        self._ensure_index("idx_promos_fecha_ini", E_PROMO.FECHA_INI.value)
        self._ensure_index("idx_promos_fecha_fin", E_PROMO.FECHA_FIN.value)
        # Columna para precio final (monto fijo resultante)
        self._ensure_column(E_PROMO.PRECIO_FINAL.value, "DECIMAL(10,2) NULL DEFAULT NULL")

    def _ensure_index(self, index_name: str, column: str) -> None:
        q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            LIMIT 1
        """
        row = self.db.get_data(q, (E_PROMO.TABLE.value, index_name), dictionary=True)
        if not row:
            self.db.run_query(f"CREATE INDEX {index_name} ON {E_PROMO.TABLE.value} ({column})")

    def _ensure_column(self, column: str, definition: str) -> None:
        q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            LIMIT 1
        """
        row = self.db.get_data(q, (E_PROMO.TABLE.value, column), dictionary=True)
        if not row:
            self.db.run_query(f"ALTER TABLE {E_PROMO.TABLE.value} ADD COLUMN {column} {definition}")

    # ======================== QUERIES ========================
    def get_by_id(self, promo_id: int) -> Optional[Dict[str, Any]]:
        q = f"SELECT * FROM {E_PROMO.TABLE.value} WHERE {E_PROMO.ID.value}=%s"
        return self.db.get_data(q, (promo_id,), dictionary=True)

    def listar(
        self,
        *,
        activa: Optional[bool] = None,
        servicio_id: Optional[int] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        conds, params = [], []
        if activa is not None:
            conds.append(f"{E_PROMO.ESTADO.value}=%s")
            params.append(E_PROMO_ESTADO.ACTIVA.value if activa else E_PROMO_ESTADO.INACTIVA.value)
        if servicio_id is not None:
            conds.append(f"{E_PROMO.SERVICIO_ID.value}=%s")
            params.append(int(servicio_id))
        if search:
            conds.append(f"{E_PROMO.NOMBRE.value} LIKE %s")
            params.append(f"%{search}%")
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        q = f"""
        SELECT p.* 
        FROM {E_PROMO.TABLE.value} p
        {where}
        ORDER BY p.{E_PROMO.NOMBRE.value} ASC, p.{E_PROMO.CREATED_AT.value} DESC
        """
        return self.db.get_all(q, tuple(params) if params else None, dictionary=True) or []

    # Encuentra una promo aplicable para un servicio y fecha/hora dados
    def find_applicable(self, servicio_id: int, dt: datetime) -> Optional[Dict[str, Any]]:
        dow_map = {
            0: E_PROMO.LUN.value, 1: E_PROMO.MAR.value, 2: E_PROMO.MIE.value, 3: E_PROMO.JUE.value,
            4: E_PROMO.VIE.value, 5: E_PROMO.SAB.value, 6: E_PROMO.DOM.value
        }
        dow_col = dow_map[dt.weekday()]  # lunes=0
        # Búsqueda coarse en SQL (estado, servicio, rango de fechas, día activo)
        q = f"""
        SELECT *
        FROM {E_PROMO.TABLE.value}
        WHERE {E_PROMO.ESTADO.value} = %s
          AND {E_PROMO.SERVICIO_ID.value} = %s
          AND ({E_PROMO.FECHA_INI.value} IS NULL OR {E_PROMO.FECHA_INI.value} <= %s)
          AND ({E_PROMO.FECHA_FIN.value} IS NULL OR %s <= {E_PROMO.FECHA_FIN.value})
          AND {dow_col} = 1
        ORDER BY {E_PROMO.CREATED_AT.value} DESC
        """
        rows = self.db.get_all(q, (E_PROMO_ESTADO.ACTIVA.value, int(servicio_id), dt.date(), dt.date()), dictionary=True) or []
        if not rows:
            return None

        # Filtro fino por ventana horaria (si define)
        t = dt.time()
        def _in_time_window(r: Dict[str, Any]) -> bool:
            hi = r.get(E_PROMO.HORA_INI.value)
            hf = r.get(E_PROMO.HORA_FIN.value)
            if not hi and not hf:
                return True
            try:
                hi_t = hi if isinstance(hi, time) else time.fromisoformat(str(hi))
                hf_t = hf if isinstance(hf, time) else time.fromisoformat(str(hf))
                return (hi_t <= t <= hf_t) if (hi_t and hf_t) else True
            except Exception:
                return True

        for r in rows:
            if _in_time_window(r):
                return r
        return None

    # ======================== CRUD ========================
    def crear_promo(
        self,
        *,
        nombre: str,
        servicio_id: int,
        tipo_descuento: str,
        valor_descuento: float,
        precio_final: Optional[float] = None,
        estado: str = E_PROMO_ESTADO.ACTIVA.value,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        aplica_lunes: int = 0, aplica_martes: int = 0, aplica_miercoles: int = 0,
        aplica_jueves: int = 0, aplica_viernes: int = 0, aplica_sabado: int = 0, aplica_domingo: int = 0,
        hora_inicio: Optional[time] = None,
        hora_fin: Optional[time] = None,
        created_by: Optional[int] = None
    ) -> Dict[str, Any]:
        try:
            cols = [
                E_PROMO.NOMBRE.value, E_PROMO.SERVICIO_ID.value, E_PROMO.TIPO_DESC.value, E_PROMO.VALOR_DESC.value,
                E_PROMO.PRECIO_FINAL.value,
                E_PROMO.ESTADO.value, E_PROMO.FECHA_INI.value, E_PROMO.FECHA_FIN.value,
                E_PROMO.LUN.value, E_PROMO.MAR.value, E_PROMO.MIE.value, E_PROMO.JUE.value,
                E_PROMO.VIE.value, E_PROMO.SAB.value, E_PROMO.DOM.value,
                E_PROMO.HORA_INI.value, E_PROMO.HORA_FIN.value, E_PROMO.CREATED_BY.value
            ]
            vals = [
                nombre, int(servicio_id), tipo_descuento, float(valor_descuento),
                (float(precio_final) if precio_final is not None else None),
                estado, fecha_inicio, fecha_fin,
                int(aplica_lunes), int(aplica_martes), int(aplica_miercoles), int(aplica_jueves),
                int(aplica_viernes), int(aplica_sabado), int(aplica_domingo),
                hora_inicio, hora_fin, created_by
            ]
            placeholders = ",".join(["%s"] * len(cols))
            sql = f"INSERT INTO {E_PROMO.TABLE.value} ({','.join(cols)}) VALUES ({placeholders})"
            self.db.run_query(sql, tuple(vals))
            return {"status": "success", "message": "Promoción creada"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def actualizar_promo(
        self,
        promo_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            allowed = {e.value for e in E_PROMO} - {E_PROMO.TABLE.value, E_PROMO.ID.value, E_PROMO.CREATED_AT.value}
            sets, params = [], []
            for k, v in (kwargs or {}).items():
                if k in allowed:
                    sets.append(f"{k}=%s")
                    params.append(v)
            if not sets:
                return {"status": "success", "message": "Sin cambios"}
            params.append(int(promo_id))
            sql = f"UPDATE {E_PROMO.TABLE.value} SET {', '.join(sets)} WHERE {E_PROMO.ID.value}=%s"
            self.db.run_query(sql, tuple(params))
            return {"status": "success", "message": "Promoción actualizada"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def eliminar_promo(self, promo_id: int) -> Dict[str, Any]:
        try:
            sql = f"DELETE FROM {E_PROMO.TABLE.value} WHERE {E_PROMO.ID.value}=%s"
            self.db.run_query(sql, (int(promo_id),))
            return {"status": "success", "message": "Promoción eliminada"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    # ======================== Cálculo ========================
    def aplicar_descuento(
        self,
        *,
        precio_base: float | Decimal,
        promo_row: Dict[str, Any]
    ) -> Tuple[Decimal, Decimal]:
        """
        Devuelve (precio_final, descuento_aplicado) con 2 decimales.
        """
        p = Decimal(str(precio_base or 0)).quantize(Decimal("0.01"))
        if not promo_row:
            return (p, Decimal("0.00"))

        stored_final = promo_row.get(E_PROMO.PRECIO_FINAL.value)
        final_from_db: Optional[Decimal] = None
        if stored_final is not None:
            try:
                final_from_db = Decimal(str(stored_final)).quantize(Decimal("0.01"))
            except Exception:
                final_from_db = None
        if final_from_db is not None:
            if final_from_db > p:
                final_from_db = p
            if final_from_db < Decimal("0.00"):
                final_from_db = Decimal("0.00")
            desc_db = (p - final_from_db).quantize(Decimal("0.01"))
            return (final_from_db, desc_db)

        tipo = str(promo_row.get(E_PROMO.TIPO_DESC.value) or "").lower()
        val  = Decimal(str(promo_row.get(E_PROMO.VALOR_DESC.value) or 0)).quantize(Decimal("0.01"))

        if tipo == E_PROMO_TIPO.PORCENTAJE.value:
            desc = (p * val) / Decimal("100")
        else:
            desc = val

        # No permitir negativos
        if desc > p:
            desc = p

        final = (p - desc).quantize(Decimal("0.01"))
        return (final, desc)
