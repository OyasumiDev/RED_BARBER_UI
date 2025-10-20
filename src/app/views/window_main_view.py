from __future__ import annotations
import flet as ft
from typing import Any
from app.helpers.class_singleton import class_singleton
from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController

# Contenedores / Vistas
from app.views.containers.loggin.login_container import LoginContainer
from app.views.containers.home.home_container import HomeContainer
from app.views.containers.nvar.navbar_container import NavBarContainer
from app.views.containers.home.trabajadores.trabajadores_container import TrabajadoresContainer
from app.views.containers.home.inventario.inventario_container import InventarioContainer


@class_singleton
class WindowMain:
    def __init__(self):
        self._page: ft.Page | None = None
        self.theme_ctrl = ThemeController()

        self.nav_bar: NavBarContainer | None = None
        self.content_area: ft.Container | None = None
        self._nav_host: ft.Container | None = None
        self._content_host: ft.Container | None = None
        self._current_module: str | None = None

        # Flags
        self._navbar_initialized: bool = False
        self._shell_ready: bool = False  # ⬅️ Shell persistente

    # =========================================================
    # Entry point
    # =========================================================
    def __call__(self, flet_page: ft.Page) -> Any:
        self._page = flet_page
        print("🚀 [BOOT] Inicializando WindowMain...")
        self._configurar_ventana()

        app = AppState()
        app.set_page(self._page)
        self.theme_ctrl.attach_page(self._page)

        # Crear contenedor raíz
        self.content_area = ft.Container(expand=True)
        self._page.add(self.content_area)
        app.set("root_container", self.content_area)
        app.on_theme_change(self._apply_theme_to_shell)

        # Ruta inicial
        initial_path = self._page.route or "/login"
        print(f"🧭 [ROUTER] Ruta inicial detectada: {initial_path}")
        self._page.on_route_change = self.route_change
        self._page.go(initial_path)

    # =========================================================
    # Configuración de ventana
    # =========================================================
    def _configurar_ventana(self):
        print("🪟 [WINDOW] Configurando ventana principal...")
        self._page.title = "Sistema de gestión"
        self._page.window.icon = "logos/red_icon.ico"
        self._page.padding = 0
        self._page.theme = ft.Theme(color_scheme_seed=ft.colors.RED_400, use_material3=True)
        self._page.window_maximized = True
        self._page.window_resizable = True
        self._page.window.center()

    # =========================================================
    # Shell persistente (Nav + Content)
    # =========================================================
    def _ensure_shell(self):
        if self._shell_ready:
            return

        nav_colors = self.theme_ctrl.get_colors("navbar")
        content_colors = self.theme_ctrl.get_colors(self._current_module or "home")
        app = AppState()

        # Crear NavBar si no existe
        if not self.nav_bar:
            print("🧩 [NAV] Creando NavBarContainer inicial (shell)...")
            self.nav_bar = NavBarContainer()
            self._navbar_initialized = True

        # Hosts persistentes
        self._nav_host = ft.Container(
            content=self.nav_bar,
            expand=False,
            bgcolor=nav_colors.get("BG_COLOR"),
        )
        self._content_host = ft.Container(
            content=ft.Column([], expand=True, scroll=ft.ScrollMode.AUTO),
            expand=True,
            bgcolor=content_colors.get("BG_COLOR"),
        )

        layout_row = ft.Row(
            controls=[self._nav_host, self._content_host],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            alignment=ft.MainAxisAlignment.START,
        )

        self.content_area.content = ft.Container(
            content=layout_row,
            expand=True,
            bgcolor=content_colors.get("BG_COLOR"),
        )

        app.set("content_container", self._content_host)
        app.set("nav_container", self.nav_bar)

        self._shell_ready = True
        print("🧱 [SHELL] Estructura persistente creada.")

    # =========================================================
    # Sanitización profunda (evita ciclos de referencia)
    # =========================================================
    def _sanitize_control_tree(self, root: ft.Control | None):
        """
        Limpieza segura del árbol de controles SIN tocar `control.data`,
        porque se usa para mapear rutas en el menú lateral.
        """
        if not root:
            return
        visited = set()

        def _walk(c: ft.Control):
            if c is None:
                return
            cid = id(c)
            if cid in visited:
                return
            visited.add(cid)

            # ⚠️ Importante: NO limpiar c.data. Se usa para route mapping.
            # if hasattr(c, "data"): c.data = None

            for attr in ("content", "controls"):
                val = getattr(c, attr, None)
                if isinstance(val, ft.Control):
                    _walk(val)
                elif isinstance(val, list):
                    for x in val:
                        if isinstance(x, ft.Control):
                            _walk(x)

        _walk(root)
        print("🧹 [SANITIZE] Árbol de controles limpiado (data preservada).")

    def _pre_update_sanitize(self):
        try:
            self._sanitize_control_tree(self.content_area)
        except Exception as e:
            print(f"⚠️ [SANITIZE] Error durante limpieza: {e}")

    # =========================================================
    # Aplicar tema
    # =========================================================
    def _apply_theme_to_shell(self):
        try:
            if not self._page:
                return
            app = AppState()
            global_colors = self.theme_ctrl.get_colors()
            self._page.bgcolor = global_colors.get("BG_COLOR")

            if self.content_area:
                colors = self.theme_ctrl.get_colors(self._current_module) if self._current_module else global_colors
                self.content_area.bgcolor = colors.get("BG_COLOR")

            if self._nav_host:
                self._nav_host.bgcolor = self.theme_ctrl.get_colors("navbar").get("BG_COLOR")

            if self._content_host:
                colors = self.theme_ctrl.get_colors(self._current_module) if self._current_module else global_colors
                self._content_host.bgcolor = colors.get("BG_COLOR")

            app.set("content_container", self._content_host or self.content_area)
            app.set("nav_container", self.nav_bar)

            print(f"🎨 [THEME] Tema aplicado (área={self._current_module})")
        except Exception as e:
            print(f"⚠️ [THEME] Error al aplicar tema: {e}")

    # =========================================================
    # Manejo de rutas
    # =========================================================
    def route_change(self, route: ft.RouteChangeEvent):
        path = (route.route or "/login").rstrip("/") or "/login"
        print(f"🧭 [ROUTE] Cambio detectado → {path}")

        try:
            if path == "/login":
                self._current_module = None
                self._set_content([LoginContainer()], use_navbar=False)
                self._sync_nav_selection(path)
                return

            if path == "/home":
                self._current_module = "home"
                self._set_content([HomeContainer()], use_navbar=True)
                self._sync_nav_selection(path)
                return

            if path in ("/trabajadores", "/empleados"):
                self._current_module = "trabajadores"
                self._set_content([TrabajadoresContainer()], use_navbar=True)
                self._sync_nav_selection(path)
                return

            if path in ("/inventario", "/inventory"):
                self._current_module = "inventario"
                self._set_content([InventarioContainer()], use_navbar=True)
                self._sync_nav_selection(path)
                return

            # Ruta no reconocida → redirigir a /home para no desincronizar UI/URL
            print(f"⚠️ [ROUTE] Ruta no reconocida: {path} → redirigiendo a /home")
            if self._page:
                self._page.go("/home")
            return

        except Exception as e:
            print(f"❌ [ROUTE] Error manejando ruta {path}: {e}")

    def _sync_nav_selection(self, path: str):
        try:
            if self.nav_bar:
                normalized = (path or "").rstrip("/") or "/"
                self.nav_bar.set_current_route(normalized)
                print(f"📍 [NAV] Ruta sincronizada → {normalized}")
        except Exception as e:
            print(f"⚠️ [NAV] Error sincronizando ruta: {e}")

    # =========================================================
    # Construcción del layout por vista
    # =========================================================
    def _set_content(self, controls: list[ft.Control], use_navbar: bool = True):
        print(f"🔧 [SET_CONTENT] Montando vista (use_navbar={use_navbar}, módulo={self._current_module})")
        try:
            app = AppState()

            if use_navbar:
                # 👉 Shell persistente: crea una sola vez y solo cambia el panel derecho
                self._ensure_shell()

                colors = self.theme_ctrl.get_colors(self._current_module or "home")
                if self._content_host:
                    self._content_host.bgcolor = colors.get("BG_COLOR")
                    self._content_host.content = ft.Column(controls, expand=True, scroll=ft.ScrollMode.AUTO)

                app.set("content_container", self._content_host)
                app.set("nav_container", self.nav_bar)

            else:
                # Vista sin barra (p. ej., login). Podemos “apagar” el shell.
                self._shell_ready = False
                self._nav_host = None
                self._content_host = None

                content_colors = self.theme_ctrl.get_colors(self._current_module or "home")
                self.content_area.content = ft.Container(
                    content=ft.Column(
                        controls=controls,
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        expand=True,
                    ),
                    expand=True,
                    bgcolor=content_colors.get("BG_COLOR"),
                )
                app.set("content_container", self.content_area)
                app.set("nav_container", None)

            # Aplicar tema, sanitizar y actualizar
            self._apply_theme_to_shell()
            self._pre_update_sanitize()
            try:
                self.content_area.update()
                self._page.update()
                print("✅ [SET_CONTENT] Vista montada y actualizada correctamente.")
            except Exception as e:
                print(f"⚠️ [SET_CONTENT] Error en update: {e} → reintento tras sanitizar.")
                self._pre_update_sanitize()
                self.content_area.update()
                self._page.update()

        except Exception as e:
            print(f"❌ [SET_CONTENT] Error crítico al montar vista: {e}")
            self.content_area.content = ft.Text(f"Error al montar vista: {e}", color=ft.colors.RED_400)
            try:
                self._page.update()
            except Exception:
                pass

    # =========================================================
    # Utilidades
    # =========================================================
    def _current_route_str(self, fallback: str = "/home") -> str:
        r = (self._page.route if self._page else None) or fallback
        return r.rstrip("/") or "/"

    def page_update(self):
        try:
            print("🔄 [PAGE] Forzando actualización manual de la página...")
            self._pre_update_sanitize()
            self._page.update()
        except Exception as e:
            print(f"⚠️ [PAGE] Error al actualizar página: {e}")


# Singleton global
window_main = WindowMain()
