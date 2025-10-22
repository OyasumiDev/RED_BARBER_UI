from __future__ import annotations
from typing import Optional, Dict, List, Tuple
from datetime import date
from decimal import Decimal
from app.config.db.database_mysql import DatabaseMysql
from app.helpers.format.db_sanitizer import DBSanitizer
from app.core.enums.e_servicios import E_SERV, E_SERV_TIPO

Money = Decimal  # para evitar floats

PRECIOS_BASE: Dict[str, Money] = {
    E_SERV_TIPO.CORTE_ADULTO.value: Money("180"),
    E_SERV_TIPO.CORTE_NINO.value:   Money("150"),
    E_SERV_TIPO.BARBA_TRAD.value:   Money("150"),
    E_SERV_TIPO.BARBA_EXPRES.value: Money("100"),
    E_SERV_TIPO.FACIAL.value:       Money("120"),
    E_SERV_TIPO.CEJA.value:         Money("20"),
    E_SERV_TIPO.LINEA.value:        Money("20"),
    E_SERV_TIPO.DISENIO.value:      Money("0"),   # se ignora si monto_libre=1
}

# Martes: override de precio en cortes
MARTES_OVERRIDE = {
    E_SERV_TIPO.CORTE_ADULTO.value: Money("150"),
    E_SERV_TIPO.CORTE_NINO.value:   Money("120"),
}

