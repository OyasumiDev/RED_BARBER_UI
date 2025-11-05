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
from app.models.trabajadores_model import TrabajadoresModel     # comision_porcentaje  :contentReference[oaicite:20]{index=20}
from app.models.agenda_model import AgendaModel                  # actualizar_cita(...estado=COMPLETADA)  :contentReference[oaicite:21]{index=21}
from app.models.promos_model import PromosModel                  # find_applicable() / aplicar_descuento()  :contentReference[oaicite:22]{index=22}


class CortesModel:
    """
    Registro de cortes/pagos, agrupables por día, con:
    - FK opcional a agenda (para cortes agendados) -> al crear, se marca la cita como COMPLETADA.
    - FK opcional a servicio (o monto libre si el servicio lo permite).
    - FK opcional a promo aplicada.
    - Cálculo de descuento y comisión (snapshot).
    """

    def __init__(self) -> None:
        self.db = DatabaseMysql()
        self._ensure_schema()
        self.servicios = ServiciosModel()
        self.trabajos  = TrabajadoresModel()
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
    def _calcular_precios_y_comision(
        self,
        *,
        servicio_row: Optional[Dict],
        trabajador_id: int,
        dt: datetime,
        aplicar_promo: bool,
        precio_base_manual: Optional[float] = None
    ) -> Tuple[Decimal, Decimal, Decimal, Optional[int], Decimal, Decimal]:
        """
        Devuelve:
        (precio_base, descuento, total, promo_id, comision_pct, comision_monto)
        """
        # 1) precio base
        if servicio_row:
            is_libre = bool(servicio_row.get("monto_libre", 0))
            base = Decimal(str(
                precio_base_manual if (is_libre and precio_base_manual is not None)
                else (servicio_row.get("precio_base") or 0)
            ))
        else:
            # sin servicio => requiere precio manual
            base = Decimal(str(precio_base_manual or 0))

        # 2) promo (si aplica)
        promo_id = None
        descuento = Decimal("0.00")
        if aplicar_promo and servicio_row and servicio_row.get("id"):
            pr = self.promos.find_applicable(int(servicio_row["id"]), dt)  # :contentReference[oaicite:23]{index=23}
            if pr:
                # misma función que tu modelo de promos para cálculo exacto
                total_sugerido, desc = self.promos.aplicar_descuento(precio_base=base, promo_row=pr)  # :contentReference[oaicite:24]{index=24}
                descuento = desc
                base = (base - descuento).quantize(Decimal("0.01"))
                promo_id = pr.get("id")

        total = base.quantize(Decimal("0.01"))

        # 3) comisión (snapshot)
        trab = self.trabajos.get_by_id(trabajador_id) or {}  # :contentReference[oaicite:25]{index=25}
        pct = Decimal(str(trab.get("comision_porcentaje", 0)))
        com = (total * pct / Decimal("100")).quantize(Decimal("0.01"))

        return (total + descuento, descuento, total, promo_id, pct, com)

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
            # lectura directa por ID
            srv_row = self.servicios.get_all(where=f"id = {int(servicio_id)}", params=None)  # API flexible en servicios_model
            srv_row = (srv_row or [None])[0]

        # Cálculos
        precio_base, desc, total, promo_id, pct, com = self._calcular_precios_y_comision(
            servicio_row=srv_row,
            trabajador_id=int(trabajador_id),
            dt=dt,
            aplicar_promo=bool(aplicar_promo),
            precio_base_manual=precio_base_manual
        )
        suc = (total - com).quantize(Decimal("0.01"))

        cols = [
            E_CORTE.FECHA_HORA.value, E_CORTE.TIPO.value, E_CORTE.TRABAJADOR_ID.value,
            E_CORTE.SERVICIO_ID.value, E_CORTE.AGENDA_ID.value, E_CORTE.PROMO_ID.value,
            E_CORTE.PRECIO_BASE.value, E_CORTE.DESCUENTO.value, E_CORTE.TOTAL.value,
            E_CORTE.COM_PCT.value, E_CORTE.COM_MONTO.value, E_CORTE.SUC_MONTO.value,
            E_CORTE.DESCRIPCION.value, E_CORTE.CREATED_BY.value
        ]
        vals = [
            dt, tipo, int(trabajador_id),
            int(servicio_id) if servicio_id else None,
            int(agenda_id) if agenda_id else None,
            int(promo_id) if promo_id else None,
            float(precio_base), float(desc), float(total),
            float(pct), float(com), float(suc),
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
