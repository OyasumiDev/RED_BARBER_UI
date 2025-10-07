# app/views/containers/home/home_container.py

import flet as ft
from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController


class HomeContainer(ft.Container):
    def __init__(self):
        super().__init__(expand=True, padding=20)

        self.page = AppState().page
        self.theme_ctrl = ThemeController()
        self.colors = self.theme_ctrl.get_colors()

        # Recuperamos usuario actual
        self.user_data = self.page.client_storage.get("app.user") or {}
        self.rol = self.user_data.get("rol", "guest")
        self.nombre = self.user_data.get("nombre_completo", "Usuario")

        # Sección de bienvenida

        # Sección de bienvenida (color explícito + fondo dinámico)
        if self.theme_ctrl.is_dark():
            welcome_color = ft.colors.WHITE
            welcome_bg = ft.colors.GREY_900
        else:
            welcome_color = ft.colors.BLACK
            welcome_bg = ft.colors.GREY_200

        self.welcome_text = ft.Container(
            padding=10,
            border_radius=8,
            bgcolor=welcome_bg,  # 👈 fondo dinámico según tema
            content=ft.Text(
                f"Bienvenido, {self.nombre} ({self.rol})",
                size=24,
                weight="bold",
                color=welcome_color,  # 👈 texto siempre legible
            )
        )

        # Área principal
        self.dashboard_area = self._build_dashboard()

        # Layout
        self.content = ft.Column(
            [
                self.welcome_text,
                ft.Divider(color=self.colors["DIVIDER_COLOR"]),  # 👈 divider dinámico
                self.dashboard_area,
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    # ---------------------------
    # Construcción de dashboard según rol
    # ---------------------------
    def _build_dashboard(self) -> ft.Row:
        if self.rol == "barbero":
            return self._barbero_dashboard()
        elif self.rol == "dueno":
            return self._dueno_dashboard()
        elif self.rol == "recepcionista":
            return self._recepcion_dashboard()
        elif self.rol == "cajero":
            return self._caja_dashboard()
        elif self.rol == "inventarista":
            return self._inventario_dashboard()
        elif self.rol == "root":
            return self._admin_dashboard()
        else:
            return ft.Row([ft.Text("Rol no reconocido", color=self.colors["FG_COLOR"])])

    # Dashboards por rol
    def _barbero_dashboard(self) -> ft.Row:
        return ft.Row([
            self._card("Servicios asignados", "3"),
            self._card("Comisión acumulada", "$450"),
        ], expand=True)

    def _dueno_dashboard(self) -> ft.Row:
        return ft.Row([
            self._card("Ganancia total hoy", "$1200"),
            self._card("Clientes atendidos", "18"),
            self._card("Inventario crítico", "2 materiales"),
        ], expand=True)

    def _recepcion_dashboard(self) -> ft.Row:
        return ft.Row([
            self._card("Citas del día", "12"),
            self._card("Clientes en espera", "3"),
        ], expand=True)

    def _caja_dashboard(self) -> ft.Row:
        return ft.Row([
            self._card("Cobros pendientes", "$300"),
            self._card("Ventas del día", "$1500"),
        ], expand=True)

    def _inventario_dashboard(self) -> ft.Row:
        return ft.Row([
            self._card("Materiales bajos", "5"),
            self._card("Solicitudes abiertas", "2"),
        ], expand=True)

    def _admin_dashboard(self) -> ft.Row:
        return ft.Row([
            self._card("Usuarios activos", "6"),
            self._card("Servicios totales hoy", "20"),
            self._card("Ingresos generales", "$2000"),
        ], expand=True)

    # ---------------------------
    # Card genérica
    # ---------------------------
    def _card(self, title: str, value: str) -> ft.Container:
        return ft.Container(
            bgcolor=self.colors["BTN_BG"],  # 👈 fondo según tema
            border_radius=10,
            padding=20,
            expand=True,
            content=ft.Column([
                ft.Text(title, size=16, weight="bold", color=self.colors["FG_COLOR"]),  # 👈 texto dinámico
                ft.Text(value, size=20, weight="bold", color=self.colors["FG_COLOR"]),  # 👈 texto dinámico
            ])
        )
