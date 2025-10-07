# app/ui/io/file_open_invoker.py

from __future__ import annotations
from typing import Callable, List, Optional
import flet as ft
from flet import FilePicker, FilePickerResultEvent

from app.ui.factory.boton_factory import boton_importar


class FileOpenInvoker:
    """
    Invoker para IMPORTAR archivos.
    - Usa FilePicker.pick_files
    - Botón visual tomado de BotonFactory: boton_importar(...)
    """

    def __init__(
        self,
        *,
        page: ft.Page,
        on_select: Callable[[str], None],
        dialog_title: str = "Importar archivo",
        allowed_extensions: Optional[List[str]] = None,
    ):
        self.page = page
        self.on_select = on_select
        self.dialog_title = dialog_title
        self.allowed_extensions = [ext.lower().lstrip(".") for ext in (allowed_extensions or [])]

        self.picker = FilePicker(on_result=self._on_result)
        self._ensure_overlay(self.picker)

    # -----------------------
    # Overlay helper
    # -----------------------
    def _ensure_overlay(self, picker: FilePicker) -> None:
        if self.page and hasattr(self.page, "overlay") and picker not in self.page.overlay:
            self.page.overlay.append(picker)

    # -----------------------
    # Abrir diálogo
    # -----------------------
    def open(self) -> None:
        self._ensure_overlay(self.picker)
        if self.page:
            self.page.update()
        self.picker.pick_files(
            dialog_title=self.dialog_title,
            allow_multiple=False,
            allowed_extensions=self.allowed_extensions,
        )

    # -----------------------
    # Resultado selección
    # -----------------------
    def _on_result(self, e: FilePickerResultEvent) -> None:
        if not e.files:
            return
        selected_path = e.files[0].path
        if self.on_select:
            self.on_select(selected_path)

    # -----------------------
    # Botón (BotonFactory)
    # -----------------------
    def get_import_button(self):
        """
        Devuelve el botón 'Importar' (pill) de tu BotonFactory.
        """
        return boton_importar(lambda: self.open())
