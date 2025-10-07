# app/views/containers/nvar/navbar_container.py

import flet as ft
from app.views.containers.nvar.menu_buttons_area import MenuButtonsArea
from app.views.containers.nvar.user_icon_area import UserIconArea
from app.views.containers.nvar.layout_controller import LayoutController
from app.config.application.theme_controller import ThemeController
from app.views.containers.nvar.control_buttons_area import ControlButtonsArea
from app.views.containers.nvar.quick_nav_area import QuickNavArea
from app.config.application.app_state import AppState


class NavBarContainer(ft.Container):
    """
    Barra lateral:
      [UserIconArea]
      [QuickNavArea   ← Empleados aquí]
      [Divider]
      [MenuButtonsArea]
      ----------------------------
      [ControlButtonsArea ← abajo]
    """
    def __init__(self, is_root: bool = False):
        super().__init__(padding=10, expand=True)

        self.is_root = is_root
        self.layout_ctrl = LayoutController()
        self.theme_ctrl = ThemeController()

        self.expanded = self.layout_ctrl.is_expanded()
        self.dark = self.theme_ctrl.is_dark()

        self._build()

    # --------------------
    # Build
    # --------------------
    def _build(self):
        colors = self.theme_ctrl.get_colors()

        # Ancho / fondo
        self.width = 220 if self.expanded else 80
        self.bgcolor = colors["BG_COLOR"]

        # Arriba: avatar/usuario
        user_area = UserIconArea(
            is_root=self.is_root,
            accent=colors["AVATAR_ACCENT"],
            nav_width=self.width,
            expanded=self.expanded,
        )

        # Debajo del avatar: acceso rápido (Empleados)
        quick_area = QuickNavArea(
            expanded=self.expanded,
            bg=colors["BTN_BG"],
            fg=colors.get("FG_COLOR", ft.colors.BLACK),
            on_employees=lambda e: self._go_empleados(),   # ← acepta el evento
            mostrar_empleados=True,
        )

        # Menú principal (sólo navegación de módulos; SIN controles globales)
        menu_area = MenuButtonsArea(
            expanded=self.expanded,
            dark=self.dark,
            on_toggle_nav=None,     # ignorado por MenuButtonsArea (compatibilidad)
            on_toggle_theme=None,   # ignorado por MenuButtonsArea (compatibilidad)
            on_exit=None,           # ignorado por MenuButtonsArea (compatibilidad)
            bg=colors["BTN_BG"],
        )
        # Si quieres, puedes inyectar entradas así:
        # menu_area.set_items([
        #     {
        #         "icon_src": "assets/buttons/database-button.png",
        #         "label": "Inicio",
        #         "tooltip": "Inicio",
        #         "on_tap": lambda e: AppState().page.go("/home"),
        #     },
        # ])

        # Top stack (se expande para empujar los controles abajo)
        top_stack = ft.Column(
            controls=[
                user_area,
                quick_area,
                ft.Divider(color=colors["DIVIDER_COLOR"]),
                menu_area,
            ],
            spacing=8,
            expand=True,
        )

        # Controles globales (abajo): Expandir / Tema / Salir
        control_area = ControlButtonsArea(
            expanded=self.expanded,
            dark=self.dark,
            on_toggle_nav=self.toggle_nav,
            on_toggle_theme=self.toggle_theme,
            on_settings=None,
            on_exit=self.exit_app,
            bg=colors["BTN_BG"],
            mostrar_theme=True,
        )

        self.content = ft.Column(
            controls=[top_stack, control_area],
            spacing=12,
            expand=True,
        )

    # --------------------
    # Navegación
    # --------------------
    def _go_empleados(self):
        AppState().page.go("/trabajadores")

    # --------------------
    # Callbacks
    # --------------------
    def toggle_nav(self, e):
        self.layout_ctrl.toggle()
        self.expanded = self.layout_ctrl.is_expanded()
        self._build()
        self.update()

    def toggle_theme(self, e):
        self.theme_ctrl.toggle()
        self.dark = self.theme_ctrl.is_dark()
        self._build()
        self.update()

    def exit_app(self, e):
        page = AppState().page
        # Limpia sesión y restablece estados
        page.client_storage.remove("app.user")
        self.layout_ctrl.set(False)
        self.theme_ctrl.apply_theme()
        # Cerrar aplicación
        page.window_close()
