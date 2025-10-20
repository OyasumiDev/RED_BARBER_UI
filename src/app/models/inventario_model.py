from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.config.db.database_mysql import DatabaseMysql
from app.helpers.format.db_sanitizer import DBSanitizer
from app.core.enums.e_inventario import (
    E_INVENTARIO, E_INV_ESTADO, E_INV_CATEGORIA, E_INV_UNIDAD,
    E_INV_MOVS, E_INV_ALERTAS, E_INV_MOV
)


# ============== DTO para pasar alertas a la UI ==============
@dataclass
class AlertaInventario:
    id_alerta: int
    id_item: int
    nombre: str
    stock_actual: float
    stock_minimo: float
    fecha: datetime


# ========================= MODELO =========================
class InventarioModel:
    """
    Inventario para barbería con:
      - CRUD de productos (tabla: E_INVENTARIO.TABLE)
      - Movimientos (E_INV_MOVS.TABLE) con triggers que actualizan stock
      - Alertas (E_INV_ALERTAS.TABLE) cuando stock_actual <= stock_minimo
      - Callback on_low_stock para notificar en UI (Snackbar/Modal)

    ⚠️ Nota: MySQL no puede invocar Python desde un trigger.
    Patrón usado: el trigger inserta una alerta -> el modelo la lee y ejecuta tu callback.
    """

    def __init__(self, empresa_id: int = 1):
        self.db = DatabaseMysql()
        self.empresa_id = int(empresa_id)
        self.on_low_stock: Optional[Callable[[Dict[str, Any]], None]] = None
        # Bootstrap idempotente para trabajar con _safe_create del main
        self._ensure_schema()

    # ----------------- Esquema (DDL + índices + triggers) -----------------
    def _ensure_schema(self) -> None:
        self._create_tables()
        self._create_indexes()
        self._create_triggers()

    def _create_tables(self) -> None:
        t = E_INVENTARIO; m = E_INV_MOVS; a = E_INV_ALERTAS

        # inventario
        self.db.run_query(f"""
        CREATE TABLE IF NOT EXISTS {t.TABLE.value} (
            {t.ID.value} INT AUTO_INCREMENT PRIMARY KEY,
            {t.EMPRESA_ID.value} INT NOT NULL DEFAULT 1,
            {t.NOMBRE.value} VARCHAR(150) NOT NULL,
            {t.CATEGORIA.value} ENUM('{E_INV_CATEGORIA.INSUMO.value}','{E_INV_CATEGORIA.HERRAMIENTA.value}','{E_INV_CATEGORIA.PRODUCTO.value}') NOT NULL,
            {t.MARCA.value} VARCHAR(100) NULL,
            {t.UNIDAD.value} ENUM('{E_INV_UNIDAD.PIEZA.value}','{E_INV_UNIDAD.ML.value}','{E_INV_UNIDAD.GR.value}','{E_INV_UNIDAD.LT.value}','{E_INV_UNIDAD.KG.value}','{E_INV_UNIDAD.CAJA.value}','{E_INV_UNIDAD.PAQUETE.value}') NOT NULL DEFAULT '{E_INV_UNIDAD.PIEZA.value}',
            {t.STOCK_ACTUAL.value} DECIMAL(12,3) NOT NULL DEFAULT 0,
            {t.STOCK_MINIMO.value} DECIMAL(12,3) NOT NULL DEFAULT 0,
            {t.COSTO_UNITARIO.value} DECIMAL(12,2) NOT NULL DEFAULT 0,
            {t.PRECIO_UNITARIO.value} DECIMAL(12,2) NOT NULL DEFAULT 0,
            {t.ESTADO.value} ENUM('{E_INV_ESTADO.ACTIVO.value}','{E_INV_ESTADO.INACTIVO.value}') NOT NULL DEFAULT '{E_INV_ESTADO.ACTIVO.value}',
            {t.FECHA_ALTA.value} DATETIME DEFAULT CURRENT_TIMESTAMP,
            {t.FECHA_BAJA.value} DATETIME NULL,
            {t.FECHA_ACT.value} DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_inv_empresa_nombre ({t.EMPRESA_ID.value}, {t.NOMBRE.value})
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # movimientos
        self.db.run_query(f"""
        CREATE TABLE IF NOT EXISTS {m.TABLE.value} (
            {m.ID_MOV.value} INT AUTO_INCREMENT PRIMARY KEY,
            {m.ITEM_ID.value} INT NOT NULL,
            {m.TIPO.value} ENUM('{E_INV_MOV.ENTRADA.value}','{E_INV_MOV.SALIDA.value}','{E_INV_MOV.AJUSTE.value}') NOT NULL,
            {m.CANTIDAD.value} DECIMAL(12,3) NOT NULL,
            {m.MOTIVO.value} VARCHAR(200) NULL,
            {m.REFERENCIA.value} VARCHAR(100) NULL,
            {m.USUARIO.value} VARCHAR(50) NULL,
            {m.FECHA.value} DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_mov_item
              FOREIGN KEY ({m.ITEM_ID.value}) REFERENCES {t.TABLE.value}({t.ID.value})
              ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # alertas
        self.db.run_query(f"""
        CREATE TABLE IF NOT EXISTS {a.TABLE.value} (
            {a.ID_ALERTA.value} INT AUTO_INCREMENT PRIMARY KEY,
            {a.ITEM_ID.value} INT NOT NULL,
            {a.STOCK_ACTUAL.value} DECIMAL(12,3) NOT NULL,
            {a.STOCK_MINIMO.value} DECIMAL(12,3) NOT NULL,
            {a.RESUELTA.value} TINYINT(1) NOT NULL DEFAULT 0,
            {a.FECHA.value} DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_alerta_item
              FOREIGN KEY ({a.ITEM_ID.value}) REFERENCES {t.TABLE.value}({t.ID.value})
              ON DELETE CASCADE,
            UNIQUE KEY uk_alerta_abierta ({a.ITEM_ID.value}, {a.RESUELTA.value})
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

    def _create_index_if_missing(self, table: str, index_name: str, cols: str) -> None:
        r = self.db.get_data("""
            SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s LIMIT 1
        """, (table, index_name), dictionary=True)
        if not r:
            self.db.run_query(f"CREATE INDEX {index_name} ON {table} ({cols})")

    def _create_indexes(self) -> None:
        t = E_INVENTARIO; m = E_INV_MOVS; a = E_INV_ALERTAS
        self._create_index_if_missing(t.TABLE.value, "idx_inv_estado", t.ESTADO.value)
        self._create_index_if_missing(t.TABLE.value, "idx_inv_categoria", t.CATEGORIA.value)
        self._create_index_if_missing(t.TABLE.value, "idx_inv_nombre", t.NOMBRE.value)
        self._create_index_if_missing(m.TABLE.value, "idx_mov_item_fecha", f"{m.ITEM_ID.value}, {m.FECHA.value}")
        self._create_index_if_missing(a.TABLE.value, "idx_alerta_resuelta", a.RESUELTA.value)

    def _trigger_exists(self, name: str) -> bool:
        r = self.db.get_data(
            "SELECT 1 FROM INFORMATION_SCHEMA.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME=%s LIMIT 1",
            (name,), dictionary=True
        )
        return bool(r)

    def _drop_trigger_if_exists(self, name: str) -> None:
        try:
            self.db.run_query(f"DROP TRIGGER IF EXISTS {name}")
        except Exception:
            pass

    def _create_triggers(self) -> None:
        t = E_INVENTARIO; m = E_INV_MOVS; a = E_INV_ALERTAS

        # BEFORE INSERT: evitar stock negativo en SALIDA
        trg1 = "trg_inv_mov_prevent_negativo"
        if not self._trigger_exists(trg1):
            self.db.run_query(f"""
            CREATE TRIGGER {trg1}
            BEFORE INSERT ON {m.TABLE.value}
            FOR EACH ROW
            BEGIN
                DECLARE v_stock DECIMAL(12,3);

                IF NEW.{m.TIPO.value} = '{E_INV_MOV.SALIDA.value}' THEN
                    SELECT {t.STOCK_ACTUAL.value}
                      INTO v_stock
                      FROM {t.TABLE.value}
                     WHERE {t.ID.value} = NEW.{m.ITEM_ID.value}
                     FOR UPDATE;

                    IF v_stock < NEW.{m.CANTIDAD.value} THEN
                        SIGNAL SQLSTATE '45000'
                            SET MESSAGE_TEXT = 'Stock insuficiente para salida';
                    END IF;
                END IF;
            END;
            """)

        # AFTER INSERT: actualizar stock y crear alerta si queda bajo
        trg2 = "trg_inv_mov_actualizar_stock"
        if not self._trigger_exists(trg2):
            self.db.run_query(f"""
            CREATE TRIGGER {trg2}
            AFTER INSERT ON {m.TABLE.value}
            FOR EACH ROW
            BEGIN
                IF NEW.{m.TIPO.value} = '{E_INV_MOV.ENTRADA.value}' THEN
                    UPDATE {t.TABLE.value}
                       SET {t.STOCK_ACTUAL.value} = {t.STOCK_ACTUAL.value} + NEW.{m.CANTIDAD.value},
                           {t.FECHA_ACT.value} = NOW()
                     WHERE {t.ID.value} = NEW.{m.ITEM_ID.value};
                ELSEIF NEW.{m.TIPO.value} = '{E_INV_MOV.SALIDA.value}' THEN
                    UPDATE {t.TABLE.value}
                       SET {t.STOCK_ACTUAL.value} = {t.STOCK_ACTUAL.value} - NEW.{m.CANTIDAD.value},
                           {t.FECHA_ACT.value} = NOW()
                     WHERE {t.ID.value} = NEW.{m.ITEM_ID.value};
                ELSEIF NEW.{m.TIPO.value} = '{E_INV_MOV.AJUSTE.value}' THEN
                    UPDATE {t.TABLE.value}
                       SET {t.STOCK_ACTUAL.value} = NEW.{m.CANTIDAD.value},
                           {t.FECHA_ACT.value} = NOW()
                     WHERE {t.ID.value} = NEW.{m.ITEM_ID.value};
                END IF;

                -- Generar alerta si quedó <= mínimo (una sola abierta)
                INSERT INTO {a.TABLE.value} ({a.ITEM_ID.value}, {a.STOCK_ACTUAL.value}, {a.STOCK_MINIMO.value})
                SELECT i.{t.ID.value}, i.{t.STOCK_ACTUAL.value}, i.{t.STOCK_MINIMO.value}
                  FROM {t.TABLE.value} i
                 WHERE i.{t.ID.value} = NEW.{m.ITEM_ID.value}
                   AND i.{t.ESTADO.value} = '{E_INV_ESTADO.ACTIVO.value}'
                   AND i.{t.STOCK_ACTUAL.value} <= i.{t.STOCK_MINIMO.value}
                   AND NOT EXISTS (
                        SELECT 1 FROM {a.TABLE.value} x
                         WHERE x.{a.ITEM_ID.value} = i.{t.ID.value} AND x.{a.RESUELTA.value} = 0
                   );
            END;
            """)

        # AFTER UPDATE inventario: re-evaluar/limpiar alertas
        trg3 = "trg_inv_check_alerta_update"
        if not self._trigger_exists(trg3):
            self.db.run_query(f"""
            CREATE TRIGGER {trg3}
            AFTER UPDATE ON {t.TABLE.value}
            FOR EACH ROW
            BEGIN
                IF NEW.{t.ESTADO.value} = '{E_INV_ESTADO.ACTIVO.value}' AND NEW.{t.STOCK_ACTUAL.value} <= NEW.{t.STOCK_MINIMO.value} THEN
                    INSERT INTO {a.TABLE.value} ({a.ITEM_ID.value}, {a.STOCK_ACTUAL.value}, {a.STOCK_MINIMO.value})
                    SELECT NEW.{t.ID.value}, NEW.{t.STOCK_ACTUAL.value}, NEW.{t.STOCK_MINIMO.value}
                      FROM DUAL
                     WHERE NOT EXISTS (
                        SELECT 1 FROM {a.TABLE.value} x
                         WHERE x.{a.ITEM_ID.value} = NEW.{t.ID.value} AND x.{a.RESUELTA.value} = 0
                     );
                END IF;

                IF NEW.{t.STOCK_ACTUAL.value} > NEW.{t.STOCK_MINIMO.value} THEN
                    UPDATE {a.TABLE.value}
                       SET {a.RESUELTA.value} = 1
                     WHERE {a.ITEM_ID.value} = NEW.{t.ID.value}
                       AND {a.RESUELTA.value} = 0;
                END IF;
            END;
            """)

    # ----------------- Helpers internos -----------------
    def _safe(self, row: Optional[Dict]) -> Optional[Dict]:
        return DBSanitizer.to_safe(row) if row else None

    def _list_safe(self, rows: List[Dict]) -> List[Dict]:
        return [DBSanitizer.to_safe(r) for r in (rows or [])]

    def _valid(self, val: str, enum_cls) -> bool:
        return val in {e.value for e in enum_cls}

    def _table_exists(self, table_name: str) -> bool:
        try:
            q = """
            SELECT 1
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            LIMIT 1
            """
            row = self.db.get_data(q, (table_name,), dictionary=True)
            return row is not None
        except Exception:
            return False

    # ----------------- CRUD productos -----------------
    def crear_producto(self, nombre: str, categoria: str, *,
                       unidad: str = E_INV_UNIDAD.PIEZA.value,
                       marca: Optional[str] = None,
                       stock_minimo: float = 0.0,
                       costo_unitario: float = 0.0,
                       precio_unitario: float = 0.0,
                       estado: str = E_INV_ESTADO.ACTIVO.value) -> Dict[str, Any]:
        try:
            if not self._valid(categoria, E_INV_CATEGORIA): return {"status": "error", "message": "Categoría inválida."}
            if not self._valid(unidad, E_INV_UNIDAD):       return {"status": "error", "message": "Unidad inválida."}
            if not self._valid(estado, E_INV_ESTADO):       return {"status": "error", "message": "Estado inválido."}

            t = E_INVENTARIO
            self.db.run_query(f"""
                INSERT INTO {t.TABLE.value}
                    ({t.EMPRESA_ID.value},{t.NOMBRE.value},{t.CATEGORIA.value},{t.MARCA.value},
                     {t.UNIDAD.value},{t.STOCK_MINIMO.value},{t.COSTO_UNITARIO.value},{t.PRECIO_UNITARIO.value},{t.ESTADO.value})
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (self.empresa_id, nombre.strip(), categoria, (marca or None),
                  unidad, float(stock_minimo), float(costo_unitario), float(precio_unitario), estado))
            return {"status": "success", "message": "Producto creado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def actualizar_producto(self, item_id: int, *, nombre: Optional[str] = None,
                            categoria: Optional[str] = None, marca: Optional[str] = None,
                            unidad: Optional[str] = None, stock_minimo: Optional[float] = None,
                            costo_unitario: Optional[float] = None, precio_unitario: Optional[float] = None,
                            estado: Optional[str] = None, fecha_baja: Optional[datetime] = None) -> Dict[str, Any]:
        try:
            t = E_INVENTARIO
            sets, params = [], []
            if nombre is not None:  sets.append(f"{t.NOMBRE.value}=%s");         params.append(nombre.strip())
            if categoria is not None:
                if not self._valid(categoria, E_INV_CATEGORIA): return {"status": "error", "message": "Categoría inválida."}
                sets.append(f"{t.CATEGORIA.value}=%s");         params.append(categoria)
            if marca is not None:   sets.append(f"{t.MARCA.value}=%s");          params.append(marca or None)
            if unidad is not None:
                if not self._valid(unidad, E_INV_UNIDAD): return {"status": "error", "message": "Unidad inválida."}
                sets.append(f"{t.UNIDAD.value}=%s");            params.append(unidad)
            if stock_minimo is not None:
                sets.append(f"{t.STOCK_MINIMO.value}=%s");      params.append(float(stock_minimo))
            if costo_unitario is not None:
                sets.append(f"{t.COSTO_UNITARIO.value}=%s");    params.append(float(costo_unitario))
            if precio_unitario is not None:
                sets.append(f"{t.PRECIO_UNITARIO.value}=%s");   params.append(float(precio_unitario))
            if estado is not None:
                if not self._valid(estado, E_INV_ESTADO): return {"status": "error", "message": "Estado inválido."}
                sets.append(f"{t.ESTADO.value}=%s");            params.append(estado)
                if estado == E_INV_ESTADO.INACTIVO.value:
                    sets.append(f"{t.FECHA_BAJA.value}=CURRENT_TIMESTAMP")
                else:
                    sets.append(f"{t.FECHA_BAJA.value}=NULL")
            elif fecha_baja is not None:
                sets.append(f"{t.FECHA_BAJA.value}=%s");        params.append(fecha_baja)

            if not sets: return {"status": "success", "message": "Sin cambios."}

            params.append(item_id)
            self.db.run_query(
                f"UPDATE {t.TABLE.value} SET {', '.join(sets)} WHERE {t.ID.value}=%s",
                tuple(params)
            )
            return {"status": "success", "message": "Producto actualizado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def eliminar_producto(self, item_id: int) -> Dict[str, Any]:
        try:
            t = E_INVENTARIO
            self.db.run_query(f"DELETE FROM {t.TABLE.value} WHERE {t.ID.value}=%s", (item_id,))
            return {"status": "success", "message": "Producto eliminado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    # ----------------- Consultas -----------------
    def get_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        t = E_INVENTARIO
        r = self.db.get_data(f"SELECT * FROM {t.TABLE.value} WHERE {t.ID.value}=%s",
                             (item_id,), dictionary=True)
        return self._safe(r)

    def listar(self, *, estado: Optional[str] = None, categoria: Optional[str] = None,
               search: Optional[str] = None) -> List[Dict[str, Any]]:
        t = E_INVENTARIO
        conds, params = [f"{t.EMPRESA_ID.value}=%s"], [self.empresa_id]
        if estado and self._valid(estado, E_INV_ESTADO):
            conds.append(f"{t.ESTADO.value}=%s"); params.append(estado)
        if categoria and self._valid(categoria, E_INV_CATEGORIA):
            conds.append(f"{t.CATEGORIA.value}=%s"); params.append(categoria)
        if search:
            conds.append(f"{t.NOMBRE.value} LIKE %s"); params.append(f"%{search}%")

        rows = self.db.get_all(f"""
            SELECT * FROM {t.TABLE.value}
             WHERE {' AND '.join(conds)}
             ORDER BY {t.ESTADO.value} DESC, {t.NOMBRE.value} ASC
        """, tuple(params), dictionary=True) or []
        return self._list_safe(rows)

    def listar_bajo_stock(self) -> List[Dict[str, Any]]:
        t = E_INVENTARIO
        rows = self.db.get_all(f"""
            SELECT * FROM {t.TABLE.value}
            WHERE {t.EMPRESA_ID.value}=%s
              AND {t.ESTADO.value}='{E_INV_ESTADO.ACTIVO.value}'
              AND {t.STOCK_ACTUAL.value} <= {t.STOCK_MINIMO.value}
            ORDER BY {t.NOMBRE.value} ASC
        """, (self.empresa_id,), dictionary=True) or []
        return self._list_safe(rows)

    # ----------------- Movimientos (trigger actualiza stock) -----------------
    def _insert_mov(self, item_id: int, tipo: str, cantidad: float,
                    motivo: Optional[str], referencia: Optional[str], usuario: Optional[str]) -> None:
        m = E_INV_MOVS
        self.db.run_query(f"""
            INSERT INTO {m.TABLE.value}
              ({m.ITEM_ID.value}, {m.TIPO.value}, {m.CANTIDAD.value}, {m.MOTIVO.value}, {m.REFERENCIA.value}, {m.USUARIO.value})
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (item_id, tipo, float(cantidad), motivo, referencia, usuario))

    def ingresar_stock(self, item_id: int, cantidad: float, *, motivo: Optional[str] = None,
                       referencia: Optional[str] = None, usuario: Optional[str] = None) -> Dict[str, Any]:
        try:
            self._insert_mov(item_id, E_INV_MOV.ENTRADA.value, cantidad, motivo, referencia, usuario)
            self._post_mov_notificar()
            return {"status": "success", "message": "Entrada registrada."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def retirar_stock(self, item_id: int, cantidad: float, *, motivo: Optional[str] = None,
                      referencia: Optional[str] = None, usuario: Optional[str] = None) -> Dict[str, Any]:
        try:
            self._insert_mov(item_id, E_INV_MOV.SALIDA.value, cantidad, motivo, referencia, usuario)
            self._post_mov_notificar()
            return {"status": "success", "message": "Salida registrada."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def ajustar_stock(self, item_id: int, nuevo_stock: float, *, motivo: Optional[str] = None,
                      referencia: Optional[str] = None, usuario: Optional[str] = None) -> Dict[str, Any]:
        try:
            self._insert_mov(item_id, E_INV_MOV.AJUSTE.value, nuevo_stock, motivo, referencia, usuario)
            self._post_mov_notificar()
            return {"status": "success", "message": "Ajuste registrado."}
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    def obtener_movimientos(self, item_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        m = E_INV_MOVS
        rows = self.db.get_all(f"""
            SELECT * FROM {m.TABLE.value}
            WHERE {m.ITEM_ID.value}=%s
            ORDER BY {m.FECHA.value} DESC
            LIMIT %s
        """, (item_id, int(limit)), dictionary=True) or []
        return self._list_safe(rows)

    # ----------------- Alertas / Notificaciones -----------------
    def set_on_low_stock(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registra un callback para avisos de stock bajo."""
        self.on_low_stock = callback

    def procesar_alertas_pendientes(self) -> List[AlertaInventario]:
        t = E_INVENTARIO; a = E_INV_ALERTAS
        rows = self.db.get_all(f"""
            SELECT al.{a.ID_ALERTA.value} AS id_alerta,
                   al.{a.ITEM_ID.value} AS id_item,
                   inv.{t.NOMBRE.value} AS nombre,
                   al.{a.STOCK_ACTUAL.value} AS stock_actual,
                   al.{a.STOCK_MINIMO.value} AS stock_minimo,
                   al.{a.FECHA.value} AS fecha
              FROM {a.TABLE.value} al
              JOIN {t.TABLE.value} inv ON inv.{t.ID.value} = al.{a.ITEM_ID.value}
             WHERE al.{a.RESUELTA.value} = 0
             ORDER BY al.{a.FECHA.value} DESC
        """, (), dictionary=True) or []

        alertas: List[AlertaInventario] = []
        for r in rows:
            alerta = AlertaInventario(
                id_alerta=r["id_alerta"],
                id_item=r["id_item"],
                nombre=r["nombre"],
                stock_actual=float(r["stock_actual"]),
                stock_minimo=float(r["stock_minimo"]),
                fecha=r["fecha"],
            )
            alertas.append(alerta)
            if self.on_low_stock:
                try:
                    self.on_low_stock({
                        "id_alerta": alerta.id_alerta,
                        "id_item": alerta.id_item,
                        "nombre": alerta.nombre,
                        "stock_actual": alerta.stock_actual,
                        "stock_minimo": alerta.stock_minimo,
                        "fecha": alerta.fecha,
                        "message": f"⚠️ Stock bajo: {alerta.nombre} ({alerta.stock_actual} ≤ min {alerta.stock_minimo})"
                    })
                except Exception:
                    pass
        return alertas

    def resolver_alerta(self, id_alerta: int) -> None:
        a = E_INV_ALERTAS
        self.db.run_query(f"UPDATE {a.TABLE.value} SET {a.RESUELTA.value}=1 WHERE {a.ID_ALERTA.value}=%s", (id_alerta,))

    def _post_mov_notificar(self) -> None:
        """Después de un movimiento, lee y notifica alertas abiertas."""
        self.procesar_alertas_pendientes()

    # ----------------- Integración con bootstrap del main -----------------
    def migrate(self, *, force_recreate_triggers: bool = False) -> Dict[str, Any]:
        """
        Idempotente; asegura schema e índices. Si force_recreate_triggers=True,
        hace DROP + CREATE de los triggers.
        """
        if force_recreate_triggers:
            for name in ("trg_inv_mov_prevent_negativo", "trg_inv_mov_actualizar_stock", "trg_inv_check_alerta_update"):
                self._drop_trigger_if_exists(name)
        # re-asegura todo por si se hizo drop manual de algo
        self._ensure_schema()
        return self.healthcheck()

    def healthcheck(self) -> Dict[str, Any]:
        """Resumen para logs del bootstrap."""
        t = E_INVENTARIO; m = E_INV_MOVS; a = E_INV_ALERTAS
        tables = {
            t.TABLE.value: self._table_exists(t.TABLE.value),
            m.TABLE.value: self._table_exists(m.TABLE.value),
            a.TABLE.value: self._table_exists(a.TABLE.value),
        }
        triggers = {
            "trg_inv_mov_prevent_negativo": self._trigger_exists("trg_inv_mov_prevent_negativo"),
            "trg_inv_mov_actualizar_stock": self._trigger_exists("trg_inv_mov_actualizar_stock"),
            "trg_inv_check_alerta_update": self._trigger_exists("trg_inv_check_alerta_update"),
        }
        ok = all(tables.values()) and all(triggers.values())
        return {"tables": tables, "triggers": triggers, "ok": ok}


# ========================= USO RÁPIDO (ejemplo) =========================
if __name__ == "__main__":
    inv = InventarioModel(empresa_id=1)
    print(inv.healthcheck())
    inv.set_on_low_stock(lambda a: print(a["message"]))  # conecta tu Snackbar/Modal

    # Crear producto de ejemplo
    inv.crear_producto(
        nombre="Navajas Premium",
        categoria=E_INV_CATEGORIA.INSUMO.value,
        unidad=E_INV_UNIDAD.PIEZA.value,
        stock_minimo=10,
        costo_unitario=2.5,
        precio_unitario=5.0,
    )

    # Entradas / salidas
    inv.ingresar_stock(item_id=1, cantidad=5, motivo="Compra", usuario="root")
    inv.retirar_stock(item_id=1, cantidad=4, motivo="Servicio", usuario="barbero1")

    # Procesar alertas pendientes (también se llama tras cada movimiento)
    inv.procesar_alertas_pendientes()
