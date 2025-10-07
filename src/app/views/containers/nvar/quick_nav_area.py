# app/views/containers/nvar/quick_nav_area.py

from __future__ import annotations
import flet as ft
from typing import Callable, Optional


class QuickNavArea(ft.Column):
    """
    Acceso rápido de navegación (debajo del avatar).
    - Se adapta al estado 'expandido' de la barra lateral.
    - En expandido: icono + etiqueta.
    - En colapsado: solo icono con tooltip.
    - Por ahora incluye 'Empleados'. Puedes añadir más items siguiendo el mismo patrón.
    """

    def __init__(
        self,
        *,
        expanded: bool,
        bg: str,
        fg: str | None = None,
        on_employees: Optional[Callable] = None,
        mostrar_empleados: bool = True,
        spacing: int = 8,
        padding: int = 6,
    ):
        super().__init__(spacing=spacing)
        self.expanded = expanded
        self.bg = bg
        self.fg = fg or ft.colors.ON_SURFACE
        self.on_employees = on_employees
        self.mostrar_empleados = mostrar_empleados
        self._padding = padding

        self._build()

    # -----------------------
    # Internos
    # -----------------------
    def _quick_item(
        self,
        *,
        icon_src: str,
        label: str,
        tooltip: str,
        on_tap: Optional[Callable],
    ) -> ft.Control:
        """
        Un item de acceso rápido. Se renderiza distinto si la barra está expandida o colapsada.
        """
        icon_img = ft.Image(src=icon_src, width=24, height=24)
        if self.expanded:
            # Icono + texto
            content = ft.Container(
                bgcolor=self.bg,
                padding=self._padding,
                border_radius=6,
                content=ft.Row(
                    [icon_img, ft.Text(label, size=12, weight="bold", color=self.fg)],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.START,
                ),
            )
            return ft.GestureDetector(on_tap=on_tap, content=content)
        else:
            # Solo icono (con tooltip)
            content = ft.Container(
                bgcolor=self.bg,
                padding=self._padding,
                border_radius=6,
                content=icon_img,
                tooltip=tooltip,
            )
            return ft.GestureDetector(on_tap=on_tap, content=content)

    # -----------------------
    # Build
    # -----------------------
    def _build(self):
        items: list[ft.Control] = []

        if self.mostrar_empleados:
            items.append(
                self._quick_item(
                    icon_src="assets/buttons/employees-button.png",
                    label="Empleados",
                    tooltip="Empleados",
                    on_tap=self.on_employees,
                )
            )

        self.controls = items

    # -----------------------
    # API
    # -----------------------
    def update_state(self, *, expanded: Optional[bool] = None):
        if expanded is not None:
            self.expanded = expanded
        self._build()
        self.update()
