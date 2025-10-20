from __future__ import annotations
import flet as ft
from typing import Optional, Callable, List, Dict, Any

from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController
from app.views.containers.nvar.layout_controller import LayoutController
from app.views.containers.nvar.menu_buttons_area import MenuButtonsArea
from app.views.containers.nvar.control_buttons_area import ControlButtonsArea

_NAV_STORAGE_KEY = "ui.nav.expanded"


class NavBarContainer(ft.Container):
    """
    Barra lateral persistente con integración total de tema y layout.
    - Listener del LayoutController controlado con flag (sin duplicados).
    - Actualiza color activo según ruta actual.
    - Mantiene persistencia de expansión y tema.
    """

    def __init__(self):
        super().__init__(expand=False, padding=8)

        # Estado interno
        self._mounted: bool = False
        self._pending_route: Optional[str] = None
        self._expanded: bool = False
        self._listener_registered: bool = False  # ← evita duplicados

        # Controladores globales
        self.app = AppState()
        self.theme_ctrl = ThemeController()
        self.layout = LayoutController()

        # Leer estado expandido persistido
        try:
            self._expanded = self.layout.is_expanded()
            stored = self.app.get_client_value(_NAV_STORAGE_KEY, None)
            if isinstance(stored, bool):
                self._expanded = stored
        except Exception as e:
            print(f"[NavBar] ⚠️ No se pudo leer estado inicial expandido: {e}")

        # Config visual
        self._w_expanded = 220
        self._w_collapsed = 76

        # Subcomponentes
        self._menu: Optional[MenuButtonsArea] = None
        self._controls: Optional[ControlButtonsArea] = None
        self._theme_cb: Optional[Callable] = None

        # ❌ Ya NO registramos listener aquí para evitar duplicados
        # self.layout.ensure_listener(self._on_layout_change)

        # Construcción inicial
        print(f"[NavBar] 🧩 Creando NavBarContainer (expandido={self._expanded})")
        self._build_ui()

    # ======================================================
    # Ciclo de vida
    # ======================================================
    def did_mount(self):
        self._mounted = True
        print("[NavBar] ✅ Montado correctamente")

        # 🔁 Registrar listener del LayoutController SOLO si no está
        if not self._listener_registered:
            try:
                self.layout.ensure_listener(self._on_layout_change)
                self._listener_registered = True
            except Exception as e:
                print(f"[NavBar] ⚠️ No se pudo registrar listener: {e}")

        try:
            total = len(getattr(self.layout, "_listeners", []))
        except Exception:
            total = "?"
        print(f"[LayoutController] 👂 Listener activo (registered={self._listener_registered}, total={total})")

        # Suscripción al cambio de tema (sin duplicar)
        if not self._theme_cb:
            self._theme_cb = self._on_theme_change
            self.app.on_theme_change(self._theme_cb)

        # Ajustes visuales
        self.width = self.layout.width(self._w_expanded, self._w_collapsed)
        self.animate = ft.animation.Animation(300, ft.AnimationCurve.EASE_IN_OUT_CUBIC)
        self._apply_palette()

        # 🔄 Re-sincronizar la ruta actual del page si existe
        page = self.app.get_page()
        if page and page.route:
            print(f"[NavBar] 🔄 Ruta detectada en montaje: {page.route}")
            self.set_current_route(page.route)

        # Restaura ruta pendiente
        if self._pending_route:
            print(f"[NavBar] 🔄 Aplicando ruta pendiente: {self._pending_route}")
            self.set_current_route(self._pending_route)
            self._pending_route = None

        self._safe_update()

    def will_unmount(self):
        print("[NavBar] 🔻 Desmontando NavBarContainer, limpiando listeners...")
        self._mounted = False

        # 🧹 Limpieza segura de listeners y callbacks
        if self._listener_registered:
            try:
                self.layout.remove_listener(self._on_layout_change)
            except Exception:
                pass
            self._listener_registered = False

        if self._theme_cb:
            try:
                self.app.off_theme_change(self._theme_cb)
            except Exception:
                pass
            self._theme_cb = None

        self._menu = None
        self._controls = None

    # ======================================================
    # Construcción UI
    # ======================================================
    def _menu_items(self) -> List[Dict[str, Any]]:
        return [
            {"icon_src": "assets/buttons/user-manager-area-button.png", "label": "Mi perfil", "tooltip": "Usuario actual", "route": None, "key": "usuario"},
            {"icon_src": "assets/buttons/home-area-button.png", "label": "Inicio", "tooltip": "Ir a inicio", "route": "/home", "key": "home"},
            {"icon_src": "assets/buttons/employees-button.png", "label": "Trabajadores", "tooltip": "Gestión de trabajadores", "route": "/trabajadores", "key": "trabajadores"},
            {"icon_src": "assets/buttons/inventario-area-button.png", "label": "Inventario", "tooltip": "Gestión de inventario", "route": "/inventario", "key": "inventario"},
            {"icon_src": "assets/buttons/settings-button.png", "label": "Configuración", "tooltip": "Ajustes del sistema", "route": "/configuracion", "key": "configuracion"},
        ]

    def _build_ui(self):
        pal = self.theme_ctrl.get_colors("navbar")
        page = self.app.get_page()

        # ⚠️ No forzar /home aquí; usamos la ruta real si existe.
        current_route = page.route if page and page.route else None

        print(f"[NavBar] 🎨 Construyendo interfaz (route={current_route})")

        # Menú lateral
        self._menu = MenuButtonsArea(
            expanded=self._expanded,
            dark=self.theme_ctrl.is_dark(),
            bg=pal.get("ITEM_BG", pal.get("BTN_BG", ft.colors.GREY_200)),
            fg=pal.get("ITEM_FG", ft.colors.ON_SURFACE),
            items=self._menu_items(),
            spacing=10,
            padding=8,
            current_route=current_route,
        )

        # Separadores y controles inferiores
        divider = ft.Divider(thickness=1, height=14)
        spacer = ft.Container(expand=True)

        self._controls = ControlButtonsArea(
            theme_ctrl=self.theme_ctrl,
            on_toggle_theme=self._toggle_theme,
            on_toggle_expand=self._toggle_expand,
            on_logout=self._logout,
            expanded=self._expanded,
            spacing=10,
        )

        # Layout principal
        self.content = ft.Column(
            controls=[self._menu, divider, spacer, self._controls],
            spacing=10,
            expand=True,
            alignment=ft.MainAxisAlignment.START if self._expanded else ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH if self._expanded else ft.CrossAxisAlignment.CENTER,
        )

        self.width = self.layout.width(self._w_expanded, self._w_collapsed)
        self.bgcolor = pal.get("BG_COLOR")
        self.animate = ft.animation.Animation(300, ft.AnimationCurve.EASE_IN_OUT_CUBIC)

    # ======================================================
    # Paleta / Tema
    # ======================================================
    def _apply_palette(self):
        pal = self.theme_ctrl.get_colors("navbar")
        self.bgcolor = pal.get("BG_COLOR")

        if isinstance(self.content, ft.Column):
            for ctrl in self.content.controls:
                if isinstance(ctrl, ft.Divider):
                    ctrl.color = pal.get("DIVIDER_COLOR")

        if not self._mounted:
            return

        page = self.app.get_page()

        if self._menu:
            self._menu.update_state(
                current_route=(page.route if page else None),
                expanded=self._expanded,
                dark=self.theme_ctrl.is_dark(),
                bg=pal.get("ITEM_BG", pal.get("BTN_BG", ft.colors.GREY_200)),  # ← NUEVO
                fg=pal.get("ITEM_FG", ft.colors.ON_SURFACE),                    # ← NUEVO
                force=True,
            )
        if self._controls:
            self._controls.update_state(expanded=self._expanded)

        print(f"[NavBar] 🎨 Paleta aplicada (modo={'oscuro' if self.theme_ctrl.is_dark() else 'claro'})")


    # ======================================================
    # Eventos / Listeners
    # ======================================================
    def _on_theme_change(self):
        if not self._mounted:
            return
        print("[NavBar] 🎨 Cambio de tema detectado → reaplicando paleta")
        self._apply_palette()
        self._safe_update()

    def _on_layout_change(self, expanded: bool):
        self._expanded = bool(expanded)
        self.width = self.layout.width(self._w_expanded, self._w_collapsed)
        print(f"[NavBar] 🔄 Cambio de layout → expandido={self._expanded}")

        try:
            self.app.set_client_value(_NAV_STORAGE_KEY, self._expanded)
        except Exception:
            pass

        if not self._mounted:
            return

        page = self.app.get_page()
        pal = self.theme_ctrl.get_colors("navbar")  # ← para mantener paleta coherente

        if self._menu:
            self._menu.update_state(
                current_route=(page.route if page else None),
                expanded=self._expanded,
                dark=self.theme_ctrl.is_dark(),
                bg=pal.get("ITEM_BG", pal.get("BTN_BG", ft.colors.GREY_200)),  # ← NUEVO
                fg=pal.get("ITEM_FG", ft.colors.ON_SURFACE),                    # ← NUEVO
            )
        if self._controls:
            self._controls.update_state(expanded=self._expanded)

        # Ajuste visual de centrado
        if isinstance(self.content, ft.Column):
            self.content.alignment = (
                ft.MainAxisAlignment.START if self._expanded else ft.MainAxisAlignment.CENTER
            )
            self.content.horizontal_alignment = (
                ft.CrossAxisAlignment.STRETCH if self._expanded else ft.CrossAxisAlignment.CENTER
            )

        self._safe_update()


    # ======================================================
    # Acciones inferiores
    # ======================================================
    def _toggle_expand(self, *_):
        print(f"[NavBar] 🔘 Toggle expand/collapse (actual={self._expanded})")
        self.layout.toggle(persist=True)

    def _toggle_theme(self, *_):
        print("[NavBar] 🌗 Toggle de tema solicitado")
        self.theme_ctrl.toggle()

    def _logout(self, *_):
        """
        Cierra la aplicación por completo.
        - Persiste estado útil (expandido y tema).
        - Limpia claves de sesión en client_storage.
        - Evita rebotes de navegación.
        - Intenta cerrar la ventana de forma robusta (destroy → close → exit).
        """
        print("[NavBar] 🚪 Logout solicitado (guardando cambios y cerrando aplicación)")
        page = self.app.get_page()

        try:
            # 1) Persistencias mínimas
            self.layout.set_state(self._expanded, persist=True)
            # Usa AppState como fuente de verdad de tema (clave 'app.theme')
            self.app.set_client_value(
                "app.theme",
                "dark" if self.theme_ctrl.is_dark() else "light"
            )

            # 2) Limpiar sesión y evitar rebotes
            if page:
                # Claves típicas de sesión (amplía si usas otras)
                for k in ("app.user", "session.user", "auth.token"):
                    try:
                        page.client_storage.remove(k)
                    except Exception:
                        pass

                # Evitar que algún handler intente redirigir al login
                try:
                    page.on_route_change = None
                except Exception:
                    pass

            print("[NavBar] 💾 Estado guardado y sesión limpiada correctamente.")

            # 3) Cierre robusto de la ventana / proceso
            if page:
                print("[NavBar] 🪟 Cerrando aplicación...")
                # Asegura vaciado de cambios visuales antes de cerrar
                try:
                    page.update()
                except Exception:
                    pass

                try:
                    # En desktop, destroy suele ser el más “fuerte”
                    page.window_destroy()
                    return
                except Exception:
                    try:
                        page.window_close()
                        return
                    except Exception:
                        pass

            # 4) Último recurso: terminar el proceso (si estamos fuera de un Page válido)
            try:
                import sys
                sys.exit(0)
            except SystemExit:
                pass
            except Exception:
                pass

            # Fallback final duro
            try:
                import os
                os._exit(0)
            except Exception:
                pass

        except Exception as e:
            print(f"[NavBar] ⚠️ Error al intentar cerrar sesión: {e}")


    # ======================================================
    # API pública
    # ======================================================
    def set_current_route(self, route: str):
        print(f"[NavBar] 📍 Sincronizando ruta actual → {route}")
        if not self._mounted:
            self._pending_route = route
            return
        if self._menu:
            self._menu.set_current_route(route)
        self._safe_update()

    # ======================================================
    # Utilidades
    # ======================================================
    def _safe_update(self):
        try:
            self.update()
        except Exception:
            page = self.app.get_page()
            if page:
                try:
                    page.update()
                except Exception:
                    pass
