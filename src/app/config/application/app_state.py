# app/config/application/app_state.py

import flet as ft
from app.helpers.class_singleton import class_singleton


@class_singleton
class AppState:
    """
    Estado global de la aplicación.
    Gestiona la referencia a la Page, variables globales y
    modo responsivo (desktop / tablet / mobile).
    """

    def __init__(self):
        self.page: ft.Page | None = None
        self.data: dict = {}
        self.window_width: int = 0
        self.window_height: int = 0
        self.responsive_mode: str = "desktop"  # desktop / tablet / mobile

    # ---------------------------
    # Manejo de Page
    # ---------------------------
    def set_page(self, page: ft.Page):
        """
        Establece la instancia principal de la Page y actualiza dimensiones.
        """
        self.page = page
        if page:
            self.update_dimensions(page.window_width, page.window_height)

    def get_page(self) -> ft.Page | None:
        """
        Obtiene la instancia principal de la Page.
        """
        return self.page

    # ---------------------------
    # Dimensiones y responsive
    # ---------------------------
    def update_dimensions(self, width: int, height: int):
        """
        Actualiza las dimensiones y recalcula el modo responsive.
        """
        self.window_width = width
        self.window_height = height

        if width < 600:
            self.responsive_mode = "mobile"
        elif width < 1024:
            self.responsive_mode = "tablet"
        else:
            self.responsive_mode = "desktop"

    def get_responsive_mode(self) -> str:
        """
        Devuelve el modo responsive actual.
        """
        return self.responsive_mode

    # ---------------------------
    # Almacenamiento de datos
    # ---------------------------
    def set(self, key, value):
        """
        Establece un valor en el estado global.
        """
        self.data[key] = value

    def get(self, key, default=None):
        """
        Obtiene un valor del estado global.
        """
        return self.data.get(key, default)

    # ---------------------------
    # Integración con client_storage
    # ---------------------------
    def set_client_value(self, key: str, value):
        """
        Guarda un valor en client_storage si la Page existe.
        """
        self.set(key, value)
        if self.page:
            self.page.client_storage.set(key, value)

    def get_client_value(self, key: str, default=None):
        """
        Obtiene un valor de client_storage si existe.
        """
        if self.page:
            value = self.page.client_storage.get(key)
            return value if value is not None else default
        return self.get(key, default)
