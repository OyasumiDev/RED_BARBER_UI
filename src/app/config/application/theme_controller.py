# app/config/application/theme_controller.py

import flet as ft
from app.helpers.class_singleton import class_singleton


@class_singleton
class ThemeController:
    """
    Controlador central del tema de la aplicación.
    Usa client_storage para persistencia y expone colores consistentes.
    """

    def __init__(self):
        self.page: ft.Page | None = None
        self.tema_oscuro: bool = False  # default hasta adjuntar page

    # ---------------------------
    # Integración con la Page
    # ---------------------------
    def attach_page(self, page: ft.Page):
        """
        Conecta la page real (cuando ya existe en WindowMain),
        lee la preferencia almacenada y aplica el tema inmediatamente.
        """
        self.page = page

        stored = self.page.client_storage.get("tema_oscuro")
        if stored is None:
            self.tema_oscuro = False
            self.page.client_storage.set("tema_oscuro", False)
        else:
            self.tema_oscuro = bool(stored)

        self.apply_theme()

    # ---------------------------
    # Gestión de tema
    # ---------------------------
    def toggle(self):
        """Alterna explícitamente entre oscuro y claro y guarda la preferencia."""
        if not self.page:
            return

        self.tema_oscuro = not self.tema_oscuro
        self.page.client_storage.set("tema_oscuro", self.tema_oscuro)
        self.apply_theme()

    def apply_theme(self):
        """Aplica el tema actual de manera explícita en la page."""
        if not self.page:
            return

        self.page.theme_mode = (
            ft.ThemeMode.DARK if self.tema_oscuro else ft.ThemeMode.LIGHT
        )

        try:
            self.page.update()
        except Exception:
            pass

    # ---------------------------
    # Utilidades de colores
    # ---------------------------
    def get_colors(self) -> dict:
        """Retorna de forma explícita los colores de cada modo."""
        if self.tema_oscuro:
            return {
                "BG_COLOR": ft.colors.BLACK,
                "FG_COLOR": ft.colors.WHITE,
                "AVATAR_ACCENT": ft.colors.GREY_900,
                "DIVIDER_COLOR": ft.colors.GREY_800,
                "BTN_BG": ft.colors.GREY_700,
            }
        else:
            return {
                "BG_COLOR": ft.colors.WHITE,
                "FG_COLOR": ft.colors.BLACK,
                "AVATAR_ACCENT": ft.colors.GREY_100,
                "DIVIDER_COLOR": ft.colors.GREY_300,
                "BTN_BG": ft.colors.GREY_200,
            }

    def get_fg_color(self) -> str:
        """Devuelve explícitamente solo el color de texto principal."""
        return self.get_colors()["FG_COLOR"]

    def is_dark(self) -> bool:
        """True si el tema actual es oscuro."""
        return self.tema_oscuro

    def is_white(self) -> bool:
        """True si el tema actual es claro (blanco)."""
        return not self.tema_oscuro
