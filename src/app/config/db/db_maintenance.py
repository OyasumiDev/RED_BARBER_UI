# app/core/db_maintenance.py
from __future__ import annotations
import os, shutil, subprocess, time
from pathlib import Path
from typing import Optional, Dict, Iterable, Generator

import mysql.connector as mysql

# Tipos de modo para importación
IMPORT_MODE_STANDARD = "standard"          # Inserta tal cual
IMPORT_MODE_SKIP = "skip_duplicates"       # Reescribe a INSERT IGNORE
IMPORT_MODE_OVERWRITE = "overwrite"        # Reescribe a REPLACE

def _which(prog: str) -> Optional[str]:
    """Busca binario en PATH (cross-platform)."""
    path = shutil.which(prog)
    if path:
        return path
    # fallback local tools/ (opcional)
    local = Path(__file__).resolve().parent.parent / "config" / "db" / "tools" / prog
    if os.name == "nt" and not str(local).lower().endswith(".exe"):
        local = local.with_suffix(".exe")
    return str(local) if local.exists() else None

def _tail(b: bytes, n: int = 8000) -> str:
    if not b:
        return ""
    s = b[-n:]
    try:
        return s.decode("utf-8", "ignore")
    except Exception:
        return s.decode("latin-1", "ignore")

def _transform_insert_lines(lines: Iterable[str], mode: str) -> Generator[str, None, None]:
    """
    Reescribe solo líneas que INICIAN un INSERT de mysqldump.
    - skip_duplicates -> INSERT IGNORE INTO ...
    - overwrite       -> REPLACE INTO ...
    No toca líneas de continuación ni código en procedimientos.
    """
    if mode not in (IMPORT_MODE_SKIP, IMPORT_MODE_OVERWRITE):
        yield from lines
        return

    for line in lines:
        ls = line.lstrip()
        # mysqldump coloca los INSERT al inicio de línea (con o sin espacios previos)
        if ls.upper().startswith("INSERT INTO "):
            ws = line[: len(line) - len(ls)]
            if mode == IMPORT_MODE_SKIP:
                yield ws + ls.replace("INSERT INTO ", "INSERT IGNORE INTO ", 1)
            else:
                yield ws + ls.replace("INSERT INTO ", "REPLACE INTO ", 1)
        else:
            yield line


