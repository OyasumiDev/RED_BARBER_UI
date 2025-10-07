# app/config/db/database_mysql.py
from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterable, List, Optional, Sequence, Tuple, Union

import mysql.connector as mysql
from mysql.connector import Error, MySQLConnection

import flet as ft
from app.helpers.class_singleton import class_singleton
from app.config.db.config import DB_HOST, DB_USER, DB_PASSWORD, DB_DATABASE, DB_PORT
from app.views.notifications.messages import mostrar_mensaje


DictRow = dict
TupleRow = tuple
Params = Union[Tuple[Any, ...], List[Any]]


@class_singleton
class DatabaseMysql:
    """
    Capa de acceso a datos MySQL robusta y reutilizable.

    ✔ Compatible con código existente:
        - run_query, get_data, get_data_list, execute_procedure, call_procedure,
        get_last_insert_id, is_empty, exportar_base_datos, importar_base_datos
        - Atributos: .database, .connection (objeto MySQLConnection)

    ✨ Extras:
        - auto-reconexión (ensure_connection)
        - fetch_scalar (obtener un solo valor)
        - run_many (ejecución masiva)
        - transaction() context manager (commit/rollback automático)
        - limpieza de resultados extra de SP/triggers (while cursor.nextset(): pass)
        - búsqueda de mysqldump/mysql en PATH o en tools/
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

        # Inicializa BD y conexión
        self._verificar_y_crear_base_datos()
        self.connect()

    # -------------------------
    # Conexión y mantenimiento
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
            # mysql.connector soporta ping()
            self.connection.ping(reconnect=True, attempts=3, delay=2)  # type: ignore[attr-defined]
        except Exception:
            try:
                # Fallback a reconnect()
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
        """
        Context manager para abrir/cerrar cursor de forma segura.
        Limpia conjuntos de resultados extra (SP/triggers).
        """
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
    # Operaciones de escritura
    # -------------------------
    def run_query(self, query: str, params: Params = ()) -> None:
        """
        Ejecuta un INSERT/UPDATE/DELETE/DDL. Hace commit si todo sale bien.
        Lanza la excepción para que el caller la maneje si lo desea.
        """
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
        """
        Ejecuta muchas veces la misma sentencia con diferentes parámetros.
        Devuelve el total de filas afectadas.
        """
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
        """
        Context manager de transacción:
            with db.transaction() as cur:
                cur.execute(...)
                cur.execute(...)
            # commit automático; rollback si hay excepción
        """
        self.ensure_connection()
        if not self.connection:
            raise RuntimeError("No hay conexión a la base de datos.")

        cur = self.connection.cursor()
        try:
            yield cur
            # limpiar resultsets residuales
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
    # Operaciones de lectura
    # -------------------------
    def get_data(
        self, query: str, params: Params = (), dictionary: bool = False
    ) -> Union[DictRow, TupleRow, None]:
        """
        Devuelve UNA fila (o None si no hay resultados).
        - dictionary=True -> dict
        - dictionary=False -> tuple
        Compatibilidad: si falla, retorna {} o () según dictionary.
        """
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
        """
        Devuelve TODAS las filas como lista (posiblemente vacía).
        Compatibilidad: en error, retorna [].
        """
        try:
            with self._cursor(dictionary=dictionary) as cursor:
                cursor.execute(query, params)
                result = cursor.fetchall()
                return result or []
        except Exception as e:
            print(f"❌ Error en get_data_list: {e}\nSQL: {query}\nParams: {params}")
            return []

    def fetch_scalar(self, query: str, params: Params = ()) -> Any:
        """
        Devuelve el primer valor de la primera fila (o None).
        Útil para COUNT(*), MAX(), etc.
        """
        row = self.get_data(query, params, dictionary=False)
        if not row:
            return None
        try:
            return row[0]  # type: ignore[index]
        except Exception:
            return None

    # -------------------------
    # Procedimientos almacenados
    # -------------------------
    def execute_procedure(self, procedure_name: str, params: Params = ()) -> List[DictRow]:
        """
        Llama un SP y devuelve la ÚLTIMA colección de resultados como lista de dicts.
        (Compatibilidad con tu uso actual.)
        """
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
        """
        Alias más corto (compatibilidad). Mismo comportamiento que execute_procedure().
        """
        return self.execute_procedure(procedure_name, params)

    def get_last_insert_id(self) -> Optional[int]:
        """Devuelve el último ID autoincrement insertado en la sesión/conexión."""
        try:
            row = self.get_data("SELECT LAST_INSERT_ID()", (), dictionary=False)
            if isinstance(row, tuple) and row:
                return int(row[0])  # type: ignore[arg-type]
            return None
        except Exception as e:
            print(f"❌ Error al obtener el último ID insertado: {e}")
            return None

    # -------------------------
    # Estado de la BD
    # -------------------------
    def is_empty(self) -> bool:
        """
        Heurística: considera que la BD está "vacía" si estas tablas no tienen filas.
        (Ignora excepciones por tablas inexistentes).
        """
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
    # Exportar / Importar
    # -------------------------
    def _buscar_binario(self, nombre: str, fallback_relativo: Path) -> Optional[str]:
        """
        Busca un ejecutable en PATH; si no, intenta en tools/ relativo a este archivo.
        """
        path = shutil.which(nombre)
        if path:
            return path
        local = (Path(__file__).parent / "tools" / fallback_relativo).resolve()
        return str(local) if local.exists() else None

    def exportar_base_datos(self, ruta_destino: str) -> bool:
        """
        Exporta la BD completa con mysqldump.
        - Busca 'mysqldump' en PATH o en tools/mysqldump(.exe).
        """
        try:
            # Compatibilidad Windows/Linux
            bin_name = "mysqldump.exe" if os.name == "nt" else "mysqldump"
            mysqldump = self._buscar_binario(bin_name, Path("mysqldump.exe"))
            if not mysqldump:
                raise FileNotFoundError("No se encontró mysqldump en PATH ni en tools/.")

            comando = [
                mysqldump,
                f"--user={self.user}",
                f"--password={self.password}",
                f"--host={self.host}",
                f"--port={self.port}",
                "--routines",
                "--events",
                "--triggers",
                self.database,
            ]

            with open(ruta_destino, "w", encoding="utf-8") as salida:
                subprocess.run(comando, stdout=salida, check=True)

            print(f"✅ Base de datos exportada a: {ruta_destino}")
            return True
        except Exception as e:
            print(f"❌ Error al exportar la base de datos: {e}")
            return False

    def importar_base_datos(self, ruta_sql: str, page: Optional[ft.Page] = None) -> bool:
        """
        Restaura la BD desde un .sql.
        - Recrea el schema.
        - Usa 'mysql' del PATH o tools/mysql(.exe).
        """
        try:
            ruta = Path(ruta_sql)
            if not ruta.exists():
                raise FileNotFoundError("Archivo SQL no encontrado")

            # Recrear esquema
            tmp = mysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                autocommit=True,
            )
            cur = tmp.cursor()
            cur.execute(f"DROP DATABASE IF EXISTS `{self.database}`")
            cur.execute(
                f"CREATE DATABASE `{self.database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.close()
            tmp.close()

            # Cliente mysql
            bin_name = "mysql.exe" if os.name == "nt" else "mysql"
            mysql_cli = self._buscar_binario(bin_name, Path("mysql.exe"))
            if not mysql_cli:
                raise FileNotFoundError("No se encontró mysql en PATH ni en tools/.")

            comando = [
                mysql_cli,
                f"-h{self.host}",
                f"-P{self.port}",
                f"-u{self.user}",
                f"-p{self.password}",
                self.database,
            ]

            with open(ruta, "r", encoding="utf-8") as f:
                resultado = subprocess.run(
                    comando,
                    stdin=f,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

            if resultado.returncode != 0:
                print("❌ Error durante la importación:")
                print(resultado.stderr)
                if page:
                    mostrar_mensaje(page, "Error de Importación", "Hubo un problema al importar la base de datos.")
                return False

            print("✅ Base de datos importada correctamente.")
            if page:
                mostrar_mensaje(page, "Importación Exitosa", "La base de datos fue importada correctamente.")
            return True

        except Exception as e:
            print(f"❌ Error al importar la base de datos: {e}")
            if page:
                mostrar_mensaje(page, "Error de Importación", str(e))
            return False
