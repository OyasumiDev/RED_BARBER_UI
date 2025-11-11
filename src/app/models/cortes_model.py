# app/models/cortes_model.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date, time
from decimal import Decimal

from app.config.db.database_mysql import DatabaseMysql
from app.core.enums.e_cortes import E_CORTE, E_CORTE_TIPO

# FKs a módulos foráneos (usamos sus enums reales si existen)
from app.core.enums.e_servicios import E_SERV          # servicios(id, precio_base, monto_libre)  # noqa
from app.core.enums.e_trabajadores import E_TRABAJADORES  # trabajadores(id, comision_porcentaje) # noqa
from app.core.enums.e_agenda import E_AGENDA, E_AGENDA_ESTADO  # agenda_citas                    # noqa
from app.core.enums.e_promos import E_PROMO, E_PROMO_TIPO      # promos                           # noqa

# Models para cálculos integrados
from app.models.servicios_model import ServiciosModel  # precio_base / monto_libre  :contentReference[oaicite:19]{index=19}
from app.models.agenda_model import AgendaModel                  # actualizar_cita(...estado=COMPLETADA)  :contentReference[oaicite:21]{index=21}
from app.models.promos_model import PromosModel                  # find_applicable() / aplicar_descuento()  :contentReference[oaicite:22]{index=22}