class DBMaintainer:
    """
    Mantenimiento de DB usando mysqldump / mysql, enlazado a DatabaseMysql.
    """
    def __init__(self, db):
        # 'db' es instancia de app.config.db.database_mysql.DatabaseMysql
        self.db = db

    # ---------- EXPORT ----------
    def export_db(self, dest_sql: str, insert_mode: str = "standard") -> Dict:
        """
        Exporta TODO el esquema + datos a un archivo .sql.
        insert_mode: "standard" | "skip_duplicates" | "overwrite"
          - skip_duplicates  => añade --insert-ignore al dump
          - overwrite        => añade --replace al dump
        """
        t0 = time.time()
        mysqldump = _which("mysqldump.exe" if os.name == "nt" else "mysqldump")
        if not mysqldump:
            return {"status": "error", "message": "mysqldump no encontrado en PATH ni en tools/"}

        args = [
            mysqldump,
            f"--host={self.db.host}",
            f"--port={self.db.port}",
            f"--user={self.db.user}",
            f"--password={self.db.password}",
            "--default-character-set=utf8mb4",
            "--single-transaction",
            "--quick",
            "--routines",
            "--events",
            "--triggers",
            "--hex-blob",
            "--set-gtid-purged=OFF",
            self.db.database,
        ]
        if insert_mode == IMPORT_MODE_SKIP:
            args.append("--insert-ignore")
        elif insert_mode == IMPORT_MODE_OVERWRITE:
            args.append("--replace")

        try:
            # Asegurar carpeta
            Path(dest_sql).parent.mkdir(parents=True, exist_ok=True)
            with open(dest_sql, "w", encoding="utf-8", newline="\n") as f:
                proc = subprocess.run(args, stdout=f, stderr=subprocess.PIPE)
            ok = (proc.returncode == 0)
            return {
                "status": "success" if ok else "error",
                "path": dest_sql,
                "elapsed_ms": int((time.time() - t0) * 1000),
                "stderr_tail": _tail(proc.stderr),
                "code": proc.returncode,
            }
        except Exception as ex:
            return {"status": "error", "message": f"export_db EXC: {ex}"}

    # ---------- IMPORT ----------
    def import_db(self, src_sql: str, mode: str = IMPORT_MODE_STANDARD, recreate_schema: bool = False) -> Dict:
        """
        Importa un .sql en la DB actual.
        mode:
          - "standard"          → inserta tal cual el dump
          - "skip_duplicates"   → transforma INSERT a INSERT IGNORE al vuelo
          - "overwrite"         → transforma INSERT a REPLACE al vuelo
        recreate_schema:
          - True  → DROP DATABASE y CREATE DATABASE antes de importar (full replace)
          - False → Importa sobre lo existente (útil con skip/overwrite)
        """
        t0 = time.time()
        mysql_cli = _which("mysql.exe" if os.name == "nt" else "mysql")
        if not mysql_cli:
            return {"status": "error", "message": "mysql client no encontrado en PATH ni en tools/"}

        # (Opcional) recrear schema completo antes de importar
        if recreate_schema:
            re = self._drop_and_create()
            if re.get("status") != "success":
                return {"status": "error", "message": f"No se pudo recrear schema: {re.get('message') or re.get('stderr_tail')}"}

        args = [
            mysql_cli,
            f"-h{self.db.host}",
            f"-P{self.db.port}",
            f"-u{self.db.user}",
            f"-p{self.db.password}",
            "--binary-mode",
            "--default-character-set=utf8mb4",
            "--init-command=SET FOREIGN_KEY_CHECKS=0",
            self.db.database,
        ]

        try:
            # Stream de archivo -> (posible) transform -> stdin de mysql
            with open(src_sql, "r", encoding="utf-8", errors="ignore") as f:
                src_iter = f  # Iterable[str]
                if mode in (IMPORT_MODE_SKIP, IMPORT_MODE_OVERWRITE):
                    src_iter = _transform_insert_lines(f, mode)

                # Abrimos mysql y escribimos por stdin sin cargar todo a RAM
                proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                for chunk in src_iter:
                    proc.stdin.write(chunk)  # type: ignore[arg-type]
                proc.stdin.close()  # type: ignore[union-attr]

                stdout, stderr = proc.communicate()
                ok = (proc.returncode == 0)
                return {
                    "status": "success" if ok else "error",
                    "elapsed_ms": int((time.time() - t0) * 1000),
                    "stdout_tail": _tail(stdout.encode("utf-8", "ignore") if stdout else b""),
                    "stderr_tail": _tail(stderr.encode("utf-8", "ignore") if stderr else b""),
                    "code": proc.returncode,
                }
        except Exception as ex:
            return {"status": "error", "message": f"import_db EXC: {ex}"}

    # ---------- DROP + reinit ----------
    def drop_database(self, force_reconnect: bool = True, bootstrap_cb = None) -> Dict:
        """
        DROP DATABASE actual y (opcional) reconectar + re-crear para que corra el bootstrap.
        Si pasas 'bootstrap_cb', se invoca después de reconectar (por ejemplo, tu rutina del main).
        """
        # Cerrar conexión actual para evitar 'Can't drop database; database in use'
        try:
            self.db.disconnect()
        except Exception:
            pass

        try:
            tmp = mysql.connect(
                host=self.db.host,
                port=self.db.port,
                user=self.db.user,
                password=self.db.password,
                autocommit=True,
            )
            cur = tmp.cursor()
            cur.execute(f"DROP DATABASE IF EXISTS `{self.db.database}`")
            cur.close()
            tmp.close()
        except Exception as ex:
            return {"status": "error", "message": f"DROP EXC: {ex}"}

        if force_reconnect:
            # Re-crear el schema y reconectar (esto activa tu bootstrap al volver a usar la DB)
            try:
                self._create_schema_empty()
                self.db.connect()
                # callback opcional (ej. bootstrapping de tablas/semillas)
                if callable(bootstrap_cb):
                    bootstrap_cb()
            except Exception as ex:
                return {"status": "error", "message": f"Reinit EXC: {ex}"}

        return {"status": "success"}

    # ---------- helpers internos ----------
    def _create_schema_empty(self) -> None:
        """Re-crea solo el schema vacío (utf8mb4), sin tablas; tu bootstrap las crea."""
        tmp = mysql.connect(
            host=self.db.host,
            port=self.db.port,
            user=self.db.user,
            password=self.db.password,
            autocommit=True,
        )
        cur = tmp.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{self.db.database}` "
            "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cur.close()
        tmp.close()

    def _drop_and_create(self) -> Dict:
        try:
            tmp = mysql.connect(
                host=self.db.host,
                port=self.db.port,
                user=self.db.user,
                password=self.db.password,
                autocommit=True,
            )
            cur = tmp.cursor()
            cur.execute(f"DROP DATABASE IF EXISTS `{self.db.database}`")
            cur.execute(
                f"CREATE DATABASE `{self.db.database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.close()
            tmp.close()
            return {"status": "success"}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}
