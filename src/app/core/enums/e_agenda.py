from __future__ import annotations
from enum import Enum

class E_AGENDA(Enum):
    TABLE        = "agenda_citas"
    ID           = "id"
    EMPRESA_ID   = "empresa_id"
    TITULO       = "titulo"
    NOTAS        = "notas"
    TRABAJADOR_ID= "trabajador_id"
    CLIENTE_NOM  = "cliente_nombre"
    CLIENTE_TEL  = "cliente_tel"
    INICIO       = "fecha_inicio"
    FIN          = "fecha_fin"
    TODO_DIA     = "todo_dia"
    COLOR        = "color"
    ESTADO       = "estado"
    CREATED_BY   = "created_by"
    UPDATED_BY   = "updated_by"
    CREATED_AT   = "created_at"
    UPDATED_AT   = "updated_at"

class E_AGENDA_ESTADO(Enum):
    PROGRAMADA = "programada"
    CANCELADA  = "cancelada"
    COMPLETADA = "completada"