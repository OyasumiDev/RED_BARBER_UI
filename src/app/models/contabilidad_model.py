# app/models/contabilidad_model.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum

from app.config.db.database_mysql import DatabaseMysql
from app.models.cortes_model import CortesModel
from app.models.trabajadores_model import TrabajadoresModel

# =========================================================
# Enumeradores (en este mismo módulo)
# =========================================================
class E_CORTE(StrEnum):
    TABLE         = "cortes"
    ID            = "id"
    TRABAJADOR_ID = "trabajador_id"
    FECHA_HORA    = "fecha_hora"

    TOTAL         = "total"       # total final del corte (ya con promos/descuentos)
    COM_PCT       = "com_pct"     # % snapshot en el momento del corte
    COM_MONTO     = "com_monto"   # $ snapshot empleado
    SUC_MONTO     = "suc_monto"   # $ snapshot empresa

    SERVICIO_NOMBRE = "servicio_nombre"  # opcional común
    PRECIO_FINAL    = "precio_final"     # compatibilidad

class E_NOMINA(StrEnum):
    TABLE         = "nomina_pagos"
    ID            = "id"
    TRABAJADOR_ID = "trabajador_id"
    MONTO         = "monto"
    FECHA         = "fecha"
    NOTA          = "nota"
    INICIO_PERIODO= "inicio_periodo"
    FIN_PERIODO   = "fin_periodo"
    CREATED_BY    = "created_by"
    CREATED_AT    = "created_at"

class E_TRAB(StrEnum):
    TABLE         = "trabajadores"
    ID            = "id"
    NOMBRE        = "nombre"
    COMISION_PCT  = "comision_porcentaje"  # % actual en el perfil

# =========================================================
# Aliases tolerantes (nombres antiguos / variantes)
# =========================================================
ALIASES = {
    "TOTAL":       [E_CORTE.TOTAL.value, E_CORTE.PRECIO_FINAL.value, "monto_final", "TOTAL", "precio_final", "total"],
    "TRAB_ID":     [E_CORTE.TRABAJADOR_ID.value, "id_trabajador", "TRABAJADOR_ID", "trabajador_id"],
    "FECHA":       [E_CORTE.FECHA_HORA.value, "fecha", "fecha_hora", "FECHA_HORA"],
    "COM_PCT":     [E_CORTE.COM_PCT.value, "comision_pct", "comision_porcentaje", "pct", "porcentaje"],
    "COM_MONTO":   [E_CORTE.COM_MONTO.value, "comision_monto", "gan_empleado", "gan_trab", "empleado_monto", "com_monto"],
    "SUC_MONTO":   [E_CORTE.SUC_MONTO.value, "sucursal_monto", "gan_empresa", "empresa_monto", "negocio", "suc_monto"],
    "SERVICIO":    [E_CORTE.SERVICIO_NOMBRE.value, "servicio_txt", "servicio"],
    "ID_CORTE":    [E_CORTE.ID.value, "corte_id"],
    "AGENDA_ID":   ["agenda_id", "cita_id"],

    # Trabajadores
    "TRAB_NOMBRE": [E_TRAB.NOMBRE.value, "NOMBRE", "name"],
    "TRAB_PCT":    [E_TRAB.COMISION_PCT.value, "comision_pct", "comision", "pct"],
}

# =========================================================
# Helpers genéricos
# =========================================================
Q2 = Decimal("0.01")

def _dec(v: Any, fb: str = "0.00") -> Decimal:
    try:
        return Decimal(str(v)).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal(fb)

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default

def _row_get(row: Dict[str, Any], keys: List[str]) -> Any:
    """Devuelve el primer valor existente en row (case-insensitive)."""
    if not row:
        return None
    lower = {str(k).lower(): k for k in row.keys()}
    for k in keys:
        lk = str(k).lower()
        if lk in lower:
            return row[lower[lk]]
    return None

def _get_total_from_corte(row: Dict[str, Any]) -> Decimal:
    return _dec(_row_get(row, ALIASES["TOTAL"]) or 0)

