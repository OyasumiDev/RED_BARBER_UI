# app/config/application/theme_controller.py
import flet as ft
from app.helpers.class_singleton import class_singleton
from app.config.application.app_state import AppState


@class_singleton
class ThemeController:
    """
    Controlador global de tema, sincronizado con AppState.
    Gestiona el modo claro/oscuro, persiste en client_storage y
    expone una paleta de colores consistente para toda la aplicación.
    """

    def __init__(self):
        self.app_state = AppState()
        self.page: ft.Page | None = None
        self.tema_oscuro: bool = False
        self._init_from_storage()

    # ---------------------------
    # Inicialización y persistencia
    # ---------------------------
    def _init_from_storage(self):
        """Inicializa el tema desde client_storage si existe."""
        self.page = self.app_state.get_page()
        stored = None
        try:
            if self.page:
                stored = self.page.client_storage.get("app.theme")
        except Exception:
            pass

        if isinstance(stored, str):
            s = stored.strip().lower()
            self.tema_oscuro = (s == "dark")
        elif isinstance(stored, bool):
            self.tema_oscuro = stored
        else:
            self.tema_oscuro = False  # default claro

        self.apply_theme()

    # ---------------------------
    # Integración con la Page
    # ---------------------------
    def attach_page(self, page: ft.Page):
        """Conecta la page principal y aplica el tema guardado."""
        self.page = page
        self.app_state.set_page(page)
        self._init_from_storage()

    # ---------------------------
    # Gestión del tema
    # ---------------------------
    def toggle(self):
        """Alterna entre oscuro y claro y guarda la preferencia global."""
        self.tema_oscuro = not self.tema_oscuro
        self._save_to_storage()
        self.apply_theme()
        # Notifica (si tu AppState implementa listeners)
        set_dark = getattr(self.app_state, "set_dark", None)
        if callable(set_dark):
            set_dark(self.tema_oscuro)

    def set_dark(self, value: bool):
        """Fuerza un modo específico (True=oscuro, False=claro)."""
        self.tema_oscuro = bool(value)
        self._save_to_storage()
        self.apply_theme()
        set_dark = getattr(self.app_state, "set_dark", None)
        if callable(set_dark):
            set_dark(self.tema_oscuro)

    def _save_to_storage(self):
        """Guarda la preferencia en client_storage y AppState."""
        if self.page:
            try:
                self.page.client_storage.set("app.theme", "dark" if self.tema_oscuro else "light")
            except Exception:
                pass
        self.app_state.set("tema_oscuro", self.tema_oscuro)

    def apply_theme(self):
        """
        Aplica el tema actual a la Page y establece el fondo de la Page con tu paleta.
        Esto evita que partes de la UI usen ‘surfaces’ por defecto y se inviertan.
        """
        if not self.page:
            return

        # 1) Modo de material (para controles que sí lo usan)
        self.page.theme_mode = ft.ThemeMode.DARK if self.tema_oscuro else ft.ThemeMode.LIGHT

        # 2) Color de fondo GLOBAL de la Page desde TU paleta
        colors = self.get_colors()
        try:
            self.page.bgcolor = colors.get("BG_COLOR")
        except Exception:
            pass

        try:
            self.page.update()
        except Exception:
            pass

    # ---------------------------
    # Paleta de colores global
    # ---------------------------
    def get_colors(self) -> dict:
        """Retorna la paleta completa de colores según el tema."""
        if self.tema_oscuro:
            return {
                "BG_COLOR": ft.colors.GREY_900,
                "FG_COLOR": ft.colors.WHITE,
                "AVATAR_ACCENT": ft.colors.GREY_800,
                "DIVIDER_COLOR": ft.colors.OUTLINE_VARIANT,
                "BTN_BG": ft.colors.GREY_800,
                "CARD_BG": ft.colors.GREY_800,
            }
        else:
            return {
                "BG_COLOR": ft.colors.GREY_50,
                "FG_COLOR": ft.colors.BLACK,
                "AVATAR_ACCENT": ft.colors.GREY_200,
                "DIVIDER_COLOR": ft.colors.OUTLINE,
                "BTN_BG": ft.colors.GREY_100,
                "CARD_BG": ft.colors.WHITE,
            }

    def get_fg_color(self) -> str:
        """Color principal de texto."""
        return self.get_colors().get("FG_COLOR", ft.colors.BLACK)

    def is_dark(self) -> bool:
        return self.tema_oscuro

    def is_white(self) -> bool:
        return not self.tema_oscuro
