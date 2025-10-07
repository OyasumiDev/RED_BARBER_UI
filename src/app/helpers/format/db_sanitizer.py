# app/helpers/format/db_sanitizer.py

from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Union


class DBSanitizer:
    """
    Utilidad para sanear datos provenientes de la base de datos
    y hacerlos compatibles con JSON y almacenamiento en cliente.
    """

    @staticmethod
    def sanitize_value(value: Any) -> Any:
        """Convierte un valor a un tipo serializable."""
        if isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, (datetime, date)):
            return value.isoformat()
        elif isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8", errors="ignore")
        return value

    @staticmethod
    def sanitize_dict(data: Dict) -> Dict:
        """Sanitiza un diccionario completo."""
        return {k: DBSanitizer.sanitize_value(v) for k, v in data.items()}

    @staticmethod
    def sanitize_list(data: List[Dict]) -> List[Dict]:
        """Sanitiza una lista de diccionarios."""
        return [DBSanitizer.sanitize_dict(item) for item in data]

    @staticmethod
    def to_safe(data: Union[Dict, List, Any]) -> Union[Dict, List, Any]:
        """Método genérico: convierte dict, lista o valor único en formato seguro."""
        if isinstance(data, dict):
            return DBSanitizer.sanitize_dict(data)
        elif isinstance(data, list):
            return DBSanitizer.sanitize_list(data)
        else:
            return DBSanitizer.sanitize_value(data)
