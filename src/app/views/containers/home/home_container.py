# app/views/containers/home/home_container.py
from __future__ import annotations
import json
import flet as ft
from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController


class HomeContainer(ft.Container):
    """
    Vista Home:
    - Usa paleta de área "home" desde ThemeController/AppState.
    - Encabezado con banda roja (TITLE_BG) y texto blanco (TITLE_FG).
    - Divisor/linea de sección roja (SECTION_LINE / DIVIDER_COLOR).
    - Tarjetas con fondo de CARD_BG, borde sutil y texto según FG_COLOR.
    - Reactivo a cambios de tema y del usuario en client_storage.
    """

    AREA = "home"

    def __init__(self):
        super().__init__(expand=True, padding=20)

        # Globals
        self.app_state = AppState()
        self.page = self.app_state.get_page()
        self.theme_ctrl = ThemeController()

        # Estado
        self._mounted = False
        self.colors = self._get_colors_area()
        self.user_data = self._load_user_safe()
        self.rol = self.user_data.get("rol", "guest")
        self.nombre = self.user_data.get("nombre_completo", self.user_data.get("username", "Usuario"))

        # Fondo raíz según área
        self.bgcolor = self.colors.get("BG_COLOR")

        # ---------- Encabezado con banda roja ----------
        self.title_text = ft.Text(
            f"Bienvenido, {self.nombre} ({self.rol})",
            size=22,
            weight="bold",
            color=self.colors.get("TITLE_FG", ft.colors.WHITE),
        )
        self.header_band = ft.Container(
            bgcolor=self.colors.get("TITLE_BG", ft.colors.RED_600),
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            border_radius=8,
            content=self.title_text,
        )

        # Divider rojo fino
        self.section_line = ft.Divider(
            color=self.colors.get("SECTION_LINE", self.colors.get("DIVIDER_COLOR", ft.colors.RED_300)),
            height=18,
            thickness=1,
        )

        # ---------- Dashboard ----------
        self.dashboard_area = self._build_dashboard()

        # Layout
        self.content = ft.Column(
            [
                self.header_band,
                self.section_line,
                self.dashboard_area,
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=14,
        )

        # Suscripción a cambios de tema
        self.app_state.on_theme_change(self._on_theme_changed)

    # =========================================================
    # Ciclo de vida
    # =========================================================
    def did_mount(self):
        self._mounted = True
        self.page = self.app_state.get_page()
        # Por si el usuario cambió justo antes de montar
        self._reload_user()
        self.colors = self._get_colors_area()
        self._rebuild_dashboard()   # asegura tarjetas correctas para el rol actual
        self._apply_colors()
        self._safe_update()

    def will_unmount(self):
        self._mounted = False
        self.app_state.off_theme_change(self._on_theme_changed)

    # =========================================================
    # Reacción a cambios de tema
    # =========================================================
    def _on_theme_changed(self):
        self.colors = self._get_colors_area()
        self._apply_colors()
        self._safe_update()

    # =========================================================
    # Utils de tema / datos
    # =========================================================
    def _get_colors_area(self) -> dict:
        try:
            return self.theme_ctrl.get_colors(self.AREA) or {}
        except Exception:
            return {}

    def _reload_user(self):
        self.user_data = self._load_user_safe()
        self.rol = self.user_data.get("rol", "guest")
        self.nombre = self.user_data.get("nombre_completo", self.user_data.get("username", "Usuario"))

    def _apply_colors(self):
        # raíz
        self.bgcolor = self.colors.get("BG_COLOR", self.bgcolor)

        # header band
        self.header_band.bgcolor = self.colors.get("TITLE_BG", ft.colors.RED_600)
        self.title_text.value = f"Bienvenido, {self.nombre} ({self.rol})"
        self.title_text.color = self.colors.get("TITLE_FG", ft.colors.WHITE)

        # divider/línea
        self.section_line.color = self.colors.get(
            "SECTION_LINE", self.colors.get("DIVIDER_COLOR", ft.colors.RED_300)
        )

        # tarjetas
        self._refresh_cards()

    def _refresh_cards(self):
        if isinstance(self.dashboard_area, ft.Row):
            for c in self.dashboard_area.controls:
                if isinstance(c, ft.Container):
                    c.bgcolor = self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
                    border_col = self.colors.get("BORDER", None)
                    if border_col:
                        c.border = ft.border.all(1, border_col)
                    shadow_col = self.theme_ctrl.get_colors().get("SHADOW")
                    c.shadow = ft.BoxShadow(
                        blur_radius=10,
                        spread_radius=0,
                        offset=ft.Offset(0, 3),
                        color=shadow_col if shadow_col else ft.colors.with_opacity(0.12, ft.colors.BLACK),
                    )
                    if isinstance(c.content, ft.Column):
                        for t in c.content.controls:
                            if isinstance(t, ft.Text):
                                t.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _safe_update(self):
        if self.page:
            try:
                self.page.update()
            except AssertionError:
                pass

    # =========================================================
    # Carga segura de usuario
    # =========================================================
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
        except Exception:
            return {}

    # =========================================================
    # Dashboard según rol
    # =========================================================
    def _build_dashboard(self) -> ft.Row:
        rol_method = {
            "barbero": self._barbero_dashboard,
            "dueno": self._dueno_dashboard,
            "recepcionista": self._recepcion_dashboard,
            "cajero": self._caja_dashboard,
            "inventarista": self._inventario_dashboard,
            "root": self._admin_dashboard,
        }.get(self.rol)

        return (rol_method() if rol_method else
                ft.Row([self._card("Rol no reconocido", "—")], expand=True))

    def _rebuild_dashboard(self):
        """Reconstruye las tarjetas según el rol actual y aplica colores."""
        self.dashboard_area = self._build_dashboard()
        # Reemplaza el 3er control del Column (index 2)
        try:
            if isinstance(self.content, ft.Column) and len(self.content.controls) >= 3:
                self.content.controls[2] = self.dashboard_area
                # Aplica colores a las nuevas tarjetas
                self._refresh_cards()
        except Exception:
            pass

    # ---- Dashboards por rol ----
    def _barbero_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Servicios asignados", "3"),
                       self._card("Comisión acumulada", "$450")],
                      expand=True)

    def _dueno_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Ganancia total hoy", "$1200"),
                       self._card("Clientes atendidos", "18"),
                       self._card("Inventario crítico", "2 materiales")],
                      expand=True)

    def _recepcion_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Citas del día", "12"),
                       self._card("Clientes en espera", "3")],
                      expand=True)

    def _caja_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Cobros pendientes", "$300"),
                       self._card("Ventas del día", "$1500")],
                      expand=True)

    def _inventario_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Materiales bajos", "5"),
                       self._card("Solicitudes abiertas", "2")],
                      expand=True)

    def _admin_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Usuarios activos", "6"),
                       self._card("Servicios totales hoy", "20"),
                       self._card("Ingresos generales", "$2000")],
                      expand=True)

    # =========================================================
    # Card genérica
    # =========================================================
    def _card(self, title: str, value: str) -> ft.Container:
        return ft.Container(
            bgcolor=self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)),
            border_radius=12,
            padding=16,
            expand=True,
            content=ft.Column(
                [
                    ft.Text(
                        title,
                        size=16,
                        weight="bold",
                        color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                    ),
                    ft.Text(
                        value,
                        size=22,
                        weight="bold",
                        color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                    ),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
        )
