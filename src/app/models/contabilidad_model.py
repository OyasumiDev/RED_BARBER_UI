from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal

from app.config.db.database_mysql import DatabaseMysql
from app.models.cortes_model import CortesModel
from app.models.trabajadores_model import TrabajadoresModel

# =========================================================
# Enums tolerantes (E_CORTES o E_CORTE; con fallback)
# =========================================================
_EC_ENUMS: List[Any] = []
try:
    from app.core.enums.e_cortes import E_CORTE as _ECORTES
    _EC_ENUMS.append(_ECORTES)
except Exception:
    pass
try:
    from app.core.enums.e_cortes import E_CORTE as _ECORTE
    _EC_ENUMS.append(_ECORTE)
except Exception:
    pass

def _ekey(attr: str, default: str) -> str:
    for en in _EC_ENUMS:
        try:
            v = getattr(en, attr, None)
            if v is not None:
                return getattr(v, "value", v)
        except Exception:
            pass
    return default

K_TOTAL     = _ekey("TOTAL",     "total")
K_COM_MONTO = _ekey("COM_MONTO", "gan_trab")   # snapshot ganancia empleado
K_SUC_MONTO = _ekey("SUC_MONTO", "negocio")    # snapshot ganancia negocio

# =========================================================
# Helpers
# =========================================================
def _dec(v: Any, fb: str = "0.00") -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(fb)

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default

def _get_total_from_corte(row: Dict[str, Any]) -> Decimal:
    return _dec(row.get(K_TOTAL) or row.get("precio_final") or row.get("total") or 0)