class CortesModel:
    """
    Registro de cortes/pagos, agrupables por día, con:
    - FK opcional a agenda (para cortes agendados) -> al crear, se marca la cita como COMPLETADA.
    - FK opcional a servicio (o monto libre si el servicio lo permite).
    - FK opcional a promo aplicada.
    - Cálculo de descuento contra precio base del servicio o monto libre.
    """

    def __init__(self) -> None:
        self.db = DatabaseMysql()
        self._ensure_schema()
        self.servicios = ServiciosModel()
        self.agenda    = AgendaModel()
        self.promos    = PromosModel()

    # ============================ DDL ============================
    def _ensure_schema(self) -> None:
        stbl, sid = E_SERV.TABLE.value, E_SERV.ID.value
        ttab, tid = E_TRABAJADORES.TABLE.value, E_TRABAJADORES.ID.value
        atab, aid = E_AGENDA.TABLE.value, "id"
        ptab, pid = E_PROMO.TABLE.value, E_PROMO.ID.value

        sql = f"""
        CREATE TABLE IF NOT EXISTS {E_CORTE.TABLE.value} (
            {E_CORTE.ID.value} INT AUTO_INCREMENT PRIMARY KEY,
            {E_CORTE.FECHA_HORA.value} DATETIME NOT NULL,

            {E_CORTE.TIPO.value} ENUM('{E_CORTE_TIPO.AGENDADO.value}','{E_CORTE_TIPO.LIBRE.value}') NOT NULL,
            {E_CORTE.TRABAJADOR_ID.value} INT NOT NULL,
            {E_CORTE.SERVICIO_ID.value} INT NULL,
            {E_CORTE.AGENDA_ID.value} INT NULL,
            {E_CORTE.PROMO_ID.value} INT NULL,

            {E_CORTE.PRECIO_BASE.value} DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            {E_CORTE.DESCUENTO.value}   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            {E_CORTE.TOTAL.value}       DECIMAL(10,2) NOT NULL DEFAULT 0.00,

            {E_CORTE.COM_PCT.value}   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            {E_CORTE.COM_MONTO.value} DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            {E_CORTE.SUC_MONTO.value} DECIMAL(10,2) NOT NULL DEFAULT 0.00,

            {E_CORTE.DESCRIPCION.value} VARCHAR(240) NULL,

            {E_CORTE.CREATED_BY.value} INT NULL,
            {E_CORTE.UPDATED_BY.value} INT NULL,
            {E_CORTE.CREATED_AT.value} DATETIME DEFAULT CURRENT_TIMESTAMP,
            {E_CORTE.UPDATED_AT.value} DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            CONSTRAINT fk_cortes_trab FOREIGN KEY ({E_CORTE.TRABAJADOR_ID.value}) REFERENCES {ttab}({tid})
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CONSTRAINT fk_cortes_serv FOREIGN KEY ({E_CORTE.SERVICIO_ID.value}) REFERENCES {stbl}({sid})
                ON UPDATE CASCADE ON DELETE SET NULL,
            CONSTRAINT fk_cortes_agenda FOREIGN KEY ({E_CORTE.AGENDA_ID.value}) REFERENCES {atab}({aid})
                ON UPDATE CASCADE ON DELETE SET NULL,
            CONSTRAINT fk_cortes_promo FOREIGN KEY ({E_CORTE.PROMO_ID.value}) REFERENCES {ptab}({pid})
                ON UPDATE CASCADE ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        self.db.run_query(sql)

        # Índices de uso común
        self._ensure_index("idx_cortes_fecha", E_CORTE.FECHA_HORA.value)
        self._ensure_index("idx_cortes_trab",  E_CORTE.TRABAJADOR_ID.value)
        self._ensure_index("idx_cortes_serv",  E_CORTE.SERVICIO_ID.value)
        self._ensure_index("idx_cortes_agenda",E_CORTE.AGENDA_ID.value)

    def _ensure_index(self, name: str, col: str) -> None:
        q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s LIMIT 1
        """
        row = self.db.get_data(q, (E_CORTE.TABLE.value, name), dictionary=True)
        if not row:
            self.db.run_query(f"CREATE INDEX {name} ON {E_CORTE.TABLE.value} ({col})")

    # ===================== Lógica de cálculo =====================
    def _calcular_totales(
        self,
        *,
        servicio_row: Optional[Dict],
        dt: datetime,
        aplicar_promo: bool,
        precio_base_manual: Optional[float] = None
    ) -> Tuple[Decimal, Decimal, Decimal, Optional[int]]:
        """Devuelve (precio_base, descuento, total, promo_id)."""
        # 1) precio base
        manual_override = None
        if precio_base_manual is not None:
            try:
                manual_override = Decimal(str(precio_base_manual))
            except Exception:
                manual_override = None

        if manual_override is not None:
            base = manual_override
        elif servicio_row:
            fallback = servicio_row.get("precio_base") or servicio_row.get("precio") or 0
            base = Decimal(str(fallback))
        else:
            # sin servicio => requiere precio manual
            base = Decimal(str(precio_base_manual or 0))

        precio_base_val = base.quantize(Decimal("0.01"))

        # 2) promo (si aplica)
        promo_id = None
        descuento = Decimal("0.00")
        srv_id_lookup = self._extract_servicio_id(servicio_row)
        if aplicar_promo and srv_id_lookup:
            pr = self.promos.find_applicable(int(srv_id_lookup), dt)  # :contentReference[oaicite:23]{index=23}
            if pr:
                total_sugerido, desc = self.promos.aplicar_descuento(precio_base=base, promo_row=pr)  # :contentReference[oaicite:24]{index=24}
                descuento = Decimal(str(desc)).quantize(Decimal("0.01"))
                total = Decimal(str(total_sugerido)).quantize(Decimal("0.01"))
                promo_id = pr.get("id")
            else:
                total = precio_base_val
        else:
            total = precio_base_val

        return (precio_base_val, descuento, total, promo_id)

    @staticmethod
    def _extract_servicio_id(servicio_row: Optional[Dict]) -> Optional[int]:
        if not servicio_row:
            return None
        for key in ("id", "ID", "id_servicio", "ID_SERVICIO"):
            val = servicio_row.get(key)
            if val in (None, "", 0):
                continue
            try:
                return int(val)
            except Exception:
                continue
        return None

    # ============================ CRUD ============================
    def crear_corte(
        self,
        *,
        trabajador_id: int,
        tipo: str,  # E_CORTE_TIPO
        servicio_id: Optional[int] = None,
        agenda_id: Optional[int] = None,
        fecha_hora: Optional[datetime] = None,
        aplicar_promo: bool = True,
        precio_base_manual: Optional[float] = None,
        descripcion: Optional[str] = None,
        created_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        - Si tipo=AGENDADO y agenda_id -> marca cita como COMPLETADA.
        - Si servicio.monto_libre=1, usar precio_base_manual si lo proveen. (servicios.precio_base/monto_libre)  :contentReference[oaicite:26]{index=26}
        - Calcula promo (si aplica) y comisión (snapshot de trabajadores.comision_porcentaje). :contentReference[oaicite:27]{index=27}
        """
        dt = fecha_hora or datetime.now()

        # Servicio (opcional)
        srv_row = None
        if servicio_id:
            try:
                srv_row = self.servicios.get_by_id(int(servicio_id))
            except Exception:
                srv_row = None

        # Cálculos
        precio_base, desc, total, promo_id = self._calcular_totales(
            servicio_row=srv_row,
            dt=dt,
            aplicar_promo=bool(aplicar_promo),
            precio_base_manual=precio_base_manual
        )

        cols = [
            E_CORTE.FECHA_HORA.value, E_CORTE.TIPO.value, E_CORTE.TRABAJADOR_ID.value,
            E_CORTE.SERVICIO_ID.value, E_CORTE.AGENDA_ID.value, E_CORTE.PROMO_ID.value,
            E_CORTE.PRECIO_BASE.value, E_CORTE.DESCUENTO.value, E_CORTE.TOTAL.value,
            E_CORTE.DESCRIPCION.value, E_CORTE.CREATED_BY.value
        ]
        vals = [
            dt, tipo, int(trabajador_id),
            int(servicio_id) if servicio_id else None,
            int(agenda_id) if agenda_id else None,
            int(promo_id) if promo_id else None,
            float(precio_base), float(desc), float(total),
            descripcion, created_by
        ]
        placeholders = ",".join(["%s"] * len(cols))
        self.db.run_query(
            f"INSERT INTO {E_CORTE.TABLE.value} ({','.join(cols)}) VALUES ({placeholders})",
            tuple(vals)
        )

        # Si viene de Agenda: marcar completada
        if agenda_id:
            self.agenda.actualizar_cita(
                cita_id=int(agenda_id),
                titulo=None,
                inicio=dt,
                fin=dt,
                estado=E_AGENDA_ESTADO.COMPLETADA.value
            )  # :contentReference[oaicite:28]{index=28}

        return {"status": "success", "message": "Corte registrado."}

    def get_by_agenda(self, agenda_id: int) -> Optional[Dict[str, Any]]:
        """Devuelve el corte asociado a una agenda, si existe."""
        try:
            q = f"SELECT * FROM {E_CORTE.TABLE.value} WHERE {E_CORTE.AGENDA_ID.value}=%s LIMIT 1"
            return self.db.get_data(q, (agenda_id,), dictionary=True)
        except Exception:
            return None

    def crear_corte_desde_cita(
        self,
        cita: Dict[str, Any],
        *,
        fecha_corte: Optional[datetime] = None,
        created_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Genera un corte AGENDADO a partir de una cita completada.
        Evita duplicados verificando si ya existe un corte ligado a la agenda.
        """
        if not cita:
            return {"status": "error", "message": "Cita no encontrada."}

        try:
            agenda_id = int(cita.get(E_AGENDA.ID.value) or cita.get("id"))
        except Exception:
            return {"status": "error", "message": "Cita sin identificador."}
        if agenda_id in (None, "", 0):
            return {"status": "error", "message": "Cita sin identificador."}

        existing = self.get_by_agenda(agenda_id)
        if existing:
            return {"status": "exists", "message": "El corte ya fue generado.", "corte": existing}

        trabajador_id = cita.get(E_AGENDA.TRABAJADOR_ID.value) or cita.get("trabajador_id")
        try:
            trabajador_id = int(trabajador_id) if trabajador_id not in (None, "", 0) else None
        except Exception:
            trabajador_id = None
        if trabajador_id is None:
            return {"status": "error", "message": "La cita no tiene trabajador asignado."}

        servicio_id = cita.get("servicio_id")
        try:
            servicio_id = int(servicio_id) if servicio_id not in (None, "", 0) else None
        except Exception:
            servicio_id = None

        descripcion = (
            cita.get(E_AGENDA.CLIENTE_NOM.value) or
            cita.get("cliente") or
            cita.get(E_AGENDA.TITULO.value) or
            f"Cita #{agenda_id}"
        )

        def _as_float(val: Any) -> Optional[float]:
            if val in (None, "", 0):
                return None
            try:
                return float(val)
            except Exception:
                return None

        precio_manual = (
            _as_float(cita.get("total")) or
            _as_float(cita.get("precio_unit")) or
            _as_float(cita.get("precio_base"))
        )

        fh = fecha_corte or cita.get(E_AGENDA.FIN.value) or cita.get("fecha_fin") or datetime.now()
        if isinstance(fh, str):
            try:
                fh = datetime.fromisoformat(fh)
            except Exception:
                fh = datetime.now()

        payload = dict(
            trabajador_id=int(trabajador_id),
            tipo=E_CORTE_TIPO.AGENDADO.value,
            servicio_id=int(servicio_id) if servicio_id else None,
            agenda_id=agenda_id,
            fecha_hora=fh,
            aplicar_promo=True,
            precio_base_manual=precio_manual,
            descripcion=descripcion,
            created_by=created_by,
        )
        return self.crear_corte(**payload)

    def eliminar_corte(self, corte_id: int) -> Dict[str, Any]:
        # (UI debe validar rol root antes de llamar)
        self.db.run_query(f"DELETE FROM {E_CORTE.TABLE.value} WHERE {E_CORTE.ID.value}=%s", (int(corte_id),))
        return {"status": "success", "message": "Corte eliminado."}

    # ===================== Listados / Reportes =====================
    def listar_por_dia(self, d: date) -> List[Dict[str, Any]]:
        q = f"""
        SELECT *
        FROM {E_CORTE.TABLE.value}
        WHERE DATE({E_CORTE.FECHA_HORA.value})=%s
        ORDER BY {E_CORTE.FECHA_HORA.value} ASC
        """
        return self.db.get_all(q, (d.isoformat(),), dictionary=True) or []

    def listar_por_rango(self, inicio: datetime, fin: datetime) -> List[Dict[str, Any]]:
        q = f"""
        SELECT *
        FROM {E_CORTE.TABLE.value}
        WHERE {E_CORTE.FECHA_HORA.value} BETWEEN %s AND %s
        ORDER BY {E_CORTE.FECHA_HORA.value} ASC
        """
        return self.db.get_all(q, (inicio, fin), dictionary=True) or []

    def totales_del_dia(self, d: date) -> Dict[str, float]:
        q = f"""
        SELECT
          COALESCE(SUM({E_CORTE.TOTAL.value}),0)      AS total_ventas,
          COALESCE(SUM({E_CORTE.COM_MONTO.value}),0) AS total_comisiones,
          COALESCE(SUM({E_CORTE.SUC_MONTO.value}),0) AS total_sucursal
        FROM {E_CORTE.TABLE.value}
        WHERE DATE({E_CORTE.FECHA_HORA.value})=%s
        """
        row = self.db.get_data(q, (d.isoformat(),), dictionary=True) or {}
        return {k: float(v or 0) for k, v in row.items()}
