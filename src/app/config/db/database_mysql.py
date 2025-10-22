# app/config/db/database_mysql.py
from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple, Union

import mysql.connector as mysql
from mysql.connector import Error, MySQLConnection

import flet as ft
from app.helpers.class_singleton import class_singleton
from app.config.db.config import DB_HOST, DB_USER, DB_PASSWORD, DB_DATABASE, DB_PORT
from app.views.notifications.messages import mostrar_mensaje

# ---- Mantenimiento (export/import/drop) ----
from app.config.db.db_maintenance import (
    DBMaintainer,
    IMPORT_MODE_STANDARD,
    IMPORT_MODE_SKIP,
    IMPORT_MODE_OVERWRITE,
)

# ---- Overrides opcionales desde config/env (no obligatorios) ----
try:
    from app.config.db.config import MYSQL_BIN_DIR, MYSQLDUMP_PATH, MYSQL_CLI_PATH
except Exception:
    MYSQL_BIN_DIR = ""
    MYSQLDUMP_PATH = ""
    MYSQL_CLI_PATH = ""

DictRow = dict
TupleRow = tuple
Params = Union[Tuple[Any, ...], List[Any]]


# ------------------------------------------------------------
# Descubrimiento de binarios (module-level helpers)
# ------------------------------------------------------------
def _program_files_dirs() -> List[Path]:
    """Posibles raíces de instalación en Windows."""
    dirs: List[Path] = []
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        v = os.environ.get(var)
        if v:
            p = Path(v)
            if p.exists():
                dirs.append(p)
    # Añadimos C:\ por si acaso (Laragon / XAMPP)
    try:
        c = Path("C:\\")
        if c.exists():
            dirs.append(c)
    except Exception:
        pass
    return dirs


def _known_windows_mysql_bins() -> List[Path]:
    """Rutas típicas en Windows para MySQL/MariaDB/XAMPP/WAMP/Laragon."""
    candidates: List[Path] = []

    # Overrides explícitos (máxima prioridad)
    for p in (MYSQL_BIN_DIR, os.getenv("MYSQL_BIN_DIR", "")):
        if p:
            bp = Path(p).resolve()
            if bp.exists():
                candidates.append(bp)

    for fp in (MYSQLDUMP_PATH, os.getenv("MYSQLDUMP_PATH", ""),
               MYSQL_CLI_PATH, os.getenv("MYSQL_CLI_PATH", "")):
        if fp:
            bp = Path(fp).resolve().parent
            if bp.exists():
                candidates.append(bp)

    # Program Files / XAMPP / WAMP / Laragon
    pf_dirs = _program_files_dirs()
    known_roots = [
        # MySQL oficiales
        "MySQL\\MySQL Server 8.0\\bin",
        "MySQL\\MySQL Server 5.7\\bin",
        # MariaDB
        "MariaDB 10.11\\bin",
        "MariaDB 10.6\\bin",
        "MariaDB 10.5\\bin",
        # XAMPP
        "xampp\\mysql\\bin",
        # WAMP (versiones varían; probamos directorio padre)
        "wamp64\\bin\\mysql",
        # Laragon (versiones varían)
        "laragon\\bin\\mysql",
    ]

    for root in pf_dirs:
        for suffix in known_roots:
            base = (root / suffix)
            if base.exists():
                # WAMP/Laragon tienen subcarpetas por versión; exploramos un nivel
                if base.name in ("mysql",):
                    try:
                        for child in base.iterdir():
                            if child.is_dir() and (child / "bin").exists():
                                candidates.append((child / "bin").resolve())
                    except Exception:
                        pass
                else:
                    candidates.append(base.resolve())

    # Rutas directas conocidas fuera de env vars, por si acaso
    extra_direct = [
        Path(r"C:\xampp\mysql\bin"),
        Path(r"C:\wamp64\bin\mysql\mysql8.0.31\bin"),
        Path(r"C:\wamp64\bin\mysql\mysql8.0.30\bin"),
        Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin"),
        Path(r"C:\Program Files\MariaDB 10.11\bin"),
        Path(r"C:\laragon\bin\mysql"),
    ]
    for ed in extra_direct:
        if ed.exists():
            # si es ...\mysql (Laragon), ampliar dentro
            if ed.name == "mysql":
                try:
                    for child in ed.iterdir():
                        if child.is_dir() and (child / "bin").exists():
                            candidates.append((child / "bin").resolve())
                except Exception:
                    pass
            else:
                candidates.append(ed.resolve())

    return candidates