# ==========================
# NOMINA (persistente)
# ==========================
class NominaModel:
    """
    Tabla de pagos a empleados.
    Métodos: registrar_pago, total_pagado_por_rango, listar_pagos_por_rango, eliminar_pago, healthcheck
    """
    TABLE = "nomina_pagos"

    def __init__(self, db: Optional[DatabaseMysql] = None):
        self.db = db or DatabaseMysql()
        self.db.ensure_connection()
        self._ensure_schema()

    def _ensure_schema(self):
        q = f"""
        CREATE TABLE IF NOT EXISTS `{self.TABLE}` (
            `id` INT AUTO_INCREMENT PRIMARY KEY,
            `trabajador_id` INT NOT NULL,
            `monto` DECIMAL(10,2) NOT NULL,
            `fecha` DATETIME NOT NULL,
            `nota` TEXT NULL,
            `inicio_periodo` DATETIME NULL,
            `fin_periodo` DATETIME NULL,
            `created_by` INT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_trabajador_fecha` (`trabajador_id`, `fecha`),
            INDEX `idx_periodo` (`inicio_periodo`, `fin_periodo`)
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
        (trabajador_id, monto, fecha, nota, inicio_periodo, fin_periodo, created_by)
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
        SELECT COALESCE(SUM(monto), 0) AS total
        FROM `{self.TABLE}`
        WHERE trabajador_id = %s
          AND fecha BETWEEN %s AND %s
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
            SELECT id, trabajador_id, monto, fecha, nota, inicio_periodo, fin_periodo, created_by, created_at
            FROM `{self.TABLE}`
            WHERE trabajador_id = %s
              AND fecha BETWEEN %s AND %s
            ORDER BY fecha DESC, id DESC
            """
            return self.db.get_all(q, (int(trabajador_id), inicio, fin), dictionary=True) or []
        else:
            q = f"""
            SELECT id, trabajador_id, monto, fecha, nota, inicio_periodo, fin_periodo, created_by, created_at
            FROM `{self.TABLE}`
            WHERE fecha BETWEEN %s AND %s
            ORDER BY fecha DESC, id DESC
            """
            return self.db.get_all(q, (inicio, fin), dictionary=True) or []

    def eliminar_pago(self, pago_id: int) -> Dict[str, Any]:
        q = f"DELETE FROM `{self.TABLE}` WHERE id = %s"
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
    No crea tablas.
    """
    def __init__(self, nomina_model: Optional[NominaModel] = None):
        self.cortes_model = CortesModel()
        self.trab_model = TrabajadoresModel()
        self.nomina_model = nomina_model or NominaModel()

    # -- compat para distintas firmas de listar_por_rango()
    def _listar_cortes(self, inicio: datetime, fin: datetime) -> List[Dict[str, Any]]:
        try:
            # firma posicional común
            return self.cortes_model.listar_por_rango(inicio, fin) or []
        except TypeError:
            # algunos modelos aceptan kwargs
            return self.cortes_model.listar_por_rango(inicio=inicio, fin=fin) or []
        except Exception:
            return []

    # --- porcentaje (snapshot > perfil del trabajador > default)
    def _resolve_pct(self, corte_row: Dict[str, Any], default_pct: float = 50.0) -> float:
        for k in ("comision_pct_snapshot", "comision_pct", "comision_porcentaje"):
            if k in corte_row and corte_row[k] not in (None, ""):
                try:
                    return float(corte_row[k])
                except Exception:
                    pass
        tid = _safe_int(corte_row.get("trabajador_id"), 0)
        if tid:
            try:
                t = self.trab_model.get_by_id(tid) or {}
                for key in ("comision_porcentaje", "comision_pct", "comision"):
                    if key in t and t[key] is not None:
                        return float(t[key])
            except Exception:
                pass
        return float(default_pct)

    # --- separa ganancia a empleado y negocio (usa snapshots si existen)
    def _split_ganancias(self, corte_row: Dict[str, Any]) -> Tuple[Decimal, Decimal]:
        total = _get_total_from_corte(corte_row)
        com_snap = corte_row.get(K_COM_MONTO)
        suc_snap = corte_row.get(K_SUC_MONTO)
        if com_snap not in (None, "") and suc_snap not in (None, ""):
            try:
                emp = _dec(com_snap)
                neg = _dec(suc_snap)
                return emp, neg
            except Exception:
                pass
        pct = Decimal(str(self._resolve_pct(corte_row)))
        emp = (total * pct / Decimal("100")).quantize(Decimal("0.01"))
        return emp, (total - emp).quantize(Decimal("0.01"))

    def resumen_por_rango(
        self, *, inicio: datetime, fin: datetime, trabajador_id: Optional[int] = None
    ) -> Dict[str, Any]:
        cortes = self._listar_cortes(inicio, fin)
        if trabajador_id:
            tid = str(int(trabajador_id))
            cortes = [r for r in cortes if str(r.get("trabajador_id") or "") == tid]

        agg: Dict[int, Dict[str, Any]] = {}
        for r in cortes:
            tid = _safe_int(r.get("trabajador_id"), 0)
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
                    a["trabajador"] = t.get("nombre") or t.get("NOMBRE") or f"Trabajador {tid}"
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

            a["pendiente"] = (a["gan_empleado"] - a["pagado"]).quantize(Decimal("0.01"))

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
        return {
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

    def detalle_trabajador(self, *, inicio: datetime, fin: datetime, trabajador_id: int) -> List[Dict[str, Any]]:
        cortes = self._listar_cortes(inicio, fin)
        tid = str(int(trabajador_id))
        cortes = [r for r in cortes if str(r.get("trabajador_id") or "") == tid]

        def _key_dt(x: Dict[str, Any]):  # orden por fecha/hora si existe
            return str(x.get("fecha_hora") or x.get("fecha") or "")

        out: List[Dict[str, Any]] = []
        for r in sorted(cortes, key=_key_dt):
            total = _get_total_from_corte(r)
            gan_emp, empresa = self._split_ganancias(r)
            pct = self._resolve_pct(r)
            out.append(
                {
                    "fecha_hora":   r.get("fecha_hora") or r.get("fecha"),
                    "servicio":     r.get("servicio_nombre") or r.get("servicio_txt"),
                    "total":        float(total),
                    "pct":          float(pct),
                    "gan_empleado": float(gan_emp),
                    "gan_empresa":  float(empresa),
                    "agenda_id":    r.get("agenda_id") or r.get("cita_id"),
                    "corte_id":     r.get("id"),
                }
            )
        return out

    def healthcheck(self) -> Dict[str, Any]:
        try:
            _ = self.nomina_model.healthcheck()
            return {"ok": True}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}
