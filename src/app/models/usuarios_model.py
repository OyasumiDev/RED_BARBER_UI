from typing import Optional, Dict, List, Tuple
from app.config.db.database_mysql import DatabaseMysql
from app.core.enums.e_usuarios import E_USUARIOS, E_USU_ROL, E_USER_ESTADO
from app.helpers.format.db_sanitizer import DBSanitizer
from app.helpers.security.password_hasher import (
    hash_password, verify_password, rehash_if_needed
)


class UsuariosModel:
    """
    Usuarios de aplicación (login/autorización).
    Esquema: username, password(hash), rol, estado_usr, fecha_creacion.
    Incluye:
    - CRUD completo
    - Autenticación con verificación de hash + rehash/migración transparente
    - Salvaguardas para no desactivar/eliminar el último root activo
    - Mapa de 'capabilities' para habilitar/ocultar funciones en la UI
    """

    # ------- Capacidades por rol (la UI decide qué mostrar) -------
    _ROLE_CAPABILITIES = {
        E_USU_ROL.ROOT.value: {
            "agenda_ver": True, "agenda_editar": True,
            "ventas_cobrar": True, "ventas_cancelar": True,
            "inventario_ver": True, "inventario_mov": True,
            "compras_ver": True, "compras_editar": True,
            "reportes_full": True,
            "trabajadores_ver": True, "trabajadores_editar": True,
            "servicios_ver": True, "servicios_editar": True,
            "configuracion": True,
            "usuarios_admin": True,
        },
        E_USU_ROL.RECEPCIONISTA.value: {
            "agenda_ver": True, "agenda_editar": True,
            "ventas_cobrar": True, "ventas_cancelar": False,
            "inventario_ver": True, "inventario_mov": False,
            "compras_ver": False, "compras_editar": False,
            "reportes_full": False,
            "trabajadores_ver": False, "trabajadores_editar": False,
            "servicios_ver": True, "servicios_editar": False,
            "configuracion": False,
            "usuarios_admin": False,
        },
    }

    def __init__(self):
        self.db = DatabaseMysql()
        self._exists_table = self.check_table()
        if self._exists_table:
            self._seed_root_if_empty()

    # ===================== DDL =====================
    def check_table(self) -> bool:
        """Crea la tabla si no existe y crea índices solo si faltan (sin duplicar)."""
        try:
            q = f"""
            CREATE TABLE IF NOT EXISTS {E_USUARIOS.TABLE.value} (
                {E_USUARIOS.ID.value} INT AUTO_INCREMENT PRIMARY KEY,
                {E_USUARIOS.USERNAME.value} VARCHAR(50) UNIQUE NOT NULL,
                {E_USUARIOS.PASSWORD.value} VARCHAR(255) NOT NULL,
                {E_USUARIOS.ROL.value} ENUM('{E_USU_ROL.ROOT.value}','{E_USU_ROL.RECEPCIONISTA.value}') NOT NULL,
                {E_USUARIOS.ESTADO_USR.value} ENUM('{E_USER_ESTADO.ACTIVO.value}','{E_USER_ESTADO.INACTIVO.value}')
                    NOT NULL DEFAULT '{E_USER_ESTADO.ACTIVO.value}',
                {E_USUARIOS.FECHA_CREACION.value} DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            self.db.run_query(q)

            def _index_exists(table: str, key_name: str) -> bool:
                qi = f"SHOW INDEX FROM {table} WHERE Key_name=%s"
                row = self.db.get_data(qi, (key_name,), dictionary=True)
                return row is not None

            table = E_USUARIOS.TABLE.value
            if not _index_exists(table, "idx_usr_rol"):
                self.db.run_query(f"CREATE INDEX idx_usr_rol ON {table} ({E_USUARIOS.ROL.value})")
            if not _index_exists(table, "idx_usr_estado"):
                self.db.run_query(f"CREATE INDEX idx_usr_estado ON {table} ({E_USUARIOS.ESTADO_USR.value})")

            return True
        except Exception as ex:
            print(f"❌ Error creando tabla usuarios: {ex}")
            return False

    def _seed_root_if_empty(self) -> None:
        """Crea root/root (hasheado) si no hay usuarios."""
        try:
            res = self.db.get_data(
                f"SELECT COUNT(*) AS c FROM {E_USUARIOS.TABLE.value}", (), dictionary=True
            )
            if res and res.get("c", 0) == 0:
                pw_hash = hash_password("root")
                q = f"""
                INSERT INTO {E_USUARIOS.TABLE.value}
                    ({E_USUARIOS.USERNAME.value}, {E_USUARIOS.PASSWORD.value},
                    {E_USUARIOS.ROL.value}, {E_USUARIOS.ESTADO_USR.value})
                VALUES (%s, %s, %s, %s)
                """
                self.db.run_query(q, ("root", pw_hash, E_USU_ROL.ROOT.value, E_USER_ESTADO.ACTIVO.value))
        except Exception as ex:
            print(f"❌ Seed root: {ex}")

    # ===================== Helpers internos =====================
    def _safe(self, row: Optional[Dict]) -> Optional[Dict]:
        return DBSanitizer.to_safe(row) if row else None

    def _list_safe(self, rows: List[Dict]) -> List[Dict]:
        return [DBSanitizer.to_safe(r) for r in (rows or [])]

    def _username_existe(self, username: str, exclude_id: Optional[int] = None) -> bool:
        username_norm = (username or "").strip().lower()
        cond = ""
        params: Tuple = (username_norm,)
        if exclude_id is not None:
            cond = f" AND {E_USUARIOS.ID.value} <> %s"
            params = (username_norm, exclude_id)
        q = f"""
            SELECT COUNT(*) AS c
            FROM {E_USUARIOS.TABLE.value}
            WHERE LOWER(TRIM({E_USUARIOS.USERNAME.value})) = %s {cond}
        """
        row = self.db.get_data(q, params, dictionary=True)
        return int((row or {}).get("c", 0)) > 0


    def _conteo_root_activo(self) -> int:
        q = f"""
            SELECT COUNT(*) AS c
            FROM {E_USUARIOS.TABLE.value}
            WHERE {E_USUARIOS.ROL.value} = %s
            AND {E_USUARIOS.ESTADO_USR.value} = %s
        """
        row = self.db.get_data(q, (E_USU_ROL.ROOT.value, E_USER_ESTADO.ACTIVO.value), dictionary=True)
        return int((row or {}).get("c", 0))

    # ===================== Autenticación =====================
    def autenticar(self, username: str, password: str) -> Optional[Dict]:
        """
        Busca por username normalizado (trim+lower) y estado=activo,
        verifica hash y realiza rehash si es necesario.
        """
        try:
            username_norm = (username or "").strip().lower()
            q = f"""
            SELECT * FROM {E_USUARIOS.TABLE.value}
            WHERE LOWER(TRIM({E_USUARIOS.USERNAME.value})) = %s
            AND {E_USUARIOS.ESTADO_USR.value} = %s
            """
            row = self.db.get_data(q, (username_norm, E_USER_ESTADO.ACTIVO.value), dictionary=True)
            row = self._safe(row)
            if not row:
                return None

            stored = row.get(E_USUARIOS.PASSWORD.value, "")
            if not verify_password(password, stored):
                return None

            # Rehash/migración si hace falta
            new_hash = rehash_if_needed(password, stored)
            if new_hash:
                uq = f"""
                UPDATE {E_USUARIOS.TABLE.value}
                SET {E_USUARIOS.PASSWORD.value} = %s
                WHERE {E_USUARIOS.ID.value} = %s
                """
                self.db.run_query(uq, (new_hash, row[E_USUARIOS.ID.value]))
                row[E_USUARIOS.PASSWORD.value] = new_hash

            role = row.get(E_USUARIOS.ROL.value)
            row["capabilities"] = self._ROLE_CAPABILITIES.get(role, {})
            return row
        except Exception as ex:
            print(f"❌ Error autenticando: {ex}")
            return None

    # ===================== Consultas =====================
    def get_by_id(self, user_id: int) -> Optional[Dict]:
        q = f"SELECT * FROM {E_USUARIOS.TABLE.value} WHERE {E_USUARIOS.ID.value} = %s"
        return self._safe(self.db.get_data(q, (user_id,), dictionary=True))

    def get_by_username(self, username: str) -> Optional[Dict]:
        """
        Obtiene usuario por username normalizado.
        """
        username_norm = (username or "").strip().lower()
        q = f"""
            SELECT * FROM {E_USUARIOS.TABLE.value}
            WHERE LOWER(TRIM({E_USUARIOS.USERNAME.value})) = %s
            LIMIT 1
        """
        return self._safe(self.db.get_data(q, (username_norm,), dictionary=True))

    def listar(self, rol: Optional[str] = None, estado: Optional[str] = None) -> List[Dict]:
        conds, params = [], []
        if rol:
            conds.append(f"{E_USUARIOS.ROL.value} = %s")
            params.append(rol)
        if estado:
            conds.append(f"{E_USUARIOS.ESTADO_USR.value} = %s")
            params.append(estado)
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        q = f"""
        SELECT * FROM {E_USUARIOS.TABLE.value}
        {where}
        ORDER BY {E_USUARIOS.FECHA_CREACION.value} DESC
        """
        rows = self.db.get_all(q, tuple(params), dictionary=True) if hasattr(self.db, "get_all") else []
        return self._list_safe(rows)

    # ===================== Mutaciones (CRUD) =====================
    def crear_usuario(self, username: str, password: str,
                    rol: str = E_USU_ROL.RECEPCIONISTA.value,
                    estado: str = E_USER_ESTADO.ACTIVO.value) -> Dict:
        try:
            username_norm = (username or "").strip().lower()
            if not username_norm or len(username_norm) < 3:
                return {"status": "error", "message": "Username inválido (mín. 3 caracteres)."}
            if not password:
                return {"status": "error", "message": "La contraseña es obligatoria."}
            if self._username_existe(username_norm):
                return {"status": "error", "message": "El username ya existe."}

            if rol not in (E_USU_ROL.ROOT.value, E_USU_ROL.RECEPCIONISTA.value):
                return {"status": "error", "message": "Rol inválido."}
            if estado not in (E_USER_ESTADO.ACTIVO.value, E_USER_ESTADO.INACTIVO.value):
                return {"status": "error", "message": "Estado inválido."}

            pw_hash = hash_password(password)
            q = f"""
            INSERT INTO {E_USUARIOS.TABLE.value}
                ({E_USUARIOS.USERNAME.value}, {E_USUARIOS.PASSWORD.value},
                {E_USUARIOS.ROL.value}, {E_USUARIOS.ESTADO_USR.value})
            VALUES (%s, %s, %s, %s)
            """
            self.db.run_query(q, (username_norm, pw_hash, rol, estado))
            return {"status": "success", "message": "Usuario creado."}
        except Exception as ex:
            msg = str(ex)
            if "1062" in msg or "Duplicate entry" in msg:
                return {"status": "error", "message": "El username ya existe."}
            return {"status": "error", "message": msg}

    def actualizar_usuario(self, user_id: int, *,
                        username: Optional[str] = None,
                        password: Optional[str] = None,
                        rol: Optional[str] = None,
                        estado: Optional[str] = None) -> Dict:
        try:
            sets: List[str] = []
            params: List = []

            current = self.get_by_id(user_id)

            # Username (normalizado)
            if username is not None:
                username_norm = (username or "").strip().lower()
                if len(username_norm) < 3:
                    return {"status": "error", "message": "Username inválido (mín. 3 caracteres)."}
                if self._username_existe(username_norm, exclude_id=user_id):
                    return {"status": "error", "message": "El username ya existe."}
                sets.append(f"{E_USUARIOS.USERNAME.value} = %s"); params.append(username_norm)

            # Password (si viene None no cambia; si viene "" lo ignoramos)
            if password is not None:
                if password == "":
                    pass
                else:
                    pw_hash = hash_password(password)
                    sets.append(f"{E_USUARIOS.PASSWORD.value} = %s"); params.append(pw_hash)

            # Rol
            if rol is not None:
                if rol not in (E_USU_ROL.ROOT.value, E_USU_ROL.RECEPCIONISTA.value):
                    return {"status": "error", "message": "Rol inválido."}
                if current and current.get(E_USUARIOS.ROL.value) == E_USU_ROL.ROOT.value \
                and rol == E_USU_ROL.RECEPCIONISTA.value \
                and self._conteo_root_activo() <= 1:
                    return {"status": "error", "message": "No puedes quitar el rol root del único root activo."}
                sets.append(f"{E_USUARIOS.ROL.value} = %s"); params.append(rol)

            # Estado
            if estado is not None:
                if estado not in (E_USER_ESTADO.ACTIVO.value, E_USER_ESTADO.INACTIVO.value):
                    return {"status": "error", "message": "Estado inválido."}
                if current and current.get(E_USUARIOS.ROL.value) == E_USU_ROL.ROOT.value \
                and estado == E_USER_ESTADO.INACTIVO.value \
                and self._conteo_root_activo() <= 1:
                    return {"status": "error", "message": "No puedes desactivar el único usuario root."}
                sets.append(f"{E_USUARIOS.ESTADO_USR.value} = %s"); params.append(estado)

            if not sets:
                return {"status": "success", "message": "Sin cambios."}

            params.append(user_id)
            q = f"UPDATE {E_USUARIOS.TABLE.value} SET {', '.join(sets)} WHERE {E_USUARIOS.ID.value} = %s"
            self.db.run_query(q, tuple(params))
            return {"status": "success", "message": "Usuario actualizado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def actualizar_password(self, user_id: int, new_password: str) -> Dict:
        try:
            pw_hash = hash_password(new_password)
            q = f"UPDATE {E_USUARIOS.TABLE.value} SET {E_USUARIOS.PASSWORD.value} = %s WHERE {E_USUARIOS.ID.value} = %s"
            self.db.run_query(q, (pw_hash, user_id))
            return {"status": "success", "message": "Contraseña actualizada."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def cambiar_estado(self, user_id: int, estado: str) -> Dict:
        return self.actualizar_usuario(user_id, estado=estado)

    def eliminar_usuario(self, user_id: int) -> Dict:
        """Eliminación dura. Evita borrar el último root activo."""
        try:
            current = self.get_by_id(user_id)
            if current and current.get(E_USUARIOS.ROL.value) == E_USU_ROL.ROOT.value \
            and self._conteo_root_activo() <= 1:
                return {"status": "error", "message": "No puedes eliminar el único usuario root activo."}
            q = f"DELETE FROM {E_USUARIOS.TABLE.value} WHERE {E_USUARIOS.ID.value} = %s"
            self.db.run_query(q, (user_id,))
            return {"status": "success", "message": "Usuario eliminado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    # ===================== Autorización para la UI =====================
    @staticmethod
    def role_is_root(role: str) -> bool:
        return role == E_USU_ROL.ROOT.value

    @classmethod
    def capabilities_for_role(cls, role: str) -> Dict[str, bool]:
        return cls._ROLE_CAPABILITIES.get(role, {})

    @classmethod
    def has_capability(cls, role: str, capability: str) -> bool:
        return cls._ROLE_CAPABILITIES.get(role, {}).get(capability, False)
