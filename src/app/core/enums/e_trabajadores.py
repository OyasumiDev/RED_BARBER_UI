from enum import Enum

class E_TRABAJADORES(Enum):
    TABLE = "trabajadores"

    ID = "id_trabajador"
    NOMBRE = "nombre"
    TELEFONO = "telefono"
    EMAIL = "email"

    TIPO = "tipo"                       # ver E_TRAB_TIPO
    COMISION = "comision_porcentaje"    # opcional; default 0.00
    ESTADO = "estado"                   # ver E_TRAB_ESTADO

    FECHA_ALTA = "fecha_alta"
    FECHA_BAJA = "fecha_baja"           # opcional; NULL si sigue activo


class E_TRAB_TIPO(Enum):
    OCASIONAL = "ocasional"
    PLANTA = "planta"
    DUENO = "dueno"   # sin tilde para SQL


class E_TRAB_ESTADO(Enum):
    ACTIVO = "activo"
    INACTIVO = "inactivo"
