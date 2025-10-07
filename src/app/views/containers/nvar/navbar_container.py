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

        # Flag de montaje para evitar AssertionError al updatear
        self._mounted = False

        # Construcción inicial
        self._build()

        # Escucha global del cambio de tema (para actualizar colores automáticamente)
        self.theme_ctrl.app_state.on_theme_change(self._on_theme_changed)

    # --------------------
    # Ciclo de vida
    # --------------------
    def did_mount(self):
        """Se llama automáticamente cuando el control se monta en la Page."""
        self._mounted = True
        try:
            self.theme_ctrl.apply_theme()
        except Exception:
            pass
        self._safe_update()

    def will_unmount(self):
        """Se llama automáticamente al desmontarse del árbol."""
        self._mounted = False
        self.theme_ctrl.app_state.off_theme_change(self._on_theme_changed)

    def _safe_update(self):
        """Actualiza la Page solo si ya está montado."""
        p = getattr(self, "page", None)
        if p is not None:
            try:
                p.update()
            except AssertionError:
                pass

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
    def _on_theme_changed(self):
        """Callback llamado por AppState cuando cambia el tema global."""
        self.dark = self.theme_ctrl.is_dark()
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
        """Alterna el tema y lo propaga globalmente."""
        self.theme_ctrl.toggle()
        self.dark = self.theme_ctrl.is_dark()
        try:
            self.theme_ctrl.apply_theme()
        except Exception:
            pass
        self._build()
        self._safe_update()

    def exit_app(self, e=None):
        """Cierra sesión y la ventana principal."""
        page = self.app_state.page
        if not page:
            return
        # Limpia sesión y restablece estados
        try:
            page.client_storage.remove("app.user")
        except Exception:
            pass

        self.layout_ctrl.set(False)
        try:
            self.theme_ctrl.apply_theme()
        except Exception:
            pass

        # Cierra la app
        try:
            page.window_close()
        except Exception:
            pass
