# app/views/containers/nvar/menu_buttons_area.py

from __future__ import annotations
from typing import Callable, List, Optional, Dict, Any
import flet as ft


class MenuButtonsArea(ft.Column):
    """
    Área de MENÚ (navegación de módulos).
    - En barra expandida: icono + etiqueta
    - En barra colapsada: solo icono con tooltip
    - SIN controles globales (expandir/tema/salir) → esos viven en ControlButtonsArea
    """

    def __init__(
        self,
        *,
        expanded: bool,
        dark: bool,
        # los siguientes se reciben por compatibilidad pero NO se usan aquí:
        on_toggle_nav=None,
        on_toggle_theme=None,
        on_exit=None,
        bg: str,
        fg: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
        spacing: int = 10,
        padding: int = 6,
    ):
        super().__init__(spacing=spacing)

        self.expanded = expanded
        self.dark = dark
        self.bg = bg
        self.fg = fg or ft.colors.ON_SURFACE
        self._padding = padding

        # items: [{ "icon_src": str, "label": str, "tooltip": str, "on_tap": callable }]
        self.items: List[Dict[str, Any]] = items or []

        self._build()

    # -----------------------
    # API para configurar menú
    # -----------------------
    def set_items(self, items: List[Dict[str, Any]]) -> None:
        self.items = items or []
        self._build()
        self.update()

    def add_item(self, *, icon_src: str, label: str, tooltip: str, on_tap: Callable) -> None:
        self.items.append({"icon_src": icon_src, "label": label, "tooltip": tooltip, "on_tap": on_tap})
        self._build()
        self.update()

    # -----------------------
    # Internos
    # -----------------------
    def _menu_item(
        self,
        *,
        icon_src: str,
        label: str,
        tooltip: str,
        on_tap: Optional[Callable],
    ) -> ft.Control:
        icon_img = ft.Image(src=icon_src, width=24, height=24)

        if self.expanded:
            content = ft.Container(
                bgcolor=self.bg,
                padding=self._padding,
                border_radius=6,
                content=ft.Row(
                    [icon_img, ft.Text(label, size=12, weight="bold", color=self.fg)],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.START,
                ),
                tooltip=tooltip,
            )
        else:
            content = ft.Container(
                bgcolor=self.bg,
                padding=self._padding,
                border_radius=6,
                content=icon_img,
                tooltip=tooltip,
            )

        return ft.GestureDetector(on_tap=on_tap, content=content)

    def _build(self) -> None:
        controls: List[ft.Control] = []

        for it in self.items:
            controls.append(
                self._menu_item(
                    icon_src=it.get("icon_src", ""),
                    label=it.get("label", ""),
                    tooltip=it.get("tooltip", it.get("label", "")),
                    on_tap=it.get("on_tap"),
                )
            )

        self.controls = controls

    # -----------------------
    # Estado dinámico
    # -----------------------
    def update_state(self, *, expanded: Optional[bool] = None, dark: Optional[bool] = None):
        if expanded is not None:
            self.expanded = expanded
        if dark is not None:
            self.dark = dark
        self._build()
        self.update()