def _known_unix_bins() -> List[Path]:
    """Rutas típicas en Linux/macOS."""
    paths = [
        Path("/usr/bin"),
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),  # macOS ARM (Homebrew)
        Path("/opt/local/bin"),     # MacPorts
        Path("/snap/bin"),
    ]
    return [p for p in paths if p.exists()]


def _tools_folder() -> Path:
    """Carpeta local 'tools/' junto a este archivo."""
    return (Path(__file__).parent / "tools").resolve()


def _candidatos_mysql() -> List[Path]:
    """Lista consolidada de carpetas a inspeccionar para encontrar binarios."""
    candidates: List[Path] = []

    # 1) Overrides desde config/env
    if MYSQL_BIN_DIR:
        p = Path(MYSQL_BIN_DIR).resolve()
        if p.exists():
            candidates.append(p)

    if MYSQLDUMP_PATH:
        p = Path(MYSQLDUMP_PATH).resolve().parent
        if p.exists():
            candidates.append(p)

    if MYSQL_CLI_PATH:
        p = Path(MYSQL_CLI_PATH).resolve().parent
        if p.exists():
            candidates.append(p)

    # 2) Rutas típicas según SO
    if os.name == "nt":
        candidates.extend(_known_windows_mysql_bins())
    else:
        candidates.extend(_known_unix_bins())

    # 3) Carpeta local tools/
    tf = _tools_folder()
    if tf.exists():
        candidates.append(tf)

    # 4) De-dupe preservando orden
    uniq: List[Path] = []
    seen = set()
    for c in candidates:
        try:
            rc = c.resolve()
        except Exception:
            continue
        key = str(rc).lower()
        if rc.exists() and key not in seen:
            uniq.append(rc)
            seen.add(key)

    return uniq


def _path_in_env(bin_dir: Path) -> bool:
    """Verifica si bin_dir ya está en PATH (case-insensitive en Windows)."""
    try:
        path_sep = ";" if os.name == "nt" else ":"
        current = os.environ.get("PATH", "")
        parts = [p.strip().lower() for p in current.split(path_sep) if p.strip()]
        return str(bin_dir).strip().lower() in parts
    except Exception:
        return False


