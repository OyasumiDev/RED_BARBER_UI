from __future__ import annotations
from enum import Enum


class E_INVENTARIO(Enum):
    """Tabla principal de inventario (barbería)."""
    TABLE = "inventario"
    ID = "id_item"
    EMPRESA_ID = "id_empresa"
    NOMBRE = "nombre"
    CATEGORIA = "categoria"
    MARCA = "marca"
    UNIDAD = "unidad"
    STOCK_ACTUAL = "stock_actual"
    STOCK_MINIMO = "stock_minimo"
    COSTO_UNITARIO = "costo_unitario"
    PRECIO_UNITARIO = "precio_unitario"
    ESTADO = "estado"
    FECHA_ALTA = "fecha_alta"
    FECHA_BAJA = "fecha_baja"
    FECHA_ACT = "fecha_actualizacion"


class E_INV_ESTADO(Enum):
    ACTIVO = "activo"
    INACTIVO = "inactivo"


class E_INV_CATEGORIA(Enum):
    INSUMO = "insumo"           # navajas, gel, talco…
    HERRAMIENTA = "herramienta" # máquina, tijeras…
    PRODUCTO = "producto"       # venta al público


class E_INV_UNIDAD(Enum):
    PIEZA = "pieza"
    ML = "ml"
    GR = "gr"
    LT = "lt"
    KG = "kg"
    CAJA = "caja"
    PAQUETE = "paquete"


# --- Movimientos y Alertas (tablas relacionadas) ---

class E_INV_MOVS(Enum):
    """Tabla de movimientos de inventario."""
    TABLE = "inventario_movimientos"
    ID_MOV = "id_mov"
    ITEM_ID = E_INVENTARIO.ID.value
    TIPO = "tipo"       # entrada | salida | ajuste
    CANTIDAD = "cantidad"
    MOTIVO = "motivo"
    REFERENCIA = "referencia"
    USUARIO = "usuario"
    FECHA = "fecha"


class E_INV_ALERTAS(Enum):
    """Tabla de alertas por stock bajo."""
    TABLE = "inventario_alertas"
    ID_ALERTA = "id_alerta"
    ITEM_ID = E_INVENTARIO.ID.value
    STOCK_ACTUAL = "stock_actual"
    STOCK_MINIMO = "stock_minimo"
    RESUELTA = "resuelta"
    FECHA = "fecha"


class E_INV_MOV(Enum):
    ENTRADA = "entrada"
    SALIDA = "salida"
    AJUSTE = "ajuste"
