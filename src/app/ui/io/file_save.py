# app/ui/io/file_save_invoker.py
from __future__ import annotations
from typing import Callable, List, Optional
import os
import flet as ft
from flet import FilePicker, FilePickerResultEvent

# Botón visual del proyecto (con fallback si no existe)
try:
    from app.ui.factory.boton_factory import boton_exportar as _boton_exportar
except Exception:  # pragma: no cover
    _boton_exportar = None


class FileSaver:
    """
    Invoker MODAL y GENÉRICO para GUARDAR archivos.
    - Abre un diálogo 'Guardar como...' y retorna la ruta elegida.
    - No hace lógica adicional: el módulo llamador decide qué guardar / cómo.

    Callbacks:
        on_save(path: str) -> None
        on_cancel() -> None                  (opcional)

    Parámetros:
        page: Page de Flet.
        save_dialog_title: título del diálogo.
        file_name: nombre sugerido.
        initial_directory: ruta inicial (opcional).
        allowed_extensions: lista de extensiones permitidas (["sql","zip"]). Si None o [], sin restricción.
        enforce_extension: si se especifica, fuerza que el archivo termine con ese sufijo (p. ej. "sql").
    """

    def __init__(
        self,
        *,
        page: ft.Page,
        on_save: Optional[Callable[[str], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        save_dialog_title: str = "Guardar archivo",
        file_name: Optional[str] = None,
        initial_directory: Optional[str] = None,
        allowed_extensions: Optional[List[str]] = None,
        enforce_extension: Optional[str] = None,
    ):
        self.page = page
        self.on_save = on_save
        self.on_cancel = on_cancel
        self.save_dialog_title = save_dialog_title
        self.file_name = file_name or "archivo"
        self.initial_directory = initial_directory or ""
        self.allowed_extensions = [ext.lower().lstrip(".") for ext in (allowed_extensions or [])]
        self.enforce_extension = (enforce_extension or "").lower().lstrip(".") or None

        self._picker = FilePicker(on_result=self._on_save_result)
        self._ensure_overlay(self._picker)

    # ---------------- Helpers ----------------
    def set_page(self, page: ft.Page):
        """Permite reinyectar la Page si cambió el contexto."""
        self.page = page
        self._ensure_overlay(self._picker)

    def set_allowed_extensions(self, exts: Optional[List[str]]):
        """Actualiza extensiones permitidas (o deja sin restricción con None/[])."""
        self.allowed_extensions = [e.lower().lstrip(".") for e in (exts or [])]

    def set_suggested_filename(self, name: str):
        self.file_name = name or self.file_name

    def _ensure_overlay(self, picker: FilePicker):
        if self.page and hasattr(self.page, "overlay") and picker not in self.page.overlay:
            self.page.overlay.append(picker)

    @staticmethod
    def _ensure_ext(path: str, ext: Optional[str]) -> str:
        if not ext:
            return path
        ext = ext.lower().lstrip(".")
        return path if path.lower().endswith("." + ext) else f"{path}.{ext}"

    @staticmethod
    def _check_allowed(path: str, allowed_exts: List[str]) -> bool:
        if not allowed_exts:
            return True
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        return ext in [e.lower().lstrip(".") for e in allowed_exts]

    # ---------------- Abrir diálogo ----------------
    def open_save(self) -> None:
        self._ensure_overlay(self._picker)
        if self.page:
            try:
                self.page.update()
            except Exception:
                pass
        self._picker.save_file(
            dialog_title=self.save_dialog_title,
            file_name=self.file_name,
            initial_directory=self.initial_directory,
            # None o [] => sin restricción (Flet admite None)
            allowed_extensions=self.allowed_extensions or None,
        )

    # ---------------- Resultado ----------------
    def _on_save_result(self, e: FilePickerResultEvent) -> None:
        # Usuario canceló
        if not e.path:
            if callable(self.on_cancel):
                try:
                    self.on_cancel()
                except Exception:
                    pass
            return

        # Ajuste de extensión si se pidió
        final_path = self._ensure_ext(
            e.path,
            self.enforce_extension or (self.allowed_extensions[0] if self.allowed_extensions else None),
        )

        # Validación suave (deja que el caller decida qué hacer si no cumple)
        _ = self._check_allowed(final_path, self.allowed_extensions)

        if callable(self.on_save):
            try:
                self.on_save(final_path)
            except Exception:
                pass

    # ---------------- Botón opcional ----------------
    def get_export_button(self, text: str = "Guardar", icon=ft.icons.SAVE):
        """Devuelve un botón que abre el diálogo; usa la factory si existe."""
        if callable(_boton_exportar):
            return _boton_exportar(lambda: self.open_save())
        return ft.ElevatedButton(text, icon=icon, on_click=lambda _: self.open_save())