class ServiciosModel:
    """
    Catálogo de servicios + motor de promociones.
    - CRUD y semilla de predeterminados
    - Cálculo de precio con promos (Martes, Miércoles)
    """

    def __init__(self):
        self.db = DatabaseMysql()
        self._exists = self.check_table()

    # --------------------- DDL ---------------------
    def check_table(self) -> bool:
        try:
            q = f"""
            CREATE TABLE IF NOT EXISTS {E_SERV.TABLE.value}(
              {E_SERV.ID.value} INT AUTO_INCREMENT PRIMARY KEY,
              {E_SERV.NOMBRE.value} VARCHAR(150) NOT NULL,
              {E_SERV.TIPO.value}   VARCHAR(40) NOT NULL,
              {E_SERV.PRECIO.value} DECIMAL(10,2) NULL,
              {E_SERV.MONTO_LIBRE.value} TINYINT(1) NOT NULL DEFAULT 0,
              {E_SERV.ACTIVO.value} TINYINT(1) NOT NULL DEFAULT 1,
              {E_SERV.CREATED_AT.value} DATETIME DEFAULT CURRENT_TIMESTAMP,
              {E_SERV.UPDATED_AT.value} DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            self.db.run_query(q)

            # ====== FIX: crear índices sólo si no existen ======
            self._ensure_index("idx_serv_tipo",   E_SERV.TIPO.value)
            self._ensure_index("idx_serv_activo", E_SERV.ACTIVO.value)
            # (Si en el futuro quieres un índice único por tipo, usa unique=True,
            #  pero ojo: fallará si ya tienes filas duplicadas)
            # self._ensure_index("ux_serv_tipo", E_SERV.TIPO.value, unique=True)

            return True
        except Exception as ex:
            print("❌ servicios.check_table:", ex)
            return False

    # --------------------- helpers índices ---------------------
    def _index_exists(self, index_name: str) -> bool:
        try:
            q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            LIMIT 1
            """
            row = self.db.get_data(q, (E_SERV.TABLE.value, index_name), dictionary=True)
            return row is not None
        except Exception:
            return False

    def _ensure_index(self, index_name: str, column: str, *, unique: bool = False):
        """Crea el índice si no existe (compatible con MySQL que no soporta IF NOT EXISTS)."""
        try:
            if not self._index_exists(index_name):
                sql = f"CREATE {'UNIQUE ' if unique else ''}INDEX {index_name} ON {E_SERV.TABLE.value}({column})"
                self.db.run_query(sql)
        except Exception:
            # En caso de condición de carrera o permisos, sólo silenciamos el warning
            # para no romper el arranque.
            pass

    # ----------------- helpers sanitizar -----------------
    def _safe(self, row: Optional[Dict]) -> Optional[Dict]:
        return DBSanitizer.to_safe(row) if row else None

    def _list_safe(self, rows: List[Dict]) -> List[Dict]:
        return [DBSanitizer.to_safe(r) for r in (rows or [])]

    # ----------------- seed -----------------
    def seed_predeterminados(self) -> None:
        """Inserta servicios si no existen por tipo (idempotente)."""
        existentes = {r.get(E_SERV.TIPO.value) for r in (self.listar(activo=None) or [])}
        def _ins(nombre: str, tipo: str, precio: Money, libre: bool):
            if tipo in existentes:
                return
            self.crear_servicio(nombre=nombre, tipo=tipo,
                                precio_base=None if libre else float(precio),
                                monto_libre=1 if libre else 0)
        _ins("Corte Adulto", E_SERV_TIPO.CORTE_ADULTO.value, PRECIOS_BASE[E_SERV_TIPO.CORTE_ADULTO.value], False)
        _ins("Corte niño",   E_SERV_TIPO.CORTE_NINO.value,   PRECIOS_BASE[E_SERV_TIPO.CORTE_NINO.value],   False)
        _ins("Arreglo de barba tradicional", E_SERV_TIPO.BARBA_TRAD.value,   PRECIOS_BASE[E_SERV_TIPO.BARBA_TRAD.value],   False)
        _ins("Arreglo de barba Expres",      E_SERV_TIPO.BARBA_EXPRES.value, PRECIOS_BASE[E_SERV_TIPO.BARBA_EXPRES.value], False)
        _ins("Limpieza facial",              E_SERV_TIPO.FACIAL.value,       PRECIOS_BASE[E_SERV_TIPO.FACIAL.value],       False)
        _ins("Arreglo de ceja",              E_SERV_TIPO.CEJA.value,         PRECIOS_BASE[E_SERV_TIPO.CEJA.value],         False)
        _ins("Linea",                        E_SERV_TIPO.LINEA.value,        PRECIOS_BASE[E_SERV_TIPO.LINEA.value],        False)
        _ins("Diseños personalizados",       E_SERV_TIPO.DISENIO.value,      PRECIOS_BASE[E_SERV_TIPO.DISENIO.value],      True)

    # ----------------- CRUD -----------------
    def listar(self, *, activo: Optional[bool]=True, search: Optional[str]=None) -> List[Dict]:
        conds, params = [], []
        if activo is not None:
            conds.append(f"{E_SERV.ACTIVO.value}=%s"); params.append(1 if activo else 0)
        if search:
            conds.append(f"{E_SERV.NOMBRE.value} LIKE %s"); params.append(f"%{search}%")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        q = f"SELECT * FROM {E_SERV.TABLE.value} {where} ORDER BY {E_SERV.NOMBRE.value} ASC"
        rows = self.db.get_all(q, tuple(params), dictionary=True) or []
        return self._list_safe(rows)

    def get_by_id(self, servicio_id: int) -> Optional[Dict]:
        q = f"SELECT * FROM {E_SERV.TABLE.value} WHERE {E_SERV.ID.value}=%s"
        return self._safe(self.db.get_data(q, (servicio_id,), dictionary=True))

    def crear_servicio(self, *, nombre: str, tipo: str, precio_base: Optional[float], monto_libre: int=0, activo: int=1) -> Dict:
        try:
            q = f"""
            INSERT INTO {E_SERV.TABLE.value}
              ({E_SERV.NOMBRE.value},{E_SERV.TIPO.value},{E_SERV.PRECIO.value},
               {E_SERV.MONTO_LIBRE.value},{E_SERV.ACTIVO.value})
            VALUES (%s,%s,%s,%s,%s)
            """
            self.db.run_query(q, (nombre, tipo, precio_base, int(monto_libre), int(activo)))
            return {"status":"success","message":"Servicio creado"}
        except Exception as ex:
            return {"status":"error","message":str(ex)}

    def actualizar_servicio(self, servicio_id: int, *, nombre: Optional[str]=None, tipo: Optional[str]=None,
                            precio_base: Optional[float]=None, monto_libre: Optional[int]=None, activo: Optional[int]=None) -> Dict:
        try:
            sets, params = [], []
            def _set(col, v): sets.append(f"{col}=%s"); params.append(v)
            if nombre is not None: _set(E_SERV.NOMBRE.value, nombre)
            if tipo is not None: _set(E_SERV.TIPO.value, tipo)
            if precio_base is not None: _set(E_SERV.PRECIO.value, precio_base)
            if monto_libre is not None: _set(E_SERV.MONTO_LIBRE.value, int(monto_libre))
            if activo is not None: _set(E_SERV.ACTIVO.value, int(activo))
            if not sets: return {"status":"success","message":"Sin cambios"}
            params.append(servicio_id)
            uq = f"UPDATE {E_SERV.TABLE.value} SET {', '.join(sets)} WHERE {E_SERV.ID.value}=%s"
            self.db.run_query(uq, tuple(params))
            return {"status":"success","message":"Servicio actualizado"}
        except Exception as ex:
            return {"status":"error","message":str(ex)}

    def eliminar_servicio(self, servicio_id: int) -> Dict:
        try:
            q = f"DELETE FROM {E_SERV.TABLE.value} WHERE {E_SERV.ID.value}=%s"
            self.db.run_query(q, (servicio_id,))
            return {"status":"success","message":"Servicio eliminado"}
        except Exception as ex:
            return {"status":"error","message":str(ex)}

    # ----------------- Promociones -----------------
    def _precio_base(self, tipo: str, precio_bd: Optional[float]) -> Money:
        if precio_bd is not None:
            return Money(str(precio_bd))
        return PRECIOS_BASE.get(tipo, Money("0"))

    def precio_unitario(self, servicio_id: int, fecha: date, *, cantidad: int = 1, precio_personalizado: Optional[Money]=None) -> Tuple[Money, Dict]:
        """
        Devuelve (total, detalle) con promos aplicadas para 'cantidad' unidades.
        Para 'Diseños personalizados' puedes pasar precio_personalizado.
        """
        s = self.get_by_id(servicio_id)
        if not s or not s.get(E_SERV.ACTIVO.value, 1):
            return Money("0"), {"aplica": False, "motivo": "Inactivo"}

        tipo = s.get(E_SERV.TIPO.value)
        base = self._precio_base(tipo, s.get(E_SERV.PRECIO.value))
        # monto libre
        if int(s.get(E_SERV.MONTO_LIBRE.value, 0)) == 1:
            base = Money(str(precio_personalizado or Money("0")))

        dia_sem = fecha.weekday()  # 0=Monday .. 6=Sunday
        detalle = {"aplica": False, "promo": None, "unit_base": str(base), "cantidad": cantidad}

        total: Money = Money("0")

        # ---- Martes: override precio para cortes ----
        if dia_sem == 1 and tipo in MARTES_OVERRIDE:
            base = MARTES_OVERRIDE[tipo]
            detalle.update({"aplica": True, "promo": "martes_override", "unit_final": str(base)})

        # ---- Miércoles: 2x1.5 en cortes (por tipo) ----
        if dia_sem == 2 and tipo in (E_SERV_TIPO.CORTE_ADULTO.value, E_SERV_TIPO.CORTE_NINO.value) and cantidad >= 2:
            pares = cantidad // 2
            resto = cantidad % 2
            total = pares * (base * Money("1.5")) + resto * base
            detalle.update({"aplica": True, "promo": "miercoles_2x1.5", "pares": pares, "resto": resto, "unit_base": str(base)})
            return total, detalle

        # default (sin miércoles)
        total = base * Money(str(cantidad))
        return total, detalle
