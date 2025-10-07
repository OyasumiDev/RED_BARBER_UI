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

        # Conectar la Page al ThemeController (aplica el tema guardado)
        self.theme_ctrl.attach_page(self._page)

        # Área dinámica de contenido
        self.content_area = ft.Container(expand=True)
        self._page.add(self.content_area)

        # Suscripción opcional a cambios de tema (si tu AppState expone on_theme_change)
        on_theme_change = getattr(state, "on_theme_change", None)
        if callable(on_theme_change):
            on_theme_change(self._apply_theme_to_shell)

        # Ruteo
        self._page.on_route_change = self.route_change

        # Aplicar colores al shell inicial
        self._apply_theme_to_shell()

        # Ruta inicial
        self._page.go("/login")
        # self._page.go("/home")

    # ---------------------------
    # Configuración de ventana
    # ---------------------------
    def _configurar_ventana(self):
        self._page.title = "Sistema de gestión"
        self._page.window.icon = "logos/red_icon.ico"
        self._page.padding = 0
        # No fijamos theme_mode aquí; lo gestiona ThemeController
        self._page.theme = ft.Theme(color_scheme_seed=ft.colors.BLUE_ACCENT_100)
        self._page.window_maximized = True
        self._page.window_resizable = True
        self._page.window.center()

    # ---------------------------
    # Aplicar colores del tema al shell
    # ---------------------------
    def _apply_theme_to_shell(self):
        if not self._page:
            return

        colors = self.theme_ctrl.get_colors()

        # Fondo de la Page
        try:
            self._page.bgcolor = colors.get("BG_COLOR")
        except Exception:
            pass

        # Fondo del host principal
        if self.content_area is not None:
            self.content_area.bgcolor = colors.get("BG_COLOR")

        # Si el contenido actual es el layout con navbar (Container que envuelve al Row)
        if isinstance(self.content_area.content, ft.Container):
            try:
                self.content_area.content.bgcolor = colors.get("BG_COLOR")
            except Exception:
                pass

        try:
            self._page.update()
        except Exception:
            pass

    # ---------------------------
    # Manejo de rutas
    # ---------------------------
    def route_change(self, route: ft.RouteChangeEvent):
        path = (route.route or "/login").rstrip("/") or "/login"

        if path == "/login":
            self._set_content([LoginContainer()], use_navbar=False)

        elif path == "/home":
            self._set_content([HomeContainer()], use_navbar=True)

        elif path in ("/trabajadores", "/empleados"):
            self._set_content([TrabajadoresContainer()], use_navbar=True)

        else:
            self._set_content([
                ft.Text(
                    "Vista no encontrada o sin acceso",
                    size=20,
                    weight="bold",
                    color=self.theme_ctrl.get_colors().get("FG_COLOR", ft.colors.ON_SURFACE),
                )
            ], use_navbar=True)

    # ---------------------------
    # Actualizar contenido
    # ---------------------------
    def _set_content(self, controls: list[ft.Control], use_navbar: bool = True):
        colors = self.theme_ctrl.get_colors()

        if use_navbar:
            if not self.nav_bar:
                self.nav_bar = NavBarContainer()

            nav_host = ft.Container(
                content=self.nav_bar,
                expand=False,
                bgcolor=colors.get("BG_COLOR"),
            )
            content_host = ft.Container(
                content=ft.Column(controls, expand=True, scroll=ft.ScrollMode.AUTO),
                expand=True,
                bgcolor=colors.get("BG_COLOR"),
            )

            # Row NO acepta bgcolor -> lo envolvemos en un Container con fondo
            layout_row = ft.Row(
                controls=[nav_host, content_host],
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                alignment=ft.MainAxisAlignment.START,
            )
            layout = ft.Container(
                content=layout_row,
                expand=True,
                bgcolor=colors.get("BG_COLOR"),
            )
            self.content_area.content = layout
        else:
            # Vistas sin nav (login)
            self.content_area.content = ft.Column(
                controls=controls,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
            self.content_area.bgcolor = colors.get("BG_COLOR")

        # Reaplica colores al shell para asegurar consistencia
        self._apply_theme_to_shell()

        try:
            self.content_area.update()
        except Exception:
            pass
        try:
            self._page.update()
        except Exception:
            pass

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