@class_singleton
class DatabaseMysql:
    """
    Capa de acceso a datos MySQL robusta y reutilizable.

    ✔ API compatible:
        - run_query, get_data, get_data_list, execute_procedure, call_procedure,
          get_last_insert_id, is_empty, exportar_base_datos, importar_base_datos
        - Atributos: .database, .connection (MySQLConnection)

    ✨ Extras:
        - auto-reconexión (ensure_connection)
        - run_many, transaction()
        - limpia resultsets residuales
        - **Autodetección de 'mysqldump' y 'mysql'** con inyección a PATH
        - Integración con DBMaintainer
    """

    def __init__(self) -> None:
        # Config base
        self.host: str = DB_HOST
        self.port: int = int(DB_PORT)
        self.user: str = DB_USER
        self.password: str = DB_PASSWORD
        self.database: str = DB_DATABASE

        # Conexión
        self.connection: Optional[MySQLConnection] = None

        # Rutas resueltas de binarios
        self._mysqldump_path: Optional[str] = None
        self._mysql_cli_path: Optional[str] = None

        # Inicializa BD y conexión
        self._verificar_y_crear_base_datos()
        self.connect()

        # Resolver binarios e inyectarlos al PATH (para subprocess/DBMaintainer)
        self._ensure_mysql_bins_in_path()

        # Mantenimiento (export/import/drop)
        self.maintenance = DBMaintainer(self)

    # -------------------------
    # Conexión
    # -------------------------
    def connect(self) -> None:
        """Establece la conexión al servidor/BD."""
        try:
            self.connection = mysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                autocommit=False,
            )
            if self.connection and self.connection.is_connected():
                print("✅ Conexión exitosa a la base de datos")
        except Error as e:
            print(f"❌ Error al conectar: {e}")
            self.connection = None

    def disconnect(self) -> None:
        """Cierra la conexión actual (si existe)."""
        if self.connection:
            try:
                self.connection.close()
                print("ℹ️ Conexión cerrada a la base de datos")
            except Exception:
                pass
            finally:
                self.connection = None

    def ensure_connection(self) -> None:
        """Verifica la conexión y se reconecta si es necesario."""
        if self.connection is None:
            self.connect()
            return
        try:
            self.connection.ping(reconnect=True, attempts=3, delay=2)  # type: ignore[attr-defined]
        except Exception:
            try:
                if not self.connection.is_connected():
                    self.connection.reconnect(attempts=3, delay=2)
            except Exception:
                self.connect()

    def __del__(self) -> None:
        """Best-effort: cerrar conexión al destruir el objeto."""
        self.disconnect()

    # -------------------------
    # Utilidades de cursor
    # -------------------------
    @contextmanager
    def _cursor(self, dictionary: bool = False):
        self.ensure_connection()
        if not self.connection:
            raise RuntimeError("No hay conexión a la base de datos.")

        cursor = self.connection.cursor(dictionary=dictionary)
        try:
            yield cursor
            # Limpiar posibles resultsets residuales
            while True:
                try:
                    if not cursor.nextset():
                        break
                except Exception:
                    break
        finally:
            try:
                cursor.close()
            except Exception:
                pass

    # -------------------------
    # Creación de Base de Datos
    # -------------------------
    def _verificar_y_crear_base_datos(self) -> bool:
        """Crea la BD si no existe. Devuelve True si la creó."""
        created = False
        try:
            tmp = mysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                autocommit=True,
            )
            cur = tmp.cursor()
            cur.execute(
                "SELECT SCHEMA_NAME FROM information_schema.schemata WHERE schema_name = %s",
                (self.database,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    f"CREATE DATABASE `{self.database}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
                created = True
            cur.close()
            tmp.close()
        except Error as e:
            print(f"❌ Error al verificar/crear BD: {e}")
        return created

    # -------------------------
    # Escritura
    # -------------------------
    def run_query(self, query: str, params: Params = ()) -> None:
        self.ensure_connection()
        if not self.connection:
            raise RuntimeError("No hay conexión a la base de datos.")
        try:
            with self._cursor() as cursor:
                cursor.execute(query, params)
            self.connection.commit()
        except Error as e:
            try:
                self.connection.rollback()
            except Exception:
                pass
            print(f"❌ Error ejecutando query: {e}\nSQL: {query}\nParams: {params}")
            raise

    def run_many(self, query: str, seq_params: Iterable[Params]) -> int:
        self.ensure_connection()
        if not self.connection:
            raise RuntimeError("No hay conexión a la base de datos.")
        total = 0
        try:
            with self._cursor() as cursor:
                cursor.executemany(query, list(seq_params))
                total = cursor.rowcount if cursor.rowcount is not None else 0
            self.connection.commit()
            return total
        except Error as e:
            try:
                self.connection.rollback()
            except Exception:
                pass
            print(f"❌ Error en run_many: {e}\nSQL: {query}")
            raise

    @contextmanager
    def transaction(self):
        self.ensure_connection()
        if not self.connection:
            raise RuntimeError("No hay conexión a la base de datos.")

        cur = self.connection.cursor()
        try:
            yield cur
            while True:
                try:
                    if not cur.nextset():
                        break
                except Exception:
                    break
            self.connection.commit()
        except Exception as e:
            try:
                self.connection.rollback()
            except Exception:
                pass
            raise e
        finally:
            try:
                cur.close()
            except Exception:
                pass

    # -------------------------
    # Lectura
    # -------------------------
    def get_data(
        self, query: str, params: Params = (), dictionary: bool = False
    ) -> Union[DictRow, TupleRow, None]:
        try:
            with self._cursor(dictionary=dictionary) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return row if row is not None else ({} if dictionary else None)
        except Exception as e:
            print(f"❌ Error en get_data: {e}\nSQL: {query}\nParams: {params}")
            return {} if dictionary else ()

    def get_data_list(
        self, query: str, params: Params = (), dictionary: bool = False
    ) -> Union[List[DictRow], List[TupleRow]]:
        try:
            with self._cursor(dictionary=dictionary) as cursor:
                cursor.execute(query, params)
                result = cursor.fetchall()
                return result or []
        except Exception as e:
            print(f"❌ Error en get_data_list: {e}\nSQL: {query}\nParams: {params}")
            return []

    def fetch_scalar(self, query: str, params: Params = ()) -> Any:
        row = self.get_data(query, params, dictionary=False)
        if not row:
            return None
        try:
            return row[0]  # type: ignore[index]
        except Exception:
            return None

    # -------------------------
    # Stored procedures
    # -------------------------
    def execute_procedure(self, procedure_name: str, params: Params = ()) -> List[DictRow]:
        try:
            self.ensure_connection()
            if not self.connection:
                raise RuntimeError("No hay conexión a la base de datos.")
            cursor = self.connection.cursor(dictionary=True)
            try:
                cursor.callproc(procedure_name, params)
                results: List[DictRow] = []
                for result in cursor.stored_results():
                    results = result.fetchall()
                return results
            finally:
                cursor.close()
        except Exception as ex:
            print(f"❌ Error ejecutando SP '{procedure_name}': {ex}")
            return []

    def call_procedure(self, procedure_name: str, params: Params = ()) -> List[DictRow]:
        return self.execute_procedure(procedure_name, params)

    def get_last_insert_id(self) -> Optional[int]:
        try:
            row = self.get_data("SELECT LAST_INSERT_ID()", (), dictionary=False)
            if isinstance(row, tuple) and row:
                return int(row[0])  # type: ignore[arg-type]
            return None
        except Exception as e:
            print(f"❌ Error al obtener el último ID insertado: {e}")
            return None

    # -------------------------
    # Estado
    # -------------------------
    def is_empty(self) -> bool:
        tablas = [
            "empleados", "asistencias", "pagos",
            "prestamos", "desempeno", "reportes_semanales", "usuarios_app",
        ]
        for tbl in tablas:
            try:
                row = self.get_data(f"SELECT COUNT(*) AS c FROM `{tbl}`", (), dictionary=True)
                if row and isinstance(row, dict) and int(row.get("c", 0)) > 0:
                    return False
            except Exception:
                continue
        return True

    # -------------------------
    # Descubrimiento & PATH
    # -------------------------
    def _buscar_binario(self, nombre: str, _unused: Path | None = None) -> Optional[str]:
        """
        Busca un ejecutable en:
          1) PATH del sistema (shutil.which)
          2) Rutas candidatas conocidas (_candidatos_mysql)
          3) tools/ (incluida en candidatos)
        """
        # 1) PATH
        path = shutil.which(nombre)
        if path:
            return path

        # 2) Candidatos
        for base in _candidatos_mysql():
            p = base / nombre
            if p.exists():
                return str(p.resolve())
            # Windows: permitir sin .exe
            if os.name == "nt" and not nombre.lower().endswith(".exe"):
                p2 = base / (nombre + ".exe")
                if p2.exists():
                    return str(p2.resolve())
        return None

    def _ensure_mysql_bins_in_path(self) -> None:
        """
        Resuelve rutas a mysqldump/mysql y añade sus carpetas al PATH del proceso.
        """
        dump_name = "mysqldump.exe" if os.name == "nt" else "mysqldump"
        cli_name = "mysql.exe" if os.name == "nt" else "mysql"

        dump_path = self._buscar_binario(dump_name) or self._buscar_binario("mysqldump")
        cli_path = self._buscar_binario(cli_name) or self._buscar_binario("mysql")

        self._mysqldump_path = dump_path
        self._mysql_cli_path = cli_path

        if dump_path:
            dump_dir = Path(dump_path).resolve().parent
            if not _path_in_env(dump_dir):
                sep = ";" if os.name == "nt" else ":"
                os.environ["PATH"] = str(dump_dir) + sep + os.environ.get("PATH", "")
            print(f"[DB] mysqldump → {dump_path}")
        else:
            print("[DB] ⚠️ mysqldump no localizado en PATH ni rutas conocidas.")

        if cli_path:
            cli_dir = Path(cli_path).resolve().parent
            if not _path_in_env(cli_dir):
                sep = ";" if os.name == "nt" else ":"
                os.environ["PATH"] = str(cli_dir) + sep + os.environ.get("PATH", "")
            print(f"[DB] mysql cli → {cli_path}")
        else:
            print("[DB] ⚠️ mysql (cliente) no localizado en PATH ni rutas conocidas.")

        # Info final
        print(f"[DB] PATH actualizado para proceso (longitud {len(os.environ.get('PATH',''))}).")

    # -------------------------
    # Exportar / Importar (vía DBMaintainer)
    # -------------------------
    def exportar_base_datos(self, ruta_destino: str, insert_mode: str = "standard") -> bool:
        """
        insert_mode: "standard" | "skip_duplicates" | "overwrite"
        """
        # Intento de export con DBMaintainer (usa PATH ya actualizado)
        print(f"[DB] Export interno a: {ruta_destino}")
        res = self.maintenance.export_db(ruta_destino, insert_mode=insert_mode)
        if res.get("status") == "success":
            print(f"✅ Export OK → {res.get('path')}")
            return True
        print(f"❌ Export ERROR: {res.get('message') or res.get('stderr_tail') or 'desconocido'}")
        return False

    def importar_base_datos(
        self,
        ruta_sql: str,
        mode: str = "standard",
        recreate_schema: bool = False,
        page: Optional[ft.Page] = None,
    ) -> bool:
        """
        mode: "standard" | "skip_duplicates" | "overwrite"
        recreate_schema=True → DROP+CREATE antes de importar.
        """
        print(f"[DB] Import interno desde: {ruta_sql} (mode={mode}, recreate_schema={recreate_schema})")
        res = self.maintenance.import_db(ruta_sql, mode=mode, recreate_schema=recreate_schema)
        if res.get("status") == "success":
            print("✅ Import OK")
            if page:
                mostrar_mensaje(page, "Importación Exitosa", "Datos importados correctamente.")
            return True
        msg = res.get("message") or res.get("stderr_tail") or "desconocido"
        print(f"❌ Import ERROR: {msg}")
        if page:
            mostrar_mensaje(page, "Error de Importación", str(msg))
        return False

    def dropear_base_datos(self, bootstrap_cb=None) -> bool:
        """
        DROP DB + reconectar + re-crear schema vacío; luego puedes invocar bootstrap_cb.
        """
        print("[DB] Drop database solicitado...")
        res = self.maintenance.drop_database(force_reconnect=True, bootstrap_cb=bootstrap_cb)
        if res.get("status") == "success":
            print("🗑️ DB eliminada y reconectada.")
            return True
        print(f"❌ Drop ERROR: {res.get('message') or 'desconocido'}")
        return False

    # -------------------------
    # Lectura: aliases compat
    # -------------------------
    def get_all(
        self, query: str, params: Params = (), dictionary: bool = True
    ) -> List[DictRow] | List[TupleRow]:
        try:
            with self._cursor(dictionary=dictionary) as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return rows or []
        except Exception as e:
            print(f"❌ Error en get_all: {e}\nSQL: {query}\nParams: {params}")
            return []

    def get_one(
        self, query: str, params: Params = (), dictionary: bool = True
    ) -> DictRow | TupleRow | None:
        try:
            with self._cursor(dictionary=dictionary) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return row if row is not None else None
        except Exception as e:
            print(f"❌ Error en get_one: {e}\nSQL: {query}\nParams: {params}")
            return None

    def fetch_all(
        self, query: str, params: Params = (), dictionary: bool = True
    ) -> List[DictRow] | List[TupleRow]:
        return self.get_all(query, params, dictionary=dictionary)

    def fetch_one(
        self, query: str, params: Params = (), dictionary: bool = True
    ) -> DictRow | TupleRow | None:
        return self.get_one(query, params, dictionary=dictionary)

    def select(self, query: str, params: Params = ()) -> List[DictRow]:
        rows = self.get_all(query, params, dictionary=True)
        return rows if isinstance(rows, list) else []

    def query(self, query: str, params: Params = ()) -> List[DictRow]:
        return self.select(query, params)
