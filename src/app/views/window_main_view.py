# app/views/window_main_view.py

import flet as ft
from typing import Any
from app.config.application.app_state import AppState
from app.helpers.class_singleton import class_singleton
from app.config.application.theme_controller import ThemeController

# Contenedores / Vistas
from app.views.containers.loggin.login_container import LoginContainer
from app.views.containers.home.home_container import HomeContainer
from app.views.containers.nvar.navbar_container import NavBarContainer
from app.views.containers.home.trabajadores.trabajadores_container import TrabajadoresContainer


@class_singleton
class WindowMain:
    def __init__(self):
        self._page: ft.Page | None = None
        self.theme_ctrl = ThemeController()
        self.nav_bar: NavBarContainer | None = None
        self.content_area: ft.Container | None = None

    def __call__(self, flet_page: ft.Page) -> Any:
        self._page = flet_page
        self._configurar_ventana()

        # Estado global
        state = AppState()
        state.set_page(self._page)

        # Conectar page al ThemeController
        self.theme_ctrl.attach_page(self._page)

        # Área dinámica de contenido
        self.content_area = ft.Container(expand=True)
        self._page.add(self.content_area)

        # Ruteo
        self._page.on_route_change = self.route_change

        # Ruta inicial
        # self._page.go("/login")
        self._page.go("/home")  # <- desarrollo directo a home

    # ---------------------------
    # Configuración de ventana
    # ---------------------------
    def _configurar_ventana(self):
        self._page.title = "Sistema de gestión"
        self._page.window.icon = "logos/red_icon.ico"
        self._page.padding = 0
        self._page.theme_mode = ft.ThemeMode.LIGHT
        self._page.theme = ft.Theme(color_scheme_seed=ft.colors.BLUE_ACCENT_100)
        self._page.window_maximized = True
        self._page.window_resizable = True
        self._page.window.center()

    # ---------------------------
    # Manejo de rutas
    # ---------------------------
    def route_change(self, route: ft.RouteChangeEvent):
        path = (route.route or "/login").rstrip("/") or "/login"

        if path == "/login":
            # Solo login (sin navbar)
            self._set_content([LoginContainer()], use_navbar=False)

        elif path == "/home":
            # Layout principal con navbar
            self._set_content([HomeContainer()], use_navbar=True)

        elif path in ("/trabajadores", "/empleados"):
            self._set_content([TrabajadoresContainer()], use_navbar=True)

        else:
            self._set_content([
                ft.Text(
                    "Vista no encontrada o sin acceso",
                    size=20,
                    weight="bold",
                    color=self.theme_ctrl.get_fg_color()
                )
            ], use_navbar=True)

    # ---------------------------
    # Actualizar contenido
    # ---------------------------
    def _set_content(self, controls: list[ft.Control], use_navbar: bool = True):
        if use_navbar:
            if not self.nav_bar:
                self.nav_bar = NavBarContainer()

            # 👇 FIX CLAVE:
            #  - nav_host NO expande (fija el ancho al de la navbar)
            #  - content_host SÍ expande (ocupa el resto)
            #  - Row sin spacing y con stretch vertical
            nav_host = ft.Container(
                content=self.nav_bar,
                expand=False,             # <- fuerza a no expandir
            )
            content_host = ft.Container(
                content=ft.Column(controls, expand=True, scroll=ft.ScrollMode.AUTO),
                expand=True,              # <- ocupa todo el resto
            )

            layout = ft.Row(
                controls=[nav_host, content_host],
                expand=True,
                spacing=0,                                 # <- sin separación entre columnas
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,  # <- altura completa
                alignment=ft.MainAxisAlignment.START,
            )
            self.content_area.content = layout
        else:
            # Login u otras vistas sin nav
            self.content_area.content = ft.Column(
                controls=controls,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True
            )

        try:
            self.content_area.update()
        except Exception:
            pass
        self._page.update()

    # ---------------------------
    # Refresco manual
    # ---------------------------
    def page_update(self):
        try:
            self._page.update()
        except Exception:
            pass


# Singleton global
window_main = WindowMain()
