from __future__ import annotations
import flet as ft
from typing import Any, Optional

from app.helpers.class_singleton import class_singleton
from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController

# Contenedores / Vistas
from app.views.containers.loggin.login_container import LoginContainer
from app.views.containers.home.home_container import HomeContainer
from app.views.containers.nvar.navbar_container import NavBarContainer
from app.views.containers.home.trabajadores.trabajadores_container import TrabajadoresContainer
from app.views.containers.home.inventario.inventario_container import InventarioContainer
from app.views.containers.home.usuarios.users_settings_container import UsersSettingsContainer
from app.views.containers.home.agenda.agenda_container import AgendaContainer
from app.views.containers.home.servicios.servicios import ServiciosContainer
from app.views.containers.settings.settings import SettingsDBContainer
from app.views.containers.home.cortes.cortes_container import CortesContainer
# ✅ Contabilidad
from app.views.containers.home.contabilidad.contabilidad_container import ContabilidadContainer


@class_singleton
class WindowMain:
    def __init__(self):
        self._page: Optional[ft.Page] = None
        self.theme_ctrl = ThemeController()

        self.nav_bar: Optional[NavBarContainer] = None
        self.content_area: Optional[ft.Container] = None
        self._nav_host: Optional[ft.Container] = None
        self._content_host: Optional[ft.Container] = None
        self._current_module: Optional[str] = None

        # Flags
        self._navbar_initialized: bool = False
        self._shell_ready: bool = False  # Shell persistente

    # ------------------------------- Utils ---------------------------------
    @staticmethod
    def _coerce_color(val: Any, default: str) -> str:
        """
        Asegura que las propiedades de color sean cadenas (hex/rgba/nombre).
        Si llega un valor no escalar o vacío, usa 'default'.
        """
        return val if isinstance(val, str) and val.strip() else default

    def _is_root(self) -> bool:
        """Verifica si el usuario actual es root (por rol o username)."""
        try:
            app = AppState()
            user = None
            # Soporte para diferentes APIs del AppState
            if hasattr(app, "get"):
                user = app.get("app.user") or app.get("user") or {}
            if (not user) and hasattr(app, "get_client_value"):
                user = app.get_client_value("app.user", {})  # type: ignore[attr-defined]
            if isinstance(user, dict):
                rol = str(user.get("rol", "")).lower()
                username = str(user.get("username", "")).lower()
                return rol == "root" or username == "root"
        except Exception:
            pass
        return False

    # ================================ Entry =================================
    def __call__(self, flet_page: ft.Page) -> Any:
        self._page = flet_page
        print("🚀 [BOOT] Inicializando WindowMain...")
        self._configurar_ventana()

        app = AppState()
        app.set_page(self._page)
        self.theme_ctrl.attach_page(self._page)

        # Contenedor raíz
        self.content_area = ft.Container(expand=True)
        self._page.add(self.content_area)
        app.set("root_container", self.content_area)
        app.on_theme_change(self._apply_theme_to_shell)

        # Routing
        initial_path = self._page.route or "/login"
        print(f"🧭 [ROUTER] Ruta inicial detectada: {initial_path}")
        self._page.on_route_change = self.route_change
        self._page.go(initial_path)

    # ========================= Configuración ventana =========================
    def _configurar_ventana(self):
        print("🪟 [WINDOW] Configurando ventana principal...")
        self._page.title = "Sistema de gestión"
        self._page.window.icon = "logos/red_icon.ico"
        self._page.padding = 0
        self._page.theme = ft.Theme(color_scheme_seed=ft.colors.RED_400, use_material3=True)
        self._page.window_maximized = True
        self._page.window_resizable = True
        self._page.window.center()

    # ====================== Shell persistente (Nav + Content) =================
    def _ensure_shell(self):
        if self._shell_ready:
            return

        nav_colors = self.theme_ctrl.get_colors("navbar")
        content_colors = self.theme_ctrl.get_colors(self._current_module or "home")

        # Crear NavBar si no existe
        if not self.nav_bar:
            print("🧩 [NAV] Creando NavBarContainer inicial (shell)...")
            self.nav_bar = NavBarContainer()
            self._navbar_initialized = True

        # Hosts persistentes
        self._nav_host = ft.Container(
            content=self.nav_bar,
            expand=False,
            bgcolor=self._coerce_color(nav_colors.get("BG_COLOR"), ft.colors.SURFACE),
        )
        self._content_host = ft.Container(
            content=None,  # se llena en _set_content
            expand=True,
            bgcolor=self._coerce_color(content_colors.get("BG_COLOR"), ft.colors.SURFACE),
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
            bgcolor=self._coerce_color(content_colors.get("BG_COLOR"), ft.colors.SURFACE),
        )

        app = AppState()
        app.set("content_container", self._content_host)
        app.set("nav_container", self.nav_bar)

        self._shell_ready = True
        print("🧱 [SHELL] Estructura persistente creada.")

    # =================== Sanitización (evita ciclos en .data) =================
    def _sanitize_control_tree(self, root: Optional[ft.Control]):
        if not root:
            return
        visited = set()

        def _strip_controls_in(obj):
            if isinstance(obj, ft.Control):
                return None
            if isinstance(obj, (list, tuple, set)):
                t = type(obj)
                return t(_strip_controls_in(x) for x in obj)
            if isinstance(obj, dict):
                return {k: _strip_controls_in(v) for k, v in obj.items()}
            return obj

        def _walk(c: ft.Control):
            if c is None:
                return
            cid = id(c)
            if cid in visited:
                return
            visited.add(cid)

            try:
                if hasattr(c, "data") and c.data is not None:
                    cleaned = _strip_controls_in(c.data)
                    if cleaned is None or cleaned is not c.data:
                        c.data = cleaned
            except Exception:
                pass

            for attr in ("content", "controls"):
                val = getattr(c, attr, None)
                if isinstance(val, ft.Control):
                    _walk(val)
                elif isinstance(val, list):
                    for x in val:
                        if isinstance(x, ft.Control):
                            _walk(x)

        _walk(root)
        print("🧹 [SANITIZE] Árbol de controles limpiado (data sin Controls).")

    def _pre_update_sanitize(self):
        try:
            self._sanitize_control_tree(self.content_area)
        except Exception as e:
            print(f"⚠️ [SANITIZE] Error durante limpieza: {e}")

    # =============================== Tema ====================================
    def _apply_theme_to_shell(self):
        try:
            if not self._page:
                return

            global_colors = self.theme_ctrl.get_colors()

            # Fondo global de la página
            self._page.bgcolor = self._coerce_color(global_colors.get("BG_COLOR"), ft.colors.SURFACE)

            # Fondo del content_area (root host)
            if self.content_area:
                colors = self.theme_ctrl.get_colors(self._current_module) if self._current_module else global_colors
                self.content_area.bgcolor = self._coerce_color(colors.get("BG_COLOR"), ft.colors.SURFACE)

            # Fondo del host del navbar
            if self._nav_host:
                nav = self.theme_ctrl.get_colors("navbar")
                self._nav_host.bgcolor = self._coerce_color(nav.get("BG_COLOR"), ft.colors.SURFACE_VARIANT)

            # Fondo del host del contenido
            if self._content_host:
                colors = self.theme_ctrl.get_colors(self._current_module) if self._current_module else global_colors
                self._content_host.bgcolor = self._coerce_color(colors.get("BG_COLOR"), ft.colors.SURFACE)

            app = AppState()
            app.set("content_container", self._content_host or self.content_area)
            app.set("nav_container", self.nav_bar)

            print(f"🎨 [THEME] Tema aplicado (área={self._current_module})")
        except Exception as e:
            print(f"⚠️ [THEME] Error al aplicar tema: {e}")

    # ============================== Ruteo ====================================
    def route_change(self, route: ft.RouteChangeEvent):
        path = (route.route or "/login").rstrip("/") or "/login"
        print(f"🧭 [ROUTE] Cambio detectado → {path}")

        try:
            # --- Vistas sin navbar ---
            if path == "/login":
                self._current_module = None
                self._set_content([LoginContainer()], use_navbar=False)
                self._sync_nav_selection(path)
                return

            # --- Vistas con navbar ---
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

            if path in ("/servicios", "/services"):
                self._current_module = "servicios"
                self._set_content([ServiciosContainer()], use_navbar=True)
                self._sync_nav_selection(path)
                return

            if path in ("/users-settings", "/usuarios-ajustes", "/users"):
                self._current_module = "users-settings"
                self._set_content([UsersSettingsContainer()], use_navbar=True)
                self._sync_nav_selection(path)
                return

            if path in ("/agenda", "/agenda-citas", "/citas"):
                self._current_module = "agenda"
                self._set_content([AgendaContainer()], use_navbar=True)
                self._sync_nav_selection(path)
                return

            if path in ("/configuracion", "/settings", "/settings-db"):
                self._current_module = "settings"
                self._set_content([SettingsDBContainer(self._page)], use_navbar=True)
                self._sync_nav_selection(path)
                return

            if path in ("/cortes", "/pagos", "/cortes-pagos"):
                self._current_module = "cortes"
                self._set_content([CortesContainer()], use_navbar=True)
                self._sync_nav_selection(path)
                return

            # ✅ Guard de acceso para Contabilidad (solo root)
            if path in ("/contabilidad", "/contable", "/accounting"):
                if not self._is_root():
                    print("🚫 [ROUTE] Acceso no autorizado a Contabilidad → redirigiendo a /home")
                    if self._page:
                        self._page.go("/home")
                    return
                self._current_module = "contabilidad"
                self._set_content([ContabilidadContainer()], use_navbar=True)
                self._sync_nav_selection(path)
                return

            # Ruta no reconocida → /home
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

    # ===================== Construcción de layout por vista ===================
    def _set_content(self, controls: list[ft.Control], use_navbar: bool = True):
        print(f"🔧 [SET_CONTENT] Montando vista (use_navbar={use_navbar}, módulo={self._current_module})")
        try:
            app = AppState()

            if use_navbar:
                # Shell persistente: se crea una vez y solo se refresca el panel derecho
                self._ensure_shell()

                colors = self.theme_ctrl.get_colors(self._current_module or "home")
                if self._content_host:
                    self._content_host.bgcolor = self._coerce_color(colors.get("BG_COLOR"), ft.colors.SURFACE)
                    if len(controls) == 1:
                        self._content_host.content = controls[0]
                    else:
                        self._content_host.content = ft.Column(controls, expand=True, scroll=ft.ScrollMode.AUTO)

                app.set("content_container", self._content_host)
                app.set("nav_container", self.nav_bar)

            else:
                # Vista sin barra (login). “Apagamos” el shell visualmente.
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
                    bgcolor=self._coerce_color(content_colors.get("BG_COLOR"), ft.colors.SURFACE),
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
            if self.content_area:
                self.content_area.content = ft.Text(f"Error al montar vista: {e}", color=ft.colors.RED_400)
            try:
                self._page.update()
            except Exception:
                pass

    # ================================ Miscelánea ==============================
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
