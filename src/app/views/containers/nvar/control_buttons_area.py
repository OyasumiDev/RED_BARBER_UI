# app/views/containers/nvar/control_buttons_area.py
from __future__ import annotations

import flet as ft
from typing import Optional, Callable

from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController
from app.views.containers.nvar.widgets.nav_button import NavButton


class ControlButtonsArea(ft.Column):
    """
    Controles anclados abajo:
      - Expandir/Contraer
      - Cambiar tema
      - Salir
    Usa NavButton para unificar formato con los botones de menú.
    """

    def __init__(
        self,
        theme_ctrl: ThemeController,
        on_toggle_theme: Callable,
        on_toggle_expand: Callable,
        on_logout: Callable,
        *,
        expanded: Optional[bool] = None,
        mostrar_theme: bool = True,
        spacing: int = 10,
    ):
        super().__init__(spacing=spacing, expand=False, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        self.theme = theme_ctrl
        self.app = AppState()
        self.page = self.app.get_page()
        self.pal = self.theme.get_colors("navbar")

        self.expanded = bool(expanded) if expanded is not None else False
        self.mostrar_theme = mostrar_theme

        # Callbacks provistos por el contenedor padre (NavBarContainer)
        self.on_toggle_theme = on_toggle_theme
        self.on_toggle_expand = on_toggle_expand
        self.on_logout = on_logout

        self._btn_expand: Optional[NavButton] = None
        self._btn_theme: Optional[NavButton] = None
        self._btn_exit: Optional[NavButton] = None

        # Recoloreo automático con cambios de tema
        self.app.on_theme_change(self._on_theme_change)

        self._build()

    # ---------------- icons dinámicos ----------------
    def _icon_theme(self) -> str:
        # Usa tus assets existentes
        return "assets/buttons/light-color-button.png" if self.theme.is_dark() else "assets/buttons/dark-color-button.png"

    def _icon_expand(self) -> str:
        return "assets/buttons/layout_close-button.png" if self.expanded else "assets/buttons/layout_open-button.png"

    # ---------------- UI ----------------
    def _build(self):
        self.controls.clear()

        # Expand / Collapse
        self._btn_expand = NavButton(
            icon_src=self._icon_expand(),
            label="Contraer" if self.expanded else "Expandir",
            tooltip="Contraer" if self.expanded else "Expandir",
            on_click=self.on_toggle_expand,  # ← handler directo
            pal=self.pal,
            expanded=self.expanded,
            selected=False,
            height=40,
            radius=8,
            padding=8,
            show_label_when_expanded=True,
        )
        self.controls.append(self._btn_expand)

        # Theme toggle
        if self.mostrar_theme:
            self._btn_theme = NavButton(
                icon_src=self._icon_theme(),
                label="Tema",
                tooltip="Cambiar tema",
                on_click=self.on_toggle_theme,  # ← handler directo
                pal=self.pal,
                expanded=self.expanded,
                selected=False,
                height=40,
                radius=8,
                padding=8,
                show_label_when_expanded=True,
            )
            self.controls.append(self._btn_theme)

        # Logout
        self._btn_exit = NavButton(
            icon_src="assets/buttons/exit-button.png",
            label="Salir",
            tooltip="Cerrar sesión",
            on_click=self.on_logout,  # ← handler directo
            pal=self.pal,
            expanded=self.expanded,
            selected=False,
            height=40,
            radius=8,
            padding=8,
            show_label_when_expanded=True,
        )
        self.controls.append(self._btn_exit)

    # ---------------- API pública ----------------
    def update_state(self, *, expanded: Optional[bool] = None):
        if expanded is not None:
            self.expanded = bool(expanded)

        if self._btn_expand:
            self._btn_expand.set_expanded(self.expanded)
            self._btn_expand.set_icon_src(self._icon_expand())
            self._btn_expand.set_label("Contraer" if self.expanded else "Expandir")
        if self._btn_theme:
            self._btn_theme.set_expanded(self.expanded)
        if self._btn_exit:
            self._btn_exit.set_expanded(self.expanded)

        self.update()

    # ---------------- Theme sync ----------------
    def _on_theme_change(self):
        self.pal = self.theme.get_colors("navbar")
        for b in (self._btn_expand, self._btn_theme, self._btn_exit):
            if b:
                b.set_palette(self.pal)
        if self._btn_theme:
            self._btn_theme.set_icon_src(self._icon_theme())
        self.update()

    def will_unmount(self):
        try:
            self.app.off_theme_change(self._on_theme_change)
        except Exception:
            pass
