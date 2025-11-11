from __future__ import annotations
from enum import Enum

class E_PROMO_ESTADO(str, Enum):
    ACTIVA = "activa"
    INACTIVA = "inactiva"

class E_PROMO_TIPO(str, Enum):
    PORCENTAJE = "porcentaje"  # valor_descuento => 0..100
    MONTO = "monto"            # valor_descuento => dinero fijo

class E_PROMO(str, Enum):
    TABLE       = "promos"      # nombre de la tabla
    ID          = "id"
    NOMBRE      = "nombre"
    SERVICIO_ID = "servicio_id"
    TIPO_DESC   = "tipo_descuento"
    VALOR_DESC  = "valor_descuento"
    PRECIO_FINAL = "precio_final"
    ESTADO      = "estado"

    # Ventana de vigencia (opcional)
    FECHA_INI   = "fecha_inicio"
    FECHA_FIN   = "fecha_fin"

    # Días de la semana (checkbox por día)
    LUN         = "aplica_lunes"
    MAR         = "aplica_martes"
    MIE         = "aplica_miercoles"
    JUE         = "aplica_jueves"
    VIE         = "aplica_viernes"
    SAB         = "aplica_sabado"
    DOM         = "aplica_domingo"

    # Ventana horaria opcional (HH:MM–HH:MM)
    HORA_INI    = "hora_inicio"
    HORA_FIN    = "hora_fin"

    # Auditoría (opcionales)
    CREATED_BY  = "created_by"   # FK trabajadores.id
    UPDATED_BY  = "updated_by"   # FK trabajadores.id
    CREATED_AT  = "created_at"
    UPDATED_AT  = "updated_at"
