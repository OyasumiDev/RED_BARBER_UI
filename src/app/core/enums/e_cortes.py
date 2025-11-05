# app/core/enums/e_cortes.py
from enum import Enum

class E_CORTE(Enum):
    TABLE          = "cortes"
    ID             = "id"
    FECHA_HORA     = "fecha_hora"
    TIPO           = "tipo"              # agendado | libre
    TRABAJADOR_ID  = "trabajador_id"
    SERVICIO_ID    = "servicio_id"
    AGENDA_ID      = "agenda_id"
    PROMO_ID       = "promo_id"
    PRECIO_BASE    = "precio_base"
    DESCUENTO      = "descuento_aplicado"
    TOTAL          = "precio_final"
    COM_PCT        = "comision_pct_snapshot"
    COM_MONTO      = "comision_monto"
    SUC_MONTO      = "sucursal_monto"
    DESCRIPCION    = "descripcion"
    CREATED_BY     = "created_by"
    UPDATED_BY     = "updated_by"
    CREATED_AT     = "created_at"
    UPDATED_AT     = "updated_at"

class E_CORTE_TIPO(Enum):
    AGENDADO = "agendado"
    LIBRE    = "libre"
