# app/models/trabajadores_model.py

from typing import Optional, Dict, List
from datetime import datetime
from app.config.db.database_mysql import DatabaseMysql
from app.core.enums.e_trabajadores import E_TRABAJADORES, E_TRAB_TIPO, E_TRAB_ESTADO
from app.helpers.format.db_sanitizer import DBSanitizer

TEL_DEFAULT = "0000000000"   # 10 dígitos
EMAIL_DEFAULT = "sinemail"


class TrabajadoresModel:
    """
    Gestión de trabajadores (barbería).
    - tipo: 'ocasional' | 'planta' | 'dueno'
    - estado: 'activo' | 'inactivo'
    - comision_porcentaje: DECIMAL(10,2) NOT NULL DEFAULT 0.00 (SIN TOPE)
    - telefono/email con defaults:
        telefono -> "0000000000" (10 dígitos)
        email    -> "sinemail"
    """

    def __init__(self):
        self.db = DatabaseMysql()
        self._exists_table = self.check_table()

    # ===================== DDL =====================
    def check_table(self) -> bool:
        """Crea la tabla si no existe y asegura índices (sin duplicados)."""
        try:
            # 1) Tabla
            create_table = f"""
            CREATE TABLE IF NOT EXISTS {E_TRABAJADORES.TABLE.value} (
                {E_TRABAJADORES.ID.value} INT AUTO_INCREMENT PRIMARY KEY,
                {E_TRABAJADORES.NOMBRE.value} VARCHAR(150) NOT NULL,
                {E_TRABAJADORES.TELEFONO.value} VARCHAR(10) NOT NULL DEFAULT '{TEL_DEFAULT}',
                {E_TRABAJADORES.EMAIL.value}   VARCHAR(120) NOT NULL DEFAULT '{EMAIL_DEFAULT}',
                {E_TRABAJADORES.TIPO.value}    ENUM('{E_TRAB_TIPO.OCASIONAL.value}','{E_TRAB_TIPO.PLANTA.value}','{E_TRAB_TIPO.DUENO.value}') NOT NULL,
                {E_TRABAJADORES.COMISION.value} DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                {E_TRABAJADORES.ESTADO.value}  ENUM('{E_TRAB_ESTADO.ACTIVO.value}','{E_TRAB_ESTADO.INACTIVO.value}') NOT NULL DEFAULT '{E_TRAB_ESTADO.ACTIVO.value}',
                {E_TRABAJADORES.FECHA_ALTA.value} DATETIME DEFAULT CURRENT_TIMESTAMP,
                {E_TRABAJADORES.FECHA_BAJA.value} DATETIME NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            self.db.run_query(create_table)

            # 2) Índices SOLO si faltan (evita "Duplicate key name ...")
            self._create_index_if_missing("idx_trab_tipo",   E_TRABAJADORES.TIPO.value)
            self._create_index_if_missing("idx_trab_estado", E_TRABAJADORES.ESTADO.value)
            self._create_index_if_missing("idx_trab_nombre", E_TRABAJADORES.NOMBRE.value)

            return True
        except Exception as ex:
            print(f"❌ Error creando tabla trabajadores: {ex}")
            return False

    def _create_index_if_missing(self, index_name: str, column: str) -> None:
        """
        Crea el índice si no existe, consultando INFORMATION_SCHEMA.STATISTICS.
        Evita que la capa DB loguee errores de 'Duplicate key name ...'.
        """
        try:
            exists_q = """
                SELECT 1
                FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND INDEX_NAME = %s
                LIMIT 1
            """
            row = self.db.get_data(
                exists_q,
                (E_TRABAJADORES.TABLE.value, index_name),
                dictionary=True
            )
            if not row:
                self.db.run_query(
                    f"CREATE INDEX {index_name} ON {E_TRABAJADORES.TABLE.value} ({column})"
                )
        except Exception:
            # no es crítico para correr la app
            pass

    # ===================== Helpers internos =====================
    def _safe(self, row: Optional[Dict]) -> Optional[Dict]:
        return DBSanitizer.to_safe(row) if row else None

    def _list_safe(self, rows: List[Dict]) -> List[Dict]:
        return [DBSanitizer.to_safe(r) for r in (rows or [])]

    def _sanitize_phone(self, tel: Optional[str]) -> str:
        if not tel:
            return TEL_DEFAULT
        digits = "".join(ch for ch in str(tel) if ch.isdigit())
        if len(digits) < 10:
            digits = (digits + ("0" * 10))[:10]
        else:
            digits = digits[:10]
        return digits or TEL_DEFAULT

    def _sanitize_email(self, email: Optional[str]) -> str:
        return (email or "").strip().lower() or EMAIL_DEFAULT

    def _validate_tipo(self, tipo: str) -> bool:
        return tipo in {e.value for e in E_TRAB_TIPO}

    def _validate_estado(self, estado: str) -> bool:
        return estado in {e.value for e in E_TRAB_ESTADO}

    # ===================== Consultas =====================
    def get_by_id(self, trabajador_id: int) -> Optional[Dict]:
        q = f"SELECT * FROM {E_TRABAJADORES.TABLE.value} WHERE {E_TRABAJADORES.ID.value} = %s"
        return self._safe(self.db.get_data(q, (trabajador_id,), dictionary=True))

    def get_by_nombre(self, nombre: str) -> List[Dict]:
        q = f"""
        SELECT * FROM {E_TRABAJADORES.TABLE.value}
        WHERE {E_TRABAJADORES.NOMBRE.value} LIKE %s
        ORDER BY {E_TRABAJADORES.NOMBRE.value} ASC
        """
        rows = self.db.get_all(q, (f"%{nombre}%",), dictionary=True) or []
        return self._list_safe(rows)

    def listar(
        self,
        tipo: Optional[str] = None,
        estado: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        conds, params = [], []
        if tipo and self._validate_tipo(tipo):
            conds.append(f"{E_TRABAJADORES.TIPO.value} = %s"); params.append(tipo)
        if estado and self._validate_estado(estado):
            conds.append(f"{E_TRABAJADORES.ESTADO.value} = %s"); params.append(estado)
        if search:
            conds.append(f"{E_TRABAJADORES.NOMBRE.value} LIKE %s"); params.append(f"%{search}%")
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        q = f"""
        SELECT * FROM {E_TRABAJADORES.TABLE.value}
        {where}
        ORDER BY {E_TRABAJADORES.FECHA_ALTA.value} DESC, {E_TRABAJADORES.NOMBRE.value} ASC
        """
        rows = self.db.get_all(q, tuple(params), dictionary=True) or []
        return self._list_safe(rows)

    # ===================== Mutaciones (CRUD) =====================
    def crear_trabajador(
        self,
        nombre: str,
        tipo: str,
        comision_porcentaje: float = 0.00,
        telefono: Optional[str] = None,
        email: Optional[str] = None,
        estado: str = E_TRAB_ESTADO.ACTIVO.value
    ) -> Dict:
        try:
            if not self._validate_tipo(tipo):
                return {"status": "error", "message": "Tipo inválido."}
            if not self._validate_estado(estado):
                return {"status": "error", "message": "Estado inválido."}

            tel = self._sanitize_phone(telefono)
            mail = self._sanitize_email(email)
            q = f"""
            INSERT INTO {E_TRABAJADORES.TABLE.value}
                ({E_TRABAJADORES.NOMBRE.value},
                 {E_TRABAJADORES.TELEFONO.value},
                 {E_TRABAJADORES.EMAIL.value},
                 {E_TRABAJADORES.TIPO.value},
                 {E_TRABAJADORES.COMISION.value},
                 {E_TRABAJADORES.ESTADO.value})
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            self.db.run_query(q, (nombre, tel, mail, tipo, float(comision_porcentaje), estado))
            return {"status": "success", "message": "Trabajador creado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def actualizar_trabajador(
        self,
        trabajador_id: int, *,
        nombre: Optional[str] = None,
        telefono: Optional[str] = None,
        email: Optional[str] = None,
        tipo: Optional[str] = None,
        comision_porcentaje: Optional[float] = None,
        estado: Optional[str] = None,
        fecha_baja: Optional[datetime] = None
    ) -> Dict:
        try:
            sets: List[str] = []
            params: List = []

            if nombre is not None:
                sets.append(f"{E_TRABAJADORES.NOMBRE.value} = %s"); params.append(nombre)

            if telefono is not None:
                sets.append(f"{E_TRABAJADORES.TELEFONO.value} = %s"); params.append(self._sanitize_phone(telefono))

            if email is not None:
                sets.append(f"{E_TRABAJADORES.EMAIL.value} = %s"); params.append(self._sanitize_email(email))

            if tipo is not None:
                if not self._validate_tipo(tipo):
                    return {"status": "error", "message": "Tipo inválido."}
                sets.append(f"{E_TRABAJADORES.TIPO.value} = %s"); params.append(tipo)

            if comision_porcentaje is not None:
                sets.append(f"{E_TRABAJADORES.COMISION.value} = %s"); params.append(float(comision_porcentaje))

            if estado is not None:
                if not self._validate_estado(estado):
                    return {"status": "error", "message": "Estado inválido."}
                sets.append(f"{E_TRABAJADORES.ESTADO.value} = %s"); params.append(estado)
                # manejar fecha_baja automáticamente
                if estado == E_TRAB_ESTADO.INACTIVO.value:
                    sets.append(f"{E_TRABAJADORES.FECHA_BAJA.value} = CURRENT_TIMESTAMP")
                elif estado == E_TRAB_ESTADO.ACTIVO.value:
                    sets.append(f"{E_TRABAJADORES.FECHA_BAJA.value} = NULL")
            elif fecha_baja is not None:
                sets.append(f"{E_TRABAJADORES.FECHA_BAJA.value} = %s"); params.append(fecha_baja)

            if not sets:
                return {"status": "success", "message": "Sin cambios."}

            params.append(trabajador_id)
            q = f"""
            UPDATE {E_TRABAJADORES.TABLE.value}
            SET {', '.join(sets)}
            WHERE {E_TRABAJADORES.ID.value} = %s
            """
            self.db.run_query(q, tuple(params))
            return {"status": "success", "message": "Trabajador actualizado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def cambiar_estado(self, trabajador_id: int, estado: str) -> Dict:
        """Atajo para activar/inactivar con control de fecha_baja."""
        if not self._validate_estado(estado):
            return {"status": "error", "message": "Estado inválido."}
        sets = [
            f"{E_TRABAJADORES.ESTADO.value} = %s",
            f"{E_TRABAJADORES.FECHA_BAJA.value} = " + ("CURRENT_TIMESTAMP" if estado == E_TRAB_ESTADO.INACTIVO.value else "NULL")
        ]
        q = f"UPDATE {E_TRABAJADORES.TABLE.value} SET {', '.join(sets)} WHERE {E_TRABAJADORES.ID.value} = %s"
        try:
            self.db.run_query(q, (estado, trabajador_id))
            msg = "Trabajador inactivado." if estado == E_TRAB_ESTADO.INACTIVO.value else "Trabajador reactivado."
            return {"status": "success", "message": msg}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def eliminar_trabajador(self, trabajador_id: int) -> Dict:
        """Eliminación dura (si prefieres soft-delete, usa cambiar_estado)."""
        try:
            q = f"DELETE FROM {E_TRABAJADORES.TABLE.value} WHERE {E_TRABAJADORES.ID.value} = %s"
            self.db.run_query(q, (trabajador_id,))
            return {"status": "success", "message": "Trabajador eliminado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}
