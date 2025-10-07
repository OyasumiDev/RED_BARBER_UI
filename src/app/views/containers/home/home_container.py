import json
import flet as ft
from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController


class HomeContainer(ft.Container):
    """
    Contenedor principal de inicio, reactivo a cambios de tema y usuario.
    """

    def __init__(self):
        super().__init__(expand=True, padding=20)

        # Controladores globales
        self.app_state = AppState()
        self.page = self.app_state.get_page()
        self.theme_ctrl = ThemeController()

        # Estado interno
        self._mounted = False
        self.colors = self._get_colors_safe()
        self.user_data = self._load_user_safe()
        self.rol = self.user_data.get("rol", "guest")
        self.nombre = self.user_data.get("nombre_completo", "Usuario")

        # Construcción inicial
        welcome_color, welcome_bg = self._welcome_palette()
        self.welcome_text = ft.Container(
            padding=10,
            border_radius=8,
            bgcolor=welcome_bg,
            content=ft.Text(
                f"Bienvenido, {self.nombre} ({self.rol})",
                size=24,
                weight="bold",
                color=welcome_color,
            ),
        )

        self.dashboard_area = self._build_dashboard()

        self.content = ft.Column(
            [
                self.welcome_text,
                ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)),
                self.dashboard_area,
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # 🔄 Suscripción a cambios de tema (desde AppState / ThemeController)
        self.app_state.on_theme_change(self._on_theme_changed)

    # ---------------------------
    # Ciclo de vida
    # ---------------------------
    def did_mount(self):
        self._mounted = True
        self.user_data = self._load_user_safe()
        self.rol = self.user_data.get("rol", "guest")
        self.nombre = self.user_data.get("nombre_completo", "Usuario")
        self.colors = self._get_colors_safe()
        self._update_welcome()
        self._safe_update()

    def will_unmount(self):
        self._mounted = False
        self.app_state.off_theme_change(self._on_theme_changed)

    def _safe_update(self):
        p = getattr(self, "page", None)
        if p:
            try:
                p.update()
            except AssertionError:
                pass

    # ---------------------------
    # Reacción a cambios de tema
    # ---------------------------
    def _on_theme_changed(self):
        """Se llama automáticamente cuando cambia el tema global."""
        self.colors = self._get_colors_safe()
        self._update_welcome()
        self._refresh_cards()
        self._safe_update()

    def _refresh_cards(self):
        """Actualiza dinámicamente el color de todas las cards del dashboard."""
        if isinstance(self.dashboard_area, ft.Row):
            for c in self.dashboard_area.controls:
                if isinstance(c, ft.Container):
                    c.bgcolor = self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)
                    if isinstance(c.content, ft.Column):
                        for t in c.content.controls:
                            if isinstance(t, ft.Text):
                                t.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    # ---------------------------
    # Utilidades de tema / colores
    # ---------------------------
    def _get_colors_safe(self) -> dict:
        try:
            c = self.theme_ctrl.get_colors()
            return c if isinstance(c, dict) else {}
        except Exception:
            return {}

    def _welcome_palette(self):
        if self.theme_ctrl.is_dark():
            return ft.colors.WHITE, ft.colors.GREY_900
        return ft.colors.BLACK, ft.colors.GREY_200

    def _update_welcome(self):
        """Actualiza el texto y color de la bienvenida."""
        text_color, bg_color = self._welcome_palette()
        self.welcome_text.bgcolor = bg_color
        if isinstance(self.welcome_text.content, ft.Text):
            self.welcome_text.content.value = f"Bienvenido, {self.nombre} ({self.rol})"
            self.welcome_text.content.color = text_color

    # ---------------------------
    # Carga segura de usuario
    # ---------------------------
    def _load_user_safe(self) -> dict:
        p = getattr(self, "page", None)
        if not p:
            return {}
        try:
            raw = p.client_storage.get("app.user")
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str):
                raw = raw.strip()
                if raw.startswith("{") or raw.startswith("["):
                    return json.loads(raw) or {}
                return {}
            return {}
        except Exception:
            return {}

    # ---------------------------
    # Construcción de dashboard según rol
    # ---------------------------
    def _build_dashboard(self) -> ft.Row:
        rol_method = {
            "barbero": self._barbero_dashboard,
            "dueno": self._dueno_dashboard,
            "recepcionista": self._recepcion_dashboard,
            "cajero": self._caja_dashboard,
            "inventarista": self._inventario_dashboard,
            "root": self._admin_dashboard,
        }.get(self.rol, None)

        if rol_method:
            return rol_method()
        return ft.Row([
            ft.Text("Rol no reconocido", color=self.colors.get("FG_COLOR", ft.colors.PRIMARY))
        ])

    # ---------------------------
    # Dashboards por rol
    # ---------------------------
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
            bgcolor=self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT),
            border_radius=10,
            padding=20,
            expand=True,
            content=ft.Column([
                ft.Text(title, size=16, weight="bold",
                        color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
                ft.Text(value, size=20, weight="bold",
                        color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            ])
        )
