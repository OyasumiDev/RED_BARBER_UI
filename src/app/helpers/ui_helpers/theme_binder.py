# app/helpers/ui_helpers/theme_binder.py
from __future__ import annotations
import flet as ft
from typing import Callable, Optional

from app.config.application.theme_controller import ThemeController
from app.config.application.app_state import AppState


class ThemeBinder:
    """
    Helper visual para vincular automáticamente contenedores o vistas al ThemeController.

    Permite:
    - Registrar una vista para que reaccione a cambios de tema (oscuro/claro).
    - Aplicar automáticamente la paleta correspondiente a su módulo.
    - Ejecutar una función personalizada al cambiar de tema (ej. refrescar colores de subcomponentes).

    Ejemplo:
        ThemeBinder().bind(container=self, module="navbar")
    """

    def __init__(self):
        self.app_state = AppState()
        self.theme_ctrl = ThemeController()
        self._ensure_subscription()

    # =========================================================
    # Suscripción automática a eventos del AppState
    # =========================================================
    def _ensure_subscription(self):
        """
        Registra este binder como listener global de cambio de tema en AppState.
        Se ejecuta una sola vez.
        """
        if not hasattr(self.app_state, "_theme_binder_initialized"):
            self.app_state._theme_binder_initialized = True

            def _notify_all(dark: bool):
                # Notifica a todos los binders registrados
                for cb in getattr(self.app_state, "_theme_binder_callbacks", []):
                    try:
                        cb(dark)
                    except Exception:
                        pass

            self.app_state.on_theme_change(_notify_all)

    # =========================================================
    # Vinculación de módulos
    # =========================================================
    def bind(
        self,
        container: ft.Control,
        module: str,
        on_update: Optional[Callable[[dict], None]] = None,
    ):
        """
        Vincula un contenedor a la paleta del módulo especificado.
        - container: instancia de ft.Container, ft.Column, ft.Row, etc.
        - module: nombre del módulo ("navbar", "home", "trabajadores", "inventario")
        - on_update: callback opcional que recibe la paleta y permite personalizar más colores.
        """

        paleta = self.theme_ctrl.get_paleta(module)
        self._apply_palette(container, paleta)
        if on_update:
            on_update(paleta)

        # Registra callback para futuras actualizaciones
        if not hasattr(self.app_state, "_theme_binder_callbacks"):
            self.app_state._theme_binder_callbacks = []

        def _update_callback(_is_dark: bool):
            paleta = self.theme_ctrl.get_paleta(module)
            self._apply_palette(container, paleta)
            if on_update:
                on_update(paleta)

        self.app_state._theme_binder_callbacks.append(_update_callback)

    # =========================================================
    # Aplicación de paleta
    # =========================================================
    def _apply_palette(self, ctrl: ft.Control, paleta: dict):
        """Aplica colores a un contenedor o layout base."""
        try:
            if hasattr(ctrl, "bgcolor") and "BG_COLOR" in paleta:
                ctrl.bgcolor = paleta["BG_COLOR"]
            if hasattr(ctrl, "color") and "FG_COLOR" in paleta:
                ctrl.color = paleta["FG_COLOR"]
            ctrl.update()
        except Exception:
            pass
