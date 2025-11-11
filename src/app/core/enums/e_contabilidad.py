# app/core/enums/e_contabilidad.py
from __future__ import annotations
from enum import Enum

class E_NOMINA_ESTADO(str, Enum):
    ABIERTA   = "abierta"
    PAGADA    = "pagada"
    CANCELADA = "cancelada"

class E_NOMINA(str, Enum):
    TABLE       = "nominas"
    ID          = "id"
    TRAB_ID     = "trabajador_id"
    INICIO      = "periodo_inicio"
    FIN         = "periodo_fin"
    CORTES_CNT  = "cortes_cnt"
    BRUTO_TOTAL = "bruto_total"
    EMP_TOT     = "empleados_total"   # total a pagar a empleados (suma comision_monto)
    EMPRESA_TOT = "empresa_total"     # parte de la empresa (suma sucursal_monto)
    ESTADO      = "estado"
    NOTAS       = "notas"
    CREATED_BY  = "created_by"
    UPDATED_BY  = "updated_by"
    CREATED_AT  = "created_at"
    UPDATED_AT  = "updated_at"

class E_NOMINA_ITEM(str, Enum):
    TABLE         = "nomina_items"
    ID            = "id"
    NOMINA_ID     = "nomina_id"
    CORTE_ID      = "corte_id"
    TOTAL         = "total"           # snapshot del precio_final del corte
    EMP_MONTO     = "comision_monto"  # snapshot de la comisión del trabajador
    EMPRESA_MONTO = "sucursal_monto"  # snapshot de la parte de empresa
