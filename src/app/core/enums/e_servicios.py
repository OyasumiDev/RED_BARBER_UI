from enum import Enum

class E_SERV(Enum):
    TABLE = "servicios"
    ID = "id_servicio"
    NOMBRE = "nombre"
    TIPO = "tipo"                 # 'corte_adulto', 'corte_nino', 'barba_trad', 'barba_expres', 'facial', 'ceja', 'linea', 'disenio'
    PRECIO = "precio_base"        # DECIMAL(10,2) NULL -> si monto_libre=1 puede quedar NULL
    MONTO_LIBRE = "monto_libre"   # TINYINT(1) NOT NULL DEFAULT 0
    ACTIVO = "activo"             # TINYINT(1) NOT NULL DEFAULT 1
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class E_SERV_TIPO(Enum):
    CORTE_ADULTO = "corte_adulto"
    CORTE_NINO = "corte_nino"
    BARBA_TRAD = "barba_trad"
    BARBA_EXPRES = "barba_expres"
    FACIAL = "facial"
    CEJA = "ceja"
    LINEA = "linea"
    DISENIO = "disenio"  # personalizados
