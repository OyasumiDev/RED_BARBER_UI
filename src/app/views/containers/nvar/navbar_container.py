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
    Barra lateral principal:
      [UserIconArea]
      [QuickNavArea]      ← acceso rápido
      [Divider]
      [MenuButtonsArea]   ← módulos principales
      ----------------------------
      [ControlButtonsArea] ← abajo (tema, salir)
    """

    def __init__(self, is_root: bool = False):
        super().__init__(padding=10, expand=True)

        self.is_root = is_root
        self.layout_ctrl = LayoutController()
        self.theme_ctrl = ThemeController()
        self.app_state = AppState()

        # Estado inicial
        self.expanded = self.layout_ctrl.is_expanded()
        self.dark = self.theme_ctrl.is_dark()

        # Flags
        self._mounted = False
        self._theme_listener = None  # guardamos callback para evitar múltiples suscripciones

        # Construcción inicial
        self._build()

        # Suscripción a cambios de tema (una sola vez)
        self._register_theme_listener()

    # --------------------
    # Ciclo de vida
    # --------------------
    def did_mount(self):
        """Se llama automáticamente cuando el control se monta en la Page."""
        self._mounted = True
        self._apply_current_palette()
        self._safe_update()

    def will_unmount(self):
        """Se llama automáticamente al desmontarse del árbol."""
        self._mounted = False
        self._unregister_theme_listener()

    # --------------------
    # Listeners de tema
    # --------------------
    def _register_theme_listener(self):
        """
        Registra el callback en AppState si existe y no se ha registrado aún.
        Evita listeners duplicados si la navbar se reconstruye por ruteo.
        """
        if self._theme_listener is not None:
            return  # ya está
        cb = self._on_theme_changed
        # on_theme_change debe aceptar un call-able; si AppState devuelve un id úsalo si lo tienes.
        try:
            self.app_state.on_theme_change(cb)
            self._theme_listener = cb
        except Exception:
            # Si tu AppState no implementa esto, no fallamos.
            self._theme_listener = None

    def _unregister_theme_listener(self):
        if self._theme_listener is None:
            return
        try:
            # off_theme_change debe aceptar el mismo callable
            self.app_state.off_theme_change(self._theme_listener)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._theme_listener = None

    # --------------------
    # Build visual
    # --------------------
    def _build(self):
        colors = self.theme_ctrl.get_colors()

        # Ancho / fondo según estado
        self.width = 220 if self.expanded else 80
        self.bgcolor = colors.get("BG_COLOR", ft.colors.SURFACE)

        # Área superior: avatar / usuario
        user_area = UserIconArea(
            is_root=self.is_root,
            accent=colors.get("AVATAR_ACCENT", ft.colors.PRIMARY),
            nav_width=self.width,
            expanded=self.expanded,
        )

        # Acceso rápido (Ej. Empleados)
        quick_area = QuickNavArea(
            expanded=self.expanded,
            bg=colors.get("BTN_BG", ft.colors.SURFACE_VARIANT),
            fg=colors.get("FG_COLOR", ft.colors.BLACK),
            on_employees=lambda e: self._go_empleados(),
            mostrar_empleados=True,
        )

        # Menú principal
        menu_area = MenuButtonsArea(
            expanded=self.expanded,
            dark=self.dark,
            on_toggle_nav=None,     # compatibilidad
            on_toggle_theme=None,
            on_exit=None,
            bg=colors.get("BTN_BG", ft.colors.SURFACE_VARIANT),
        )

        # Stack superior (contenido dinámico)
        top_stack = ft.Column(
            controls=[
                user_area,
                quick_area,
                ft.Divider(color=colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)),
                menu_area,
            ],
            spacing=8,
            expand=True,
        )

        # Controles inferiores (expandir / tema / salir)
        control_area = ControlButtonsArea(
            expanded=self.expanded,
            dark=self.dark,
            on_toggle_nav=self.toggle_nav,
            on_toggle_theme=self.toggle_theme,
            on_settings=None,
            on_exit=self.exit_app,
            bg=colors.get("BTN_BG", ft.colors.SURFACE_VARIANT),
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
        page = self.app_state.page
        if page:
            page.go("/trabajadores")

    # --------------------
    # Eventos de tema
    # --------------------
    def _apply_current_palette(self):
        """Aplica el fondo actual de la paleta y sincroniza bandera dark."""
        colors = self.theme_ctrl.get_colors()
        self.dark = self.theme_ctrl.is_dark()
        self.bgcolor = colors.get("BG_COLOR", self.bgcolor)

    def _on_theme_changed(self):
        """Callback llamado por AppState cuando cambia el tema global."""
        # Relee paleta y reconstruye con los colores correctos
        self._apply_current_palette()
        self._build()
        self._safe_update()

    # --------------------
    # Callbacks
    # --------------------
    def toggle_nav(self, e=None):
        """Expande o contrae la barra lateral."""
        self.layout_ctrl.toggle()
        self.expanded = self.layout_ctrl.is_expanded()
        self._build()
        self._safe_update()

    def toggle_theme(self, e=None):
        """
        Alterna el tema global.
        NOTA: no forzamos rebuild aquí; el listener _on_theme_changed lo hará,
        evitando condiciones de carrera y actualizaciones dobles.
        """
        self.theme_ctrl.toggle()

    def exit_app(self, e=None):
        """Cierra sesión y la ventana principal."""
        page = self.app_state.page
        if not page:
            return
        # Limpia sesión
        try:
            page.client_storage.remove("app.user")
        except Exception:
            pass

        self.layout_ctrl.set(False)
        try:
            self.theme_ctrl.apply_theme()
        except Exception:
            pass

        try:
            page.window_close()
        except Exception:
            pass

    # --------------------
    # Utilidades
    # --------------------
    def _safe_update(self):
        """
        Actualiza de forma segura: solo cuando el control ya fue agregado a la Page.
        Evitamos forzar page.update() desde aquí para no provocar renders globales.
        """
        if getattr(self, "page", None) is None:
            return
        try:
            self.update()
        except AssertionError:
            # Si por alguna razón aún no está montado, no forzamos nada.
            pass

