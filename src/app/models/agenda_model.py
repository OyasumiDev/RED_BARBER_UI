# app/models/agenda_model.py
from __future__ import annotations
from typing import Optional, Dict, List, Tuple
from datetime import datetime, date
from app.config.db.database_mysql import DatabaseMysql
from app.helpers.format.db_sanitizer import DBSanitizer
from app.core.enums.e_agenda import E_AGENDA, E_AGENDA_ESTADO


def _combine_dt(d: date | datetime, hhmm: str) -> datetime:
    """Combina una fecha con una hora 'HH:MM' en un datetime."""
    if isinstance(d, datetime):
        d = d.date()
    hh, mm = [int(x) for x in (hhmm or "00:00").split(":")]
    return datetime(d.year, d.month, d.day, hh, mm)


class AgendaModel:
    """
    Citas de agenda.
    - CRUD + cancelar/completar
    - Listado por día y por rango (con búsqueda 'q')
    - Validación de solapes por trabajador
    - Compatibilidad con UI por-día (fecha + hora_inicio/hora_fin) y estilo clásico (inicio/fin)
    """

    def __init__(self, empresa_id: int = 1):
        self.db = DatabaseMysql()
        self.empresa_id = empresa_id
        self._exists_table = self.check_table()

    # ===================== DDL =====================
    def check_table(self) -> bool:
        """Crea tabla + índices si no existen (sin duplicarlos)."""
        try:
            q = f"""
            CREATE TABLE IF NOT EXISTS {E_AGENDA.TABLE.value} (
                {E_AGENDA.ID.value} INT AUTO_INCREMENT PRIMARY KEY,
                {E_AGENDA.EMPRESA_ID.value} INT NOT NULL DEFAULT 1,
                {E_AGENDA.TITULO.value} VARCHAR(150) NOT NULL,
                {E_AGENDA.NOTAS.value} VARCHAR(300) NULL,
                {E_AGENDA.TRABAJADOR_ID.value} INT NULL,
                {E_AGENDA.CLIENTE_NOM.value} VARCHAR(120) NULL,
                {E_AGENDA.CLIENTE_TEL.value} VARCHAR(30) NULL,
                {E_AGENDA.INICIO.value} DATETIME NOT NULL,
                {E_AGENDA.FIN.value} DATETIME NOT NULL,
                {E_AGENDA.TODO_DIA.value} TINYINT(1) NOT NULL DEFAULT 0,
                {E_AGENDA.COLOR.value} VARCHAR(20) NULL,
                {E_AGENDA.ESTADO.value} ENUM('{E_AGENDA_ESTADO.PROGRAMADA.value}',
                                            '{E_AGENDA_ESTADO.CANCELADA.value}',
                                            '{E_AGENDA_ESTADO.COMPLETADA.value}')
                    NOT NULL DEFAULT '{E_AGENDA_ESTADO.PROGRAMADA.value}',
                {E_AGENDA.CREATED_BY.value} INT NULL,
                {E_AGENDA.UPDATED_BY.value} INT NULL,
                {E_AGENDA.CREATED_AT.value} DATETIME DEFAULT CURRENT_TIMESTAMP,
                {E_AGENDA.UPDATED_AT.value} DATETIME DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            self.db.run_query(q)

            def _index_exists(table: str, key_name: str) -> bool:
                qi = f"SHOW INDEX FROM {table} WHERE Key_name=%s"
                row = self.db.get_data(qi, (key_name,), dictionary=True)
                return row is not None

            table = E_AGENDA.TABLE.value
            # Índices frecuentes
            if not _index_exists(table, "idx_agenda_empresa"):
                self.db.run_query(f"CREATE INDEX idx_agenda_empresa ON {table} ({E_AGENDA.EMPRESA_ID.value})")
            if not _index_exists(table, "idx_agenda_estado"):
                self.db.run_query(f"CREATE INDEX idx_agenda_estado ON {table} ({E_AGENDA.ESTADO.value})")
            if not _index_exists(table, "idx_agenda_inicio"):
                self.db.run_query(f"CREATE INDEX idx_agenda_inicio ON {table} ({E_AGENDA.INICIO.value})")
            if not _index_exists(table, "idx_agenda_fin"):
                self.db.run_query(f"CREATE INDEX idx_agenda_fin ON {table} ({E_AGENDA.FIN.value})")
            if not _index_exists(table, "idx_agenda_trabajador"):
                self.db.run_query(f"CREATE INDEX idx_agenda_trabajador ON {table} ({E_AGENDA.TRABAJADOR_ID.value})")
            if not _index_exists(table, "idx_agenda_rango"):
                self.db.run_query(
                    f"CREATE INDEX idx_agenda_rango ON {table} "
                    f"({E_AGENDA.TRABAJADOR_ID.value}, {E_AGENDA.INICIO.value}, {E_AGENDA.FIN.value}, {E_AGENDA.ESTADO.value})"
                )
            return True
        except Exception as ex:
            print(f"❌ Error creando tabla agenda: {ex}")
            return False

    # ===================== Helpers =====================
    def _safe(self, row: Optional[Dict]) -> Optional[Dict]:
        return DBSanitizer.to_safe(row) if row else None

    def _list_safe(self, rows: List[Dict]) -> List[Dict]:
        return [DBSanitizer.to_safe(r) for r in (rows or [])]

    # ===================== Consultas =====================
    def get_by_id(self, cita_id: int) -> Optional[Dict]:
        q = f"SELECT * FROM {E_AGENDA.TABLE.value} WHERE {E_AGENDA.ID.value} = %s"
        return self._safe(self.db.get_data(q, (cita_id,), dictionary=True))

    # Alias de compatibilidad con el container
    def listar_rango(
        self,
        inicio: datetime,
        fin: datetime,
        *,
        q: Optional[str] = None,
        estado: Optional[str] = None,
        trabajador_id: Optional[int] = None,
    ) -> List[Dict]:
        return self.listar_por_rango(inicio, fin, q=q, estado=estado, trabajador_id=trabajador_id)

    def listar_por_rango(
        self,
        inicio: datetime,
        fin: datetime,
        *,
        q: Optional[str] = None,
        estado: Optional[str] = None,
        trabajador_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        Devuelve todas las citas que intersectan [inicio, fin) con soporte de búsqueda q.
        Retorna alias usados por la UI diaria: fecha, hora_inicio, hora_fin, servicio, cliente_nombre.
        """
        conds = [
            f"{E_AGENDA.EMPRESA_ID.value} = %s",
            f"{E_AGENDA.FIN.value} > %s",
            f"{E_AGENDA.INICIO.value} < %s",
        ]
        params: List = [self.empresa_id, inicio, fin]
        if estado:
            conds.append(f"{E_AGENDA.ESTADO.value} = %s"); params.append(estado)
        if trabajador_id is not None:
            conds.append(f"{E_AGENDA.TRABAJADOR_ID.value} = %s"); params.append(trabajador_id)
        if q:
            like = f"%{q}%"
            conds.append(
                f"({E_AGENDA.TITULO.value} LIKE %s OR {E_AGENDA.NOTAS.value} LIKE %s "
                f"OR {E_AGENDA.CLIENTE_NOM.value} LIKE %s OR {E_AGENDA.CLIENTE_TEL.value} LIKE %s)"
            )
            params.extend([like, like, like, like])

        where = " AND ".join(conds)
        qsql = f"""
        SELECT
          {E_AGENDA.ID.value}            AS id,
          {E_AGENDA.EMPRESA_ID.value}    AS empresa_id,
          {E_AGENDA.TITULO.value}        AS titulo,
          {E_AGENDA.NOTAS.value}         AS notas,
          {E_AGENDA.TRABAJADOR_ID.value} AS trabajador_id,
          {E_AGENDA.CLIENTE_NOM.value}   AS cliente_nombre,
          {E_AGENDA.CLIENTE_TEL.value}   AS cliente_tel,
          {E_AGENDA.INICIO.value}        AS inicio,
          {E_AGENDA.FIN.value}           AS fin,
          DATE({E_AGENDA.INICIO.value})  AS fecha,
          TIME({E_AGENDA.INICIO.value})  AS hora_inicio,
          TIME({E_AGENDA.FIN.value})     AS hora_fin,
          {E_AGENDA.TODO_DIA.value}      AS todo_dia,
          {E_AGENDA.COLOR.value}         AS color,
          {E_AGENDA.ESTADO.value}        AS estado
        FROM {E_AGENDA.TABLE.value}
        WHERE {where}
        ORDER BY {E_AGENDA.INICIO.value} ASC, {E_AGENDA.FIN.value} ASC
        """
        rows = self.db.get_all(qsql, tuple(params), dictionary=True) if hasattr(self.db, "get_all") else []
        for r in rows or []:
            r["servicio"] = r.get("titulo")  # alias esperado por la UI
        return self._list_safe(rows)

    def listar_por_dia(
        self,
        dia: date | datetime,
        *,
        q: Optional[str] = None,
        estado: Optional[str] = None,
        trabajador_id: Optional[int] = None,
    ) -> List[Dict]:
        """Lista citas de un día. Acepta date o datetime y normaliza límites del día."""
        if isinstance(dia, date) and not isinstance(dia, datetime):
            d0 = datetime.combine(dia, datetime.min.time())
            d1 = datetime.combine(dia, datetime.max.time()).replace(microsecond=0)
        else:
            d0 = dia.replace(hour=0, minute=0, second=0, microsecond=0)  # type: ignore[union-attr]
            d1 = dia.replace(hour=23, minute=59, second=59, microsecond=0)  # type: ignore[union-attr]
        return self.listar_por_rango(d0, d1, q=q, estado=estado, trabajador_id=trabajador_id)

    # ===================== Reglas de negocio =====================
    def hay_conflicto(
        self,
        inicio: datetime,
        fin: datetime,
        *,
        trabajador_id: Optional[int],
        exclude_id: Optional[int] = None
    ) -> bool:
        """True si hay una cita (no cancelada) del mismo trabajador que interseca [inicio, fin)."""
        if trabajador_id is None:
            return False
        cond_ex = ""
        params: Tuple = (self.empresa_id, trabajador_id, inicio, fin, E_AGENDA_ESTADO.CANCELADA.value)
        if exclude_id is not None:
            cond_ex = f" AND {E_AGENDA.ID.value} <> %s"
            params = params + (exclude_id,)
        q = f"""
        SELECT 1
        FROM {E_AGENDA.TABLE.value}
        WHERE {E_AGENDA.EMPRESA_ID.value} = %s
          AND {E_AGENDA.TRABAJADOR_ID.value} = %s
          AND {E_AGENDA.FIN.value} > %s
          AND {E_AGENDA.INICIO.value} < %s
          AND {E_AGENDA.ESTADO.value} <> %s
          {cond_ex}
        LIMIT 1
        """
        return self.db.get_data(q, params, dictionary=True) is not None

    # ===================== Mutaciones =====================
    def crear_cita(
        self,
        *,
        # estilo clásico
        titulo: Optional[str] = None,
        inicio: Optional[datetime] = None,
        fin: Optional[datetime] = None,
        # estilo por día
        fecha: Optional[date] = None,
        hora_inicio: Optional[str] = None,
        hora_fin: Optional[str] = None,
        servicio: Optional[str] = None,
        cliente: Optional[str] = None,
        # comunes
        todo_dia: bool = False,
        color: Optional[str] = None,
        notas: Optional[str] = None,
        trabajador_id: Optional[int] = None,
        cliente_nombre: Optional[str] = None,
        cliente_tel: Optional[str] = None,
        estado: str = E_AGENDA_ESTADO.PROGRAMADA.value,
        created_by: Optional[int] = None
    ) -> Dict:
        try:
            # Mapear estilo por día si viene
            if fecha is not None and hora_inicio and hora_fin:
                inicio = _combine_dt(fecha, hora_inicio)
                fin = _combine_dt(fecha, hora_fin)
                cliente_nombre = cliente_nombre or cliente
                titulo = (titulo or servicio or (cliente_nombre or "Cita")).strip()

            if not titulo or not inicio or not fin or fin <= inicio:
                return {"status": "error", "message": "Datos insuficientes o rango inválido."}
            if estado not in [e.value for e in E_AGENDA_ESTADO]:
                return {"status": "error", "message": "Estado inválido."}
            if self.hay_conflicto(inicio, fin, trabajador_id=trabajador_id):
                return {"status": "error", "message": "Conflicto de horario con otra cita."}

            q = f"""
            INSERT INTO {E_AGENDA.TABLE.value}
              ({E_AGENDA.EMPRESA_ID.value},{E_AGENDA.TITULO.value},{E_AGENDA.NOTAS.value},
               {E_AGENDA.TRABAJADOR_ID.value},{E_AGENDA.CLIENTE_NOM.value},{E_AGENDA.CLIENTE_TEL.value},
               {E_AGENDA.INICIO.value},{E_AGENDA.FIN.value},{E_AGENDA.TODO_DIA.value},
               {E_AGENDA.COLOR.value},{E_AGENDA.ESTADO.value},{E_AGENDA.CREATED_BY.value})
            VALUES
              (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
            params = (
                self.empresa_id, titulo, notas,
                trabajador_id, cliente_nombre, cliente_tel,
                inicio, fin, 1 if todo_dia else 0,
                color, estado, created_by
            )
            self.db.run_query(q, params)
            new_id = self.db.fetch_scalar("SELECT LAST_INSERT_ID()")
            return {"status": "success", "message": "Cita creada.", "id": int(new_id or 0)}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def actualizar_cita(
        self,
        cita_id: int,
        *,
        # clásico
        titulo: Optional[str] = None,
        inicio: Optional[datetime] = None,
        fin: Optional[datetime] = None,
        # por día
        fecha: Optional[date] = None,
        hora_inicio: Optional[str] = None,
        hora_fin: Optional[str] = None,
        servicio: Optional[str] = None,
        cliente: Optional[str] = None,
        # comunes
        todo_dia: Optional[bool] = None,
        color: Optional[str] = None,
        notas: Optional[str] = None,
        trabajador_id: Optional[int] = None,
        cliente_nombre: Optional[str] = None,
        cliente_tel: Optional[str] = None,
        estado: Optional[str] = None,
        updated_by: Optional[int] = None
    ) -> Dict:
        try:
            current = self.get_by_id(cita_id)
            if not current:
                return {"status": "error", "message": "Cita no encontrada."}

            # Mapear estilo por día si llega
            if fecha is not None and hora_inicio and hora_fin:
                inicio = _combine_dt(fecha, hora_inicio)
                fin = _combine_dt(fecha, hora_fin)
                cliente_nombre = cliente_nombre or cliente
                titulo = titulo or servicio

            n_inicio = inicio or current.get(E_AGENDA.INICIO.value)
            n_fin = fin or current.get(E_AGENDA.FIN.value)
            n_trab = trabajador_id if trabajador_id is not None else current.get(E_AGENDA.TRABAJADOR_ID.value)
            if n_fin <= n_inicio:
                return {"status": "error", "message": "Fin debe ser mayor que inicio."}
            if estado is not None and estado not in [e.value for e in E_AGENDA_ESTADO]:
                return {"status": "error", "message": "Estado inválido."}
            if self.hay_conflicto(n_inicio, n_fin, trabajador_id=n_trab, exclude_id=cita_id):
                return {"status": "error", "message": "Conflicto de horario con otra cita."}

            sets: List[str] = []
            params: List = []

            def _set(col, value):
                sets.append(f"{col} = %s"); params.append(value)

            if titulo is not None:          _set(E_AGENDA.TITULO.value, titulo)
            if notas is not None:           _set(E_AGENDA.NOTAS.value, notas)
            if trabajador_id is not None:   _set(E_AGENDA.TRABAJADOR_ID.value, trabajador_id)
            if cliente_nombre is not None:  _set(E_AGENDA.CLIENTE_NOM.value, cliente_nombre)
            if cliente_tel is not None:     _set(E_AGENDA.CLIENTE_TEL.value, cliente_tel)
            if inicio is not None:          _set(E_AGENDA.INICIO.value, inicio)
            if fin is not None:             _set(E_AGENDA.FIN.value, fin)
            if todo_dia is not None:        _set(E_AGENDA.TODO_DIA.value, 1 if todo_dia else 0)
            if color is not None:           _set(E_AGENDA.COLOR.value, color)
            if estado is not None:          _set(E_AGENDA.ESTADO.value, estado)
            if updated_by is not None:      _set(E_AGENDA.UPDATED_BY.value, updated_by)

            if not sets:
                return {"status": "success", "message": "Sin cambios."}

            params.append(cita_id)
            uq = f"UPDATE {E_AGENDA.TABLE.value} SET {', '.join(sets)} WHERE {E_AGENDA.ID.value} = %s"
            self.db.run_query(uq, tuple(params))
            return {"status": "success", "message": "Cita actualizada."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def cambiar_estado(self, cita_id: int, estado: str, *, updated_by: Optional[int] = None) -> Dict:
        return self.actualizar_cita(cita_id, estado=estado, updated_by=updated_by)

    def cancelar_cita(self, cita_id: int, *, updated_by: Optional[int] = None) -> Dict:
        return self.cambiar_estado(cita_id, E_AGENDA_ESTADO.CANCELADA.value, updated_by=updated_by)

    def completar_cita(self, cita_id: int, *, updated_by: Optional[int] = None) -> Dict:
        return self.cambiar_estado(cita_id, E_AGENDA_ESTADO.COMPLETADA.value, updated_by=updated_by)

    def eliminar_cita(self, cita_id: int) -> Dict:
        try:
            q = f"DELETE FROM {E_AGENDA.TABLE.value} WHERE {E_AGENDA.ID.value} = %s"
            self.db.run_query(q, (cita_id,))
            return {"status": "success", "message": "Cita eliminada."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}
