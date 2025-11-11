# app/config/application/app_state.py
from __future__ import annotations
import flet as ft
from typing import Callable, Set, Dict, Any, Optional
from app.helpers.class_singleton import class_singleton
from app.ui.factory.palette_factory import PaletteFactory

THEME_STORAGE_KEY = "app.theme"      # "dark" | "light"
LEGACY_BOOL_KEY   = "dark_mode"      # compatibilidad con versiones anteriores


@class_singleton
class AppState:
    """
    Estado global de la app (único):
    - Guarda Page, dimensiones y modo responsive
    - Fuente de verdad del tema (dark/light) + listeners
    - Integra PaletteFactory para obtener colores (por área)
    - Sistema de listeners tolerante a firma: cb(is_dark: bool) o cb()
    """

    def __init__(self):
        # Page y layout
        self.page: Optional[ft.Page] = None
        self.data: Dict[str, Any] = {}
        self.window_width: int = 0
        self.window_height: int = 0
        self.responsive_mode: str = "desktop"

        # Tema
        self._dark: bool = False
        self._theme_mode: ft.ThemeMode = ft.ThemeMode.LIGHT
        self._theme_listeners: Set[Callable] = set()  # listeners unificados

        # Paletas
        self._palettes = PaletteFactory()

    # =========================================================
    # Page & dimensiones
    # =========================================================
    def set_page(self, page: ft.Page):
        """Registra la Page, ajusta dimensiones y aplica tema desde storage."""
        self.page = page
        if not page:
            return
        self.update_dimensions(page.window_width, page.window_height)
        self._init_theme_from_storage()
        self._apply_theme_to_page()
        # 🔔 Notificar para que cualquier control ya registrado pinte de inmediato
        self._notify_theme_change()

    def get_page(self) -> Optional[ft.Page]:
        return self.page

    def update_dimensions(self, width: int, height: int):
        self.window_width = width
        self.window_height = height
        if width < 600:
            self.responsive_mode = "mobile"
        elif width < 1024:
            self.responsive_mode = "tablet"
        else:
            self.responsive_mode = "desktop"

    def get_responsive_mode(self) -> str:
        return self.responsive_mode

    # =========================================================
    # KV store en memoria + client_storage
    # =========================================================
    def set(self, key: str, value: Any):
        self.data[key] = value

    def get(self, key: str, default: Any = None):
        return self.data.get(key, default)

    def set_client_value(self, key: str, value: Any):
        if value is None:
            self.clear_client_value(key)
            return

        self.data[key] = value
        if self.page:
            try:
                self.page.client_storage.set(key, value)
            except Exception:
                pass

    def get_client_value(self, key: str, default: Any = None):
        if key in self.data:
            val = self.data[key]
            return val if val is not None else default

        if self.page:
            try:
                v = self.page.client_storage.get(key)
                if v is not None:
                    self.data[key] = v
                    return v
            except Exception:
                return default

        return default

    def clear_client_value(self, key: str):
        self.data.pop(key, None)
        if self.page:
            try:
                self.page.client_storage.remove(key)
            except Exception:
                pass

    # =========================================================
    # Tema global (persistencia + notificación)
    # =========================================================
    def _init_theme_from_storage(self):
        """Lee 'app.theme' (o legacy 'dark_mode') y ajusta estado."""
        val = None
        try:
            if self.page:
                val = self.page.client_storage.get(THEME_STORAGE_KEY)
                # migración legacy: si no está 'app.theme', intenta 'dark_mode' (bool)
                if val is None:
                    legacy = self.page.client_storage.get(LEGACY_BOOL_KEY)
                    if isinstance(legacy, bool):
                        val = "dark" if legacy else "light"
        except Exception:
            val = None

        if isinstance(val, str):
            s = val.strip().lower()
            self._dark = (s == "dark")
        else:
            self._dark = False  # default

        self._theme_mode = ft.ThemeMode.DARK if self._dark else ft.ThemeMode.LIGHT

    def _apply_theme_to_page(self):
        """Pinta Page con modo + BG global de la paleta."""
        if not self.page:
            return
        try:
            self.page.theme_mode = self._theme_mode
            global_bg = self._palettes.get_colors(area=None, dark=self._dark).get("BG_COLOR")
            if global_bg:
                self.page.bgcolor = global_bg
            self.page.update()
        except Exception:
            pass

    def is_dark(self) -> bool:
        return self._dark

    def get_theme_mode(self) -> ft.ThemeMode:
        return self._theme_mode

    def set_dark(self, value: bool):
        """Fija dark/light, persiste, aplica a Page y notifica listeners."""
        new_dark = bool(value)
        if new_dark == self._dark and self.page:
            # Ya estamos en ese modo, garantiza visual
            self._apply_theme_to_page()
            return

        self._dark = new_dark
        self._theme_mode = ft.ThemeMode.DARK if self._dark else ft.ThemeMode.LIGHT

        # Persistencia única (clave nueva)
        try:
            if self.page:
                self.page.client_storage.set(THEME_STORAGE_KEY, "dark" if self._dark else "light")
        except Exception:
            pass

        # Aplicar y notificar
        self._apply_theme_to_page()
        self._notify_theme_change()

    def toggle_theme(self):
        """Alterna entre modo claro/oscuro y notifica a todos los listeners."""
        self.set_dark(not self._dark)

    # =========================================================
    # Listeners de tema (firma flexible)
    # =========================================================
    def on_theme_change(self, callback: Callable):
        """
        Registra un callback para cambios de tema.
        Soporta ambas firmas:
          - cb(is_dark: bool)
          - cb()
        Dispara inmediatamente una vez para pintar el estado actual.
        """
        if not callable(callback):
            return
        self._theme_listeners.add(callback)

        # 🔔 Disparo inmediato para pintar de una vez
        try:
            callback(self._dark)
        except TypeError:
            try:
                callback()
            except Exception:
                pass
        except Exception:
            pass

    def off_theme_change(self, callback: Callable):
        """Elimina cualquier listener registrado."""
        self._theme_listeners.discard(callback)

    def _notify_theme_change(self):
        """Notifica a todos los listeners tolerando cb(bool) o cb()."""
        for cb in list(self._theme_listeners):
            try:
                cb(self._dark)          # preferente: cb(bool)
            except TypeError:
                try:
                    cb()                 # fallback: cb()
                except Exception:
                    pass
            except Exception:
                pass

    # API pública por si algún módulo desea notificar manualmente
    def notify_theme_change(self):
        self._notify_theme_change()

    # =========================================================
    # Paletas (API de conveniencia)
    # =========================================================
    def get_colors(self, area: Optional[str] = None) -> Dict[str, str]:
        """Devuelve la mezcla GLOBAL + override del área actual."""
        return self._palettes.get_colors(area, dark=self._dark)

    def color(self, key: str, area: Optional[str] = None, default: Optional[str] = None):
        return self._palettes.color(key, area=area, dark=self._dark, default=default)
