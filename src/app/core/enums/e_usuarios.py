from enum import Enum

class E_USUARIOS(Enum):
    TABLE = "usuarios_app"
    ID = "id_usuario"
    USERNAME = "username"
    PASSWORD = "password"
    ROL = "rol"                 # ver E_USU_ROL
    ESTADO_USR = "estado_usr"   # ver E_USER_ESTADO
    FECHA_CREACION = "fecha_creacion"

class E_USU_ROL(Enum):
    ROOT = "root"
    RECEPCIONISTA = "recepcionista"

class E_USER_ESTADO(Enum):
    ACTIVO = "activo"
    INACTIVO = "inactivo"
