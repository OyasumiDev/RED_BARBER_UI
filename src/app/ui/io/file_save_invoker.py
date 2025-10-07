# app/ui/io/file_save_invoker.py

from __future__ import annotations
from typing import Callable, List, Optional
import flet as ft
from flet import FilePicker, FilePickerResultEvent

from app.ui.factory.boton_factory import boton_exportar
from app.config.db.database_mysql import DatabaseMysql


class FileSaveInvoker:
    """
    Invoker para EXPORTAR archivos.
    - Usa FilePicker.save_file
    - Botón visual tomado de BotonFactory: boton_exportar(...)
    """

    def __init__(
        self,
        *,
        page: ft.Page,
        on_save: Optional[Callable[[str], None]] = None,
        save_dialog_title: str = "Exportar archivo",
        file_name: Optional[str] = None,
        initial_directory: Optional[str] = None,
        allowed_extensions: Optional[List[str]] = None,
    ):
        self.page = page
        self.on_save = on_save
        self.save_dialog_title = save_dialog_title
        self.file_name = file_name or "export.csv"
        self.initial_directory = initial_directory or ""
        self.allowed_extensions = [ext.lower().lstrip(".") for ext in (allowed_extensions or [])]

        self.db = DatabaseMysql()
        self.save_picker = FilePicker(on_result=self._on_save_result)
        self._ensure_overlay(self.save_picker)

    def _ensure_overlay(self, picker: FilePicker) -> None:
        if self.page and hasattr(self.page, "overlay") and picker not in self.page.overlay:
            self.page.overlay.append(picker)

    def open_save(self) -> None:
        self._ensure_overlay(self.save_picker)
        if self.page:
            self.page.update()
        self.save_picker.save_file(
            dialog_title=self.save_dialog_title,
            file_name=self.file_name,
            initial_directory=self.initial_directory,
            allowed_extensions=self.allowed_extensions,
        )

    def _on_save_result(self, e: FilePickerResultEvent) -> None:
        if not e.path:
            return
        # Si usas export DB:
        success = self.db.exportar_base_datos(e.path)
        msg = "✅ Exportado correctamente." if success else "⚠️ No se pudo exportar."
        if self.page:
            self.page.snack_bar = ft.SnackBar(ft.Text(msg))
            self.page.snack_bar.open = True
            self.page.update()
        if success and self.on_save:
            self.on_save(e.path)

    def get_export_button(self):
        return boton_exportar(lambda: self.open_save())
