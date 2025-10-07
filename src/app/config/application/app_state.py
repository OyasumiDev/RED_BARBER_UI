import json
import flet as ft
from typing import Callable, Set, Dict, Any, Optional
from app.helpers.class_singleton import class_singleton


_LIGHT_PALETTE = {
    "BG_COLOR": ft.colors.GREY_50,
    "BTN_BG": ft.colors.SURFACE_VARIANT,
    "FG_COLOR": ft.colors.BLACK,
    "DIVIDER_COLOR": ft.colors.OUTLINE_VARIANT,
    "AVATAR_ACCENT": ft.colors.PRIMARY,
}

_DARK_PALETTE = {
    "BG_COLOR": ft.colors.GREY_900,
    "BTN_BG": ft.colors.GREY_800,
    "FG_COLOR": ft.colors.WHITE,
    "DIVIDER_COLOR": ft.colors.OUTLINE,
    "AVATAR_ACCENT": ft.colors.PRIMARY,
}


@class_singleton
class AppState:
    """
    Estado global de la aplicación.
    - Guarda la Page, tamaños y modo responsive.
    - Administra tema global (light/dark/system) y paleta de colores.
    - Ofrece listeners para reaccionar a cambios de tema.
    """

    def __init__(self):
        # Page y dimensiones
        self.page: Optional[ft.Page] = None
        self.data: dict = {}
        self.window_width: int = 0
        self.window_height: int = 0
        self.responsive_mode: str = "desktop"  # desktop / tablet / mobile

        # ---- Tema global ----
        # Modo: ft.ThemeMode.LIGHT / DARK / SYSTEM
        self._theme_mode: ft.ThemeMode = ft.ThemeMode.LIGHT
        # Flag de atajo (persistimos como bool en client_storage: "dark"|"light")
        self._dark: bool = False
        # Paleta actual
        self._palette: Dict[str, Any] = dict(_LIGHT_PALETTE)
        # Suscriptores a cambios de tema
        self._theme_listeners: Set[Callable[[], None]] = set()

    # ---------------------------
    # Manejo de Page
    # ---------------------------
    def set_page(self, page: ft.Page):
        """
        Establece la instancia principal de la Page y actualiza dimensiones.
        También inicializa/recupera el tema global desde client_storage.
        """
        self.page = page
        if page:
            self.update_dimensions(page.window_width, page.window_height)
            self._init_theme_from_storage()
            self._apply_theme_to_page()

    def get_page(self) -> Optional[ft.Page]:
        return self.page

    # ---------------------------
    # Dimensiones y responsive
    # ---------------------------
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

    # ---------------------------
    # Almacenamiento de datos
    # ---------------------------
    def set(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

    # ---------------------------
    # Integración con client_storage
    # ---------------------------
    def set_client_value(self, key: str, value):
        self.set(key, value)
        if self.page:
            self.page.client_storage.set(key, value)

    def get_client_value(self, key: str, default=None):
        if self.page:
            value = self.page.client_storage.get(key)
            return value if value is not None else default
        return self.get(key, default)

    # ---------------------------
    # Tema global
    # ---------------------------
    def _init_theme_from_storage(self):
        """
        Lee el valor persistido de tema y lo aplica.
        Guarda 'app.theme' = 'dark' | 'light'
        """
        stored = None
        try:
            if self.page:
                stored = self.page.client_storage.get("app.theme")
        except Exception:
            stored = None

        if isinstance(stored, str):
            stored = stored.strip().lower()
            if stored == "dark":
                self._dark = True
                self._theme_mode = ft.ThemeMode.DARK
            elif stored == "light":
                self._dark = False
                self._theme_mode = ft.ThemeMode.LIGHT
            else:
                # por compatibilidad
                self._dark = False
                self._theme_mode = ft.ThemeMode.LIGHT
        else:
            # default si no hay storage
            self._dark = False
            self._theme_mode = ft.ThemeMode.LIGHT

        self._palette = dict(_DARK_PALETTE if self._dark else _LIGHT_PALETTE)

    def _apply_theme_to_page(self):
        """
        Aplica el tema al objeto Page (si existe) y hace update seguro.
        """
        if not self.page:
            return
        try:
            self.page.theme_mode = self._theme_mode
            # Puedes aplicar más ajustes globales aquí si lo deseas
            self.page.update()
        except AssertionError:
            # Page podría no estar aún agregada visualmente; ignoramos
            pass

    def is_dark(self) -> bool:
        return self._dark

    def get_theme_mode(self) -> ft.ThemeMode:
        return self._theme_mode

    def get_colors(self) -> Dict[str, Any]:
        """
        Devuelve la paleta actual. No modifiques este dict en sitio.
        """
        return dict(self._palette)

    def set_dark(self, value: bool):
        """
        Fija modo dark/light, persiste en client_storage y notifica listeners.
        """
        self._dark = bool(value)
        self._theme_mode = ft.ThemeMode.DARK if self._dark else ft.ThemeMode.LIGHT
        self._palette = dict(_DARK_PALETTE if self._dark else _LIGHT_PALETTE)
        # Persistir
        try:
            if self.page:
                self.page.client_storage.set("app.theme", "dark" if self._dark else "light")
        except Exception:
            pass
        # Aplicar al Page
        self._apply_theme_to_page()
        # Notificar
        self._notify_theme_change()

    def toggle_theme(self):
        self.set_dark(not self._dark)

    def on_theme_change(self, callback: Callable[[], None]):
        """
        Suscribe un callback sin argumentos que se llamará cuando cambie el tema.
        """
        self._theme_listeners.add(callback)

    def off_theme_change(self, callback: Callable[[], None]):
        self._theme_listeners.discard(callback)

    def _notify_theme_change(self):
        for cb in list(self._theme_listeners):
            try:
                cb()
            except Exception:
                pass