# ==========================
# NOMINA (persistente)
# ==========================
class NominaModel:
    """
    Tabla de pagos a empleados (usa enumerador E_NOMINA para columnas).
    Métodos: registrar_pago, total_pagado_por_rango, listar_pagos_por_rango, eliminar_pago, healthcheck
    """
    TABLE = E_NOMINA.TABLE.value

    def __init__(self, db: Optional[DatabaseMysql] = None):
        self.db = db or DatabaseMysql()
        self.db.ensure_connection()
        self._ensure_schema()

    def _ensure_schema(self):
        q = f"""
        CREATE TABLE IF NOT EXISTS `{self.TABLE}` (
            `{E_NOMINA.ID.value}` INT AUTO_INCREMENT PRIMARY KEY,
            `{E_NOMINA.TRABAJADOR_ID.value}` INT NOT NULL,
            `{E_NOMINA.MONTO.value}` DECIMAL(10,2) NOT NULL,
            `{E_NOMINA.FECHA.value}` DATETIME NOT NULL,
            `{E_NOMINA.NOTA.value}` TEXT NULL,
            `{E_NOMINA.INICIO_PERIODO.value}` DATETIME NULL,
            `{E_NOMINA.FIN_PERIODO.value}` DATETIME NULL,
            `{E_NOMINA.CREATED_BY.value}` INT NULL,
            `{E_NOMINA.CREATED_AT.value}` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_trabajador_fecha` (`{E_NOMINA.TRABAJADOR_ID.value}`, `{E_NOMINA.FECHA.value}`),
            INDEX `idx_periodo` (`{E_NOMINA.INICIO_PERIODO.value}`, `{E_NOMINA.FIN_PERIODO.value}`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        self.db.run_query(q)

    def registrar_pago(
        self,
        *,
        trabajador_id: int,
        monto: float | Decimal,
        fecha: datetime,
        nota: Optional[str] = None,
        inicio_periodo: Optional[datetime] = None,
        fin_periodo: Optional[datetime] = None,
        created_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        q = f"""
        INSERT INTO `{self.TABLE}`
        (`{E_NOMINA.TRABAJADOR_ID.value}`, `{E_NOMINA.MONTO.value}`, `{E_NOMINA.FECHA.value}`,
         `{E_NOMINA.NOTA.value}`, `{E_NOMINA.INICIO_PERIODO.value}`, `{E_NOMINA.FIN_PERIODO.value}`, `{E_NOMINA.CREATED_BY.value}`)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            int(trabajador_id),
            float(_dec(monto)),
            fecha,
            nota,
            inicio_periodo,
            fin_periodo,
            created_by,
        )
        try:
            self.db.run_query(q, params)
            return {"status": "success"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def total_pagado_por_rango(self, *, trabajador_id: int, inicio: datetime, fin: datetime) -> float:
        q = f"""
        SELECT COALESCE(SUM(`{E_NOMINA.MONTO.value}`), 0) AS total
        FROM `{self.TABLE}`
        WHERE `{E_NOMINA.TRABAJADOR_ID.value}` = %s
          AND `{E_NOMINA.FECHA.value}` BETWEEN %s AND %s
        """
        row = self.db.get_data(q, (int(trabajador_id), inicio, fin), dictionary=True)
        if isinstance(row, dict):
            return float(row.get("total", 0) or 0)
        if row:
            try:
                return float(row[0] or 0)
            except Exception:
                pass
        return 0.0

    def listar_pagos_por_rango(
        self, *, trabajador_id: Optional[int], inicio: datetime, fin: datetime
    ) -> List[Dict[str, Any]]:
        if trabajador_id:
            q = f"""
            SELECT `{E_NOMINA.ID.value}` AS id, `{E_NOMINA.TRABAJADOR_ID.value}` AS trabajador_id,
                   `{E_NOMINA.MONTO.value}` AS monto, `{E_NOMINA.FECHA.value}` AS fecha,
                   `{E_NOMINA.NOTA.value}` AS nota, `{E_NOMINA.INICIO_PERIODO.value}` AS inicio_periodo,
                   `{E_NOMINA.FIN_PERIODO.value}` AS fin_periodo, `{E_NOMINA.CREATED_BY.value}` AS created_by,
                   `{E_NOMINA.CREATED_AT.value}` AS created_at
            FROM `{self.TABLE}`
            WHERE `{E_NOMINA.TRABAJADOR_ID.value}` = %s
              AND `{E_NOMINA.FECHA.value}` BETWEEN %s AND %s
            ORDER BY `{E_NOMINA.FECHA.value}` DESC, `{E_NOMINA.ID.value}` DESC
            """
            return self.db.get_all(q, (int(trabajador_id), inicio, fin), dictionary=True) or []
        else:
            q = f"""
            SELECT `{E_NOMINA.ID.value}` AS id, `{E_NOMINA.TRABAJADOR_ID.value}` AS trabajador_id,
                   `{E_NOMINA.MONTO.value}` AS monto, `{E_NOMINA.FECHA.value}` AS fecha,
                   `{E_NOMINA.NOTA.value}` AS nota, `{E_NOMINA.INICIO_PERIODO.value}` AS inicio_periodo,
                   `{E_NOMINA.FIN_PERIODO.value}` AS fin_periodo, `{E_NOMINA.CREATED_BY.value}` AS created_by,
                   `{E_NOMINA.CREATED_AT.value}` AS created_at
            FROM `{self.TABLE}`
            WHERE `{E_NOMINA.FECHA.value}` BETWEEN %s AND %s
            ORDER BY `{E_NOMINA.FECHA.value}` DESC, `{E_NOMINA.ID.value}` DESC
            """
            return self.db.get_all(q, (inicio, fin), dictionary=True) or []

    def eliminar_pago(self, pago_id: int) -> Dict[str, Any]:
        q = f"DELETE FROM `{self.TABLE}` WHERE `{E_NOMINA.ID.value}` = %s"
        try:
            self.db.run_query(q, (int(pago_id),))
            return {"status": "success"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def healthcheck(self) -> Dict[str, Any]:
        try:
            r = self.db.get_data(f"SELECT COUNT(*) c FROM `{self.TABLE}`", (), dictionary=True)
            c = (r or {}).get("c", 0) if isinstance(r, dict) else (r[0] if r else 0)
            return {"ok": True, "rows": int(c or 0)}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

# ==========================
# GANANCIAS (reportes)
# ==========================
class GananciasModel:
    """
    Calcula ganancias de empleado/empresa desde 'cortes' y cruza con pagos de nómina.

    REGLAS:
    - Si existen snapshots por corte (COM_MONTO, SUC_MONTO), se usan tal cual.
    - Si faltan, se usa snapshot de porcentaje (COM_PCT) o el % del trabajador; y se calcula:
        empleado = total * pct/100 ; empresa = total - empleado
    - 'pendiente' = gan_empleado − pagado_en_rango (no negativo).
    """
    def __init__(self, nomina_model: Optional[NominaModel] = None):
        self.cortes_model = CortesModel()
        self.trab_model = TrabajadoresModel()
        self.nomina_model = nomina_model or NominaModel()

    # -- compat para distintas firmas de listar_por_rango()
    def _listar_cortes(self, inicio: datetime, fin: datetime) -> List[Dict[str, Any]]:
        try:
            return self.cortes_model.listar_por_rango(inicio, fin) or []
        except TypeError:
            return self.cortes_model.listar_por_rango(inicio=inicio, fin=fin) or []
        except Exception:
            return []

    # --- porcentaje (snapshot > perfil del trabajador > default)
    def _resolve_pct(self, corte_row: Dict[str, Any], default_pct: float = 50.0) -> float:
        pct = _row_get(corte_row, ALIASES["COM_PCT"])
        if pct not in (None, ""):
            try:
                return float(pct)
            except Exception:
                pass
        tid = _safe_int(_row_get(corte_row, ALIASES["TRAB_ID"]), 0)
        if tid:
            try:
                t = self.trab_model.get_by_id(tid) or {}
                for key in ALIASES["TRAB_PCT"]:
                    if key in t and t[key] is not None:
                        return float(t[key])
            except Exception:
                pass
        return float(default_pct)

    # --- separa ganancia a empleado y negocio (usa snapshots si existen)
    def _split_ganancias(self, corte_row: Dict[str, Any]) -> Tuple[Decimal, Decimal]:
        total = _get_total_from_corte(corte_row)

        # 1) Priorizar snapshots (COM_MONTO / SUC_MONTO)
        com_snap = _row_get(corte_row, ALIASES["COM_MONTO"])
        suc_snap = _row_get(corte_row, ALIASES["SUC_MONTO"])
        if com_snap not in (None, "") and suc_snap not in (None, ""):
            try:
                emp = _dec(com_snap)
                neg = _dec(suc_snap)
                return emp, neg
            except Exception:
                pass

        # 2) Si faltan snapshots, usar % (snapshot o perfil)
        pct = Decimal(str(self._resolve_pct(corte_row)))
        emp = (total * pct / Decimal("100")).quantize(Q2, rounding=ROUND_HALF_UP)
        neg = (total - emp).quantize(Q2, rounding=ROUND_HALF_UP)
        return emp, neg

    def resumen_por_rango(
        self, *, inicio: datetime, fin: datetime, trabajador_id: Optional[int] = None
    ) -> Dict[str, Any]:
        print(f"[GAN] resumen_por_rango inicio={inicio} fin={fin} trabajador_id={trabajador_id}")
        cortes = self._listar_cortes(inicio, fin)

        # Filtro por trabajador si aplica
        if trabajador_id not in (None, "", 0):
            tid_str = str(int(trabajador_id))
            cortes = [r for r in cortes if str(_row_get(r, ALIASES["TRAB_ID"]) or "") == tid_str]

        # Acumuladores por trabajador
        agg: Dict[int, Dict[str, Any]] = {}
        for r in cortes:
            tid = _safe_int(_row_get(r, ALIASES["TRAB_ID"]), 0)
            total = _get_total_from_corte(r)
            gan_emp, empresa = self._split_ganancias(r)

            a = agg.setdefault(
                tid,
                {
                    "trabajador_id": tid,
                    "trabajador": "",
                    "cortes": 0,
                    "total": Decimal("0.00"),
                    "gan_empleado": Decimal("0.00"),
                    "gan_empresa": Decimal("0.00"),
                    "pagado": Decimal("0.00"),
                    "pendiente": Decimal("0.00"),
                },
            )
            a["cortes"] += 1
            a["total"] += total
            a["gan_empleado"] += gan_emp
            a["gan_empresa"] += empresa

        # nombres + pagos + pendiente
        for tid, a in agg.items():
            if tid:
                try:
                    t = self.trab_model.get_by_id(tid) or {}
                    a["trabajador"] = _row_get(t, ALIASES["TRAB_NOMBRE"]) or f"Trabajador {tid}"
                except Exception:
                    a["trabajador"] = f"Trabajador {tid}"
            else:
                a["trabajador"] = "—"

            try:
                pagado = self.nomina_model.total_pagado_por_rango(
                    trabajador_id=tid, inicio=inicio, fin=fin
                ) if tid else 0.0
                a["pagado"] = _dec(pagado)
            except Exception:
                a["pagado"] = Decimal("0.00")

            a["pendiente"] = (a["gan_empleado"] - a["pagado"])
            if a["pendiente"] < 0:
                a["pendiente"] = Decimal("0.00")
            a["pendiente"] = a["pendiente"].quantize(Q2, rounding=ROUND_HALF_UP)

        rows = sorted(agg.values(), key=lambda x: (x["pendiente"], x["gan_empleado"]), reverse=True)

        totals = {
            "cortes":       sum((r["cortes"] for r in rows), 0),
            "total":        sum((r["total"] for r in rows),   Decimal("0.00")),
            "gan_empleado": sum((r["gan_empleado"] for r in rows), Decimal("0.00")),
            "gan_empresa":  sum((r["gan_empresa"]  for r in rows), Decimal("0.00")),
            "pagado":       sum((r["pagado"]       for r in rows), Decimal("0.00")),
            "pendiente":    sum((r["pendiente"]    for r in rows), Decimal("0.00")),
        }

        def _f(x): return float(_dec(x)) if isinstance(x, (str, Decimal)) else float(x)
        out = {
            "rows": [
                {
                    "trabajador_id": r["trabajador_id"],
                    "trabajador":    r["trabajador"],
                    "cortes":        int(r["cortes"]),
                    "total":         _f(r["total"]),
                    "gan_empleado":  _f(r["gan_empleado"]),
                    "gan_empresa":   _f(r["gan_empresa"]),
                    "pagado":        _f(r["pagado"]),
                    "pendiente":     _f(r["pendiente"]),
                }
                for r in rows
            ],
            "totals": {k: _f(v) if isinstance(v, Decimal) else v for k, v in totals.items()},
        }
        print(f"[GAN] resumen_por_rango OK: rows={len(out['rows'])} totals={out['totals']}")
        return out

    def detalle_trabajador(self, *, inicio: datetime, fin: datetime, trabajador_id: int) -> List[Dict[str, Any]]:
        print(f"[GAN] detalle_trabajador inicio={inicio} fin={fin} tid={trabajador_id}")
        cortes = self._listar_cortes(inicio, fin)
        tid_str = str(int(trabajador_id))
        cortes = [r for r in cortes if str(_row_get(r, ALIASES["TRAB_ID"]) or "") == tid_str]

        def _key_dt(x: Dict[str, Any]):
            return str(_row_get(x, ALIASES["FECHA"]) or "")

        out: List[Dict[str, Any]] = []
        for r in sorted(cortes, key=_key_dt):
            total = _get_total_from_corte(r)
            gan_emp, empresa = self._split_ganancias(r)
            pct = self._resolve_pct(r)

            out.append(
                {
                    "fecha_hora":   _row_get(r, ALIASES["FECHA"]),
                    "servicio":     _row_get(r, ALIASES["SERVICIO"]),
                    "total":        float(total),
                    "pct":          float(pct),
                    "gan_empleado": float(gan_emp),
                    "gan_empresa":  float(empresa),
                    "agenda_id":    _row_get(r, ALIASES["AGENDA_ID"]),
                    "corte_id":     _row_get(r, ALIASES["ID_CORTE"]),
                }
            )
        print(f"[GAN] detalle_trabajador OK: items={len(out)}")
        return out

    def healthcheck(self) -> Dict[str, Any]:
        try:
            _ = self.nomina_model.healthcheck()
            return {"ok": True}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}
