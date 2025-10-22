# app/models/agenda_model.py
from __future__ import annotations
from typing import Optional, Dict, List, Tuple
from datetime import datetime, date, timedelta

from app.config.db.database_mysql import DatabaseMysql
from app.helpers.format.db_sanitizer import DBSanitizer
from app.core.enums.e_agenda import E_AGENDA, E_AGENDA_ESTADO
from app.core.enums.e_trabajadores import E_TRABAJADORES
from app.core.enums.e_servicios import E_SERV

TABLE = E_AGENDA.TABLE.value  # normalmente "agenda_citas"


class AgendaModel:
    """
    Agenda de citas con FKs a trabajadores y servicios.
    - Diseñada para trabajar con el container actual (usa titulo como nombre de servicio).
    - servicio_id/cantidad/precio_unit/total son opcionales (NULL) pero existen en esquema.
    """

    def __init__(self):
        self.db = DatabaseMysql()
        self._exists = self.check_table()

    # ========================== DDL ==========================
    def check_table(self) -> bool:
        """Crea tabla si falta y asegura columnas/índices/FKs (idempotente)."""
        try:
            # -- 1) Crear tabla base si no existe
            create_table = f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
              id INT AUTO_INCREMENT PRIMARY KEY,
              empresa_id INT NOT NULL DEFAULT 1,
              titulo VARCHAR(200) NULL,
              notas TEXT NULL,
              trabajador_id INT NULL,
              cliente_nombre VARCHAR(150) NULL,
              cliente_tel VARCHAR(20) NULL,
              fecha_inicio DATETIME NOT NULL,
              fecha_fin DATETIME NOT NULL,
              todo_dia TINYINT(1) NOT NULL DEFAULT 0,
              color VARCHAR(16) NULL,
              estado VARCHAR(24) NOT NULL DEFAULT '{E_AGENDA_ESTADO.PROGRAMADA.value}',
              -- Campos de detalle económico (opcionales)
              servicio_id INT NULL,
              cantidad INT NOT NULL DEFAULT 1,
              precio_unit DECIMAL(10,2) NULL,
              total DECIMAL(10,2) NULL,
              -- Auditoría
              created_by INT NULL,
              updated_by INT NULL,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            self.db.run_query(create_table)

            # -- 2) Asegurar columnas críticas (por si existía una versión previa)
            self._ensure_column("cliente_tel", "VARCHAR(20) NULL")
            self._ensure_column("servicio_id", "INT NULL")
            self._ensure_column("cantidad", "INT NOT NULL DEFAULT 1")
            self._ensure_column("precio_unit", "DECIMAL(10,2) NULL")
            self._ensure_column("total", "DECIMAL(10,2) NULL")
            self._ensure_column("created_by", "INT NULL")
            self._ensure_column("updated_by", "INT NULL")

            # -- 3) Índices (solo si faltan)
            self._ensure_index("idx_agenda_rango", "fecha_inicio, fecha_fin")
            self._ensure_index("idx_agenda_trab", "trabajador_id")
            self._ensure_index("idx_agenda_estado", "estado")
            self._ensure_index("idx_agenda_empresa", "empresa_id")
            self._ensure_index("idx_agenda_serv", "servicio_id")

            # -- 4) FKs (solo si faltan)
            # trabajador_id → trabajadores(id)
            self._ensure_fk(
                fk_name="fk_agenda_trabajador",
                column="trabajador_id",
                ref_table=E_TRABAJADORES.TABLE.value,
                ref_column=E_TRABAJADORES.ID.value,
                on_delete="SET NULL", on_update="CASCADE",
            )
            # servicio_id → servicios(id)
            self._ensure_fk(
                fk_name="fk_agenda_servicio",
                column="servicio_id",
                ref_table=E_SERV.TABLE.value,
                ref_column=E_SERV.ID.value,
                on_delete="SET NULL", on_update="CASCADE",
            )
            return True
        except Exception as ex:
            print(f"❌ agenda.check_table: {ex}")
            return False

    # ---------- helpers DDL idempotentes ----------
    def _column_exists(self, column: str) -> bool:
        try:
            q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            LIMIT 1
            """
            row = self.db.get_data(q, (TABLE, column), dictionary=True)
            return bool(row)
        except Exception:
            return False

    def _ensure_column(self, column: str, definition: str):
        try:
            if not self._column_exists(column):
                self.db.run_query(f"ALTER TABLE {TABLE} ADD COLUMN {column} {definition}")
        except Exception:
            # Evita romper el arranque por permisos o versiones antiguas.
            pass

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
            row = self.db.get_data(q, (TABLE, index_name), dictionary=True)
            return bool(row)
        except Exception:
            return False

    def _ensure_index(self, index_name: str, columns: str, *, unique: bool = False):
        try:
            if not self._index_exists(index_name):
                self.db.run_query(
                    f"CREATE {'UNIQUE ' if unique else ''}INDEX {index_name} ON {TABLE}({columns})"
                )
        except Exception:
            pass

    def _fk_exists(self, fk_name: str) -> bool:
        try:
            q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND CONSTRAINT_NAME = %s
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            LIMIT 1
            """
            row = self.db.get_data(q, (TABLE, fk_name), dictionary=True)
            return bool(row)
        except Exception:
            return False

    def _ensure_fk(
        self, *, fk_name: str, column: str,
        ref_table: str, ref_column: str,
        on_delete: str = "RESTRICT", on_update: str = "RESTRICT"
    ):
        try:
            if not self._fk_exists(fk_name):
                self.db.run_query(
                    f"ALTER TABLE {TABLE} "
                    f"ADD CONSTRAINT {fk_name} FOREIGN KEY ({column}) "
                    f"REFERENCES {ref_table}({ref_column}) "
                    f"ON DELETE {on_delete} ON UPDATE {on_update}"
                )
        except Exception:
            # En entornos sin permisos para ALTER, no fallamos.
            pass

    # ====================== Helpers ======================
    def _safe(self, row: Optional[Dict]) -> Optional[Dict]:
        return DBSanitizer.to_safe(row) if row else None

    def _list_safe(self, rows: List[Dict]) -> List[Dict]:
        return [DBSanitizer.to_safe(r) for r in (rows or [])]

    # ====================== Queries ======================
    def get_by_id(self, cita_id: int) -> Optional[Dict]:
        q = f"SELECT * FROM {TABLE} WHERE id=%s"
        return self._safe(self.db.get_data(q, (cita_id,), dictionary=True))

    def listar_por_rango(
        self,
        *, inicio: datetime, fin: datetime,
        estado: Optional[str] = None,
        empresa_id: int = 1
    ) -> List[Dict]:
        """
        Devuelve citas cuyo intervalo se solapa con [inicio, fin].
        Campos alias con nombres de E_AGENDA.* para el container.
        """
        conds = ["empresa_id = %s", "fecha_fin > %s", "fecha_inicio < %s"]
        params: List = [empresa_id, inicio, fin]
        if estado:
            conds.append("estado = %s"); params.append(estado)

        q = f"""
        SELECT
          id            AS {E_AGENDA.ID.value},
          empresa_id    AS {E_AGENDA.EMPRESA_ID.value},
          titulo        AS {E_AGENDA.TITULO.value},
          notas         AS {E_AGENDA.NOTAS.value},
          trabajador_id AS {E_AGENDA.TRABAJADOR_ID.value},
          cliente_nombre   AS {E_AGENDA.CLIENTE_NOM.value},
          cliente_tel   AS {E_AGENDA.CLIENTE_TEL.value},
          fecha_inicio  AS {E_AGENDA.INICIO.value},
          fecha_fin     AS {E_AGENDA.FIN.value},
          DATE(fecha_inicio)  AS fecha,
          TIME(fecha_inicio)  AS hora_inicio,
          TIME(fecha_fin)     AS hora_fin,
          todo_dia      AS {E_AGENDA.TODO_DIA.value},
          color         AS {E_AGENDA.COLOR.value},
          estado        AS {E_AGENDA.ESTADO.value},
          servicio_id   AS servicio_id,
          cantidad      AS cantidad,
          precio_unit   AS precio_unit,
          total         AS total
        FROM {TABLE}
        WHERE {" AND ".join(conds)}
        ORDER BY fecha_inicio ASC, fecha_fin ASC
        """
        rows = self.db.get_all(q, tuple(params), dictionary=True) or []
        return self._list_safe(rows)

    def listar_por_dia(
        self, *, dia: date,
        estado: Optional[str] = None,
        empresa_id: int = 1
    ) -> List[Dict]:
        inicio = datetime.combine(dia, datetime.min.time())
        fin = datetime.combine(dia, datetime.max.time())
        return self.listar_por_rango(inicio=inicio, fin=fin, estado=estado, empresa_id=empresa_id)

    # ====================== Mutaciones ======================
    def crear_cita(
        self,
        *,
        titulo: Optional[str],
        inicio: datetime,
        fin: datetime,
        todo_dia: bool = False,
        color: Optional[str] = None,
        notas: Optional[str] = None,
        trabajador_id: Optional[int] = None,
        cliente_nombre: Optional[str] = None,
        cliente_tel: Optional[str] = None,
        estado: str = E_AGENDA_ESTADO.PROGRAMADA.value,
        # Opcionales no usados aún por tu container (se guardan si los pasas)
        servicio_id: Optional[int] = None,
        cantidad: int = 1,
        precio_unit: Optional[float] = None,
        total: Optional[float] = None,
        empresa_id: int = 1,
        created_by: Optional[int] = None
    ) -> Dict:
        try:
            columns = [
                ("empresa_id", empresa_id),
                ("titulo", titulo),
                ("notas", notas),
                ("trabajador_id", trabajador_id),
                ("cliente_nombre", cliente_nombre),
                ("cliente_tel", cliente_tel),
                ("fecha_inicio", inicio),
                ("fecha_fin", fin),
                ("todo_dia", int(bool(todo_dia))),
                ("color", color),
                ("estado", estado),
                ("servicio_id", servicio_id),
                ("cantidad", int(cantidad or 1)),
                ("precio_unit", precio_unit),
                ("total", total),
            ]

            if self._column_exists("created_by"):
                columns.append(("created_by", created_by))
            if self._column_exists("updated_by"):
                # Mantén updated_by en sync con created_by si se pasa, sino NULL
                columns.append(("updated_by", created_by))

            cols_sql = ", ".join(col for col, _ in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            params = tuple(val for _, val in columns)

            q = f"INSERT INTO {TABLE} ({cols_sql}) VALUES ({placeholders})"
            self.db.run_query(q, params)
            return {"status": "success", "message": "Cita creada."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def actualizar_cita(
        self,
        *,
        cita_id: int,
        titulo: Optional[str],
        inicio: datetime,
        fin: datetime,
        todo_dia: bool = False,
        color: Optional[str] = None,
        notas: Optional[str] = None,
        trabajador_id: Optional[int] = None,
        cliente_nombre: Optional[str] = None,
        cliente_tel: Optional[str] = None,
        estado: str = E_AGENDA_ESTADO.PROGRAMADA.value,
        servicio_id: Optional[int] = None,
        cantidad: Optional[int] = None,
        precio_unit: Optional[float] = None,
        total: Optional[float] = None,
        updated_by: Optional[int] = None
    ) -> Dict:
        try:
            sets: List[str] = []
            params: List = []

            def _s(col, val):
                sets.append(f"{col}=%s"); params.append(val)

            _s("titulo", titulo)
            _s("fecha_inicio", inicio)
            _s("fecha_fin", fin)
            _s("todo_dia", int(bool(todo_dia)))
            _s("color", color)
            _s("notas", notas)
            _s("trabajador_id", trabajador_id)
            _s("cliente_nombre", cliente_nombre)
            _s("cliente_tel", cliente_tel)
            _s("estado", estado)

            # Campos opcionales económicos (solo si vienen)
            if servicio_id is not None: _s("servicio_id", servicio_id)
            if cantidad is not None:    _s("cantidad", int(cantidad or 1))
            if precio_unit is not None: _s("precio_unit", precio_unit)
            if total is not None:       _s("total", total)

            if updated_by is not None:  _s("updated_by", updated_by)

            params.append(cita_id)
            uq = f"UPDATE {TABLE} SET {', '.join(sets)} WHERE id=%s"
            self.db.run_query(uq, tuple(params))
            return {"status": "success", "message": "Cita actualizada."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def eliminar_cita(self, cita_id: int) -> Dict:
        try:
            self.db.run_query(f"DELETE FROM {TABLE} WHERE id=%s", (cita_id,))
            return {"status": "success", "message": "Cita eliminada."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    # ====================== Salud ======================
    def healthcheck(self) -> Dict:
        try:
            t_exists = self.db.get_data(
                "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s LIMIT 1",
                (TABLE,), dictionary=True
            ) is not None
            fks = [
                ("fk_agenda_trabajador", self._fk_exists("fk_agenda_trabajador")),
                ("fk_agenda_servicio", self._fk_exists("fk_agenda_servicio")),
            ]
            cols = ["cliente_tel", "servicio_id", "cantidad", "precio_unit", "total"]
            cols_ok = all(self._column_exists(c) for c in cols)
            return {"ok": t_exists and cols_ok and all(x for _, x in fks),
                    "table": t_exists, "columns": cols, "fks": fks}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}
