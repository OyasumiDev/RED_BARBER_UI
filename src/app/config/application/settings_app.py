# app/config/settings_app.py
import json
import os
from pathlib import Path
from app.helpers.class_singleton import class_singleton



class SettingsApp:
    """
    Singleton para manejar configuraciones de la aplicación con persistencia JSON.
    Compatible con ThemeController (manejo de tema).
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsApp, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        # Ruta por defecto al archivo de settings
        self._file_path: Path = Path.home() / ".mi_app_settings.json"

        # Valores por defecto
        self._defaults = {
            "theme": "light",   # Usado por ThemeController
            "window": {
                "width": 800,
                "height": 600,
                "fullscreen": True
            },
            "last_view": "login"
        }

        # Cargar desde archivo si existe
        if self._file_path.exists():
            try:
                data = json.loads(self._file_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        else:
            data = {}

        # Mezcla con defaults sin perder valores anidados
        self._settings = self._merge_dicts(self._defaults, data)

        # Guardar para mantener consistencia en disco
        self._save()

    def _merge_dicts(self, defaults: dict, data: dict) -> dict:
        """
        Mezcla recursiva de defaults con data, 
        respetando claves anidadas.
        """
        merged = defaults.copy()
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = self._merge_dicts(merged[k], v)
            else:
                merged[k] = v
        return merged

    def get(self, key, default=None):
        """Obtener valor de configuración."""
        return self._settings.get(key, default)

    def set(self, key, value):
        """Asignar valor de configuración y persistir en disco."""
        self._settings[key] = value
        self._save()

    def _save(self):
        """Escribir settings al archivo JSON."""
        try:
            os.makedirs(self._file_path.parent, exist_ok=True)
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando settings: {e}")

    def all(self):
        """Devolver todo el diccionario de settings."""
        return self._settings.copy()
