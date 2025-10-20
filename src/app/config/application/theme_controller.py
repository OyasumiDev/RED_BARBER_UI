# app/config/application/theme_controller.py
from __future__ import annotations
import flet as ft
from typing import Optional, Dict, Callable, Set
from app.helpers.class_singleton import class_singleton
from app.config.application.app_state import AppState


@class_singleton
class ThemeController:
    """
    Orquestador de tema:
    - Lee/escribe el modo desde/hacia AppState (que persiste en client_storage).
    - Aplica Theme (Material 3) a Page usando la paleta global de PaletteFactory.
    - Expone helpers para colores por área y compatibilidad hacia atrás.
    - Pub/Sub fino para que las vistas se puedan suscribir a cambios de tema.
    """

    def __init__(self):
        self.app_state = AppState()
        self.page: ft.Page | None = None
        self._listeners: Set[Callable[[], None]] = set()  # listeners locales opcionales

    # =========================================================
    # Integración con Page
    # =========================================================
    def attach_page(self, page: ft.Page):
        """
        Conecta la Page principal. AppState.set_page() ya:
          - hidrata modo desde client_storage
          - pinta BG global inmediatamente
        Aquí solo guardamos ref y aplicamos Theme Material 3.
        """
        self.page = page
        self.app_state.set_page(page)
        self.apply_theme()

        # Reenviamos los cambios de AppState a los listeners locales
        self.app_state.on_theme_change(self._relay_theme_change)

    # =========================================================
    # Gestión del tema (siempre vía AppState)
    # =========================================================
    def toggle(self):
        """Alterna dark/light, persiste y notifica."""
        self.app_state.toggle_theme()
        self.apply_theme()

    def set_dark(self, value: bool):
        """Fuerza dark/light, persiste y notifica."""
        self.app_state.set_dark(bool(value))
        self.apply_theme()

    # =========================================================
    # Aplicación del Theme a la Page
    # =========================================================
    def apply_theme(self):
        """
        Aplica el Theme Material 3 a Page:
        - theme_mode desde AppState
        - color_scheme_seed desde PRIMARY/ACCENT de la paleta global
        - BG de la paleta global (ya lo pinta AppState, aquí lo reforzamos)
        """
        if not self.page:
            return

        # Modo (la fuente de verdad es AppState)
        self.page.theme_mode = self.app_state.get_theme_mode()

        # Paleta global (sin área)
        g = self.get_colors()  # ya viene de PaletteFactory vía AppState
        seed = g.get("PRIMARY") or g.get("ACCENT") or ft.colors.RED_400

        try:
            self.page.theme = ft.Theme(color_scheme_seed=seed, use_material3=True)
        except Exception:
            # Evita romper si Flet cambia firma. Continuamos con BG.
            pass

        try:
            self.page.bgcolor = g.get("BG_COLOR", ft.colors.WHITE)
            self.page.update()
        except Exception:
            pass

    # =========================================================
    # API de paletas / colores (delegadas a AppState/PaletteFactory)
    # =========================================================
    def get_colors(self, area: Optional[str] = None) -> Dict[str, str]:
        """Colores globales + override de área (si se indica)."""
        return self.app_state.get_colors(area)

    # Compat: “paletas”
    def get_paleta_global(self) -> Dict[str, str]:
        return self.get_colors(None)

    def get_paleta(self, modulo: str) -> Dict[str, str]:
        return self.get_colors(modulo)

    def color(self, key: str, area: Optional[str] = None, default: Optional[str] = None):
        return self.app_state.color(key, area=area, default=default)

    def get_fg_color(self) -> str:
        return self.color("FG_COLOR", default=ft.colors.BLACK)

    def is_dark(self) -> bool:
        return self.app_state.is_dark()

    def is_white(self) -> bool:
        return not self.is_dark()

    # =========================================================
    # Pub/Sub ligero (opcional)
    # =========================================================
    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """
        Permite a vistas suscribirse a cambios de tema.
        Devuelve el mismo callback para usarlo como “token”.
        """
        self._listeners.add(callback)
        return callback

    def unsubscribe(self, token: Callable[[], None]):
        self._listeners.discard(token)

    def _relay_theme_change(self):
        """Reenvía el evento de AppState a listeners locales y re-aplica Theme."""
        # Reaplicamos Theme por si cambia el seed o el BG base
        self.apply_theme()
        # Notificamos listeners
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass
