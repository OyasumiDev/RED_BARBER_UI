# app/ui/io/file_open_invoker.py
from __future__ import annotations
from typing import Callable, List, Optional
import flet as ft
from flet import FilePicker, FilePickerResultEvent

# Botón visual del proyecto (con fallback si no existe)
try:
    from app.ui.factory.boton_factory import boton_importar as _boton_importar
except Exception:  # pragma: no cover
    _boton_importar = None


class FileOpener:
    """
    Invoker MODAL y GENÉRICO para SELECCIONAR archivos.
    - Abre diálogo de selección y retorna las rutas elegidas.
    - Sin lógica adicional: el módulo llamador maneja qué y cómo importar/abrir.

    Callbacks:
        on_select(path: str) -> None           (para selección simple)
        on_select_many(paths: List[str]) -> None  (para selección múltiple)
        on_cancel() -> None                    (opcional)

    Parámetros:
        page: Page de Flet.
        dialog_title: título del diálogo.
        allowed_extensions: lista de extensiones permitidas (["sql","zip"]). Si None o [], sin restricción.
        allow_multiple: habilita selección múltiple.
    """

    def __init__(
        self,
        *,
        page: ft.Page,
        on_select: Optional[Callable[[str], None]] = None,
        on_select_many: Optional[Callable[[List[str]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        dialog_title: str = "Seleccionar archivo",
        allowed_extensions: Optional[List[str]] = None,
        allow_multiple: bool = False,
    ):
        self.page = page
        self.on_select = on_select
        self.on_select_many = on_select_many
        self.on_cancel = on_cancel
        self.dialog_title = dialog_title
        self.allowed_extensions = [ext.lower().lstrip(".") for ext in (allowed_extensions or [])]
        self.allow_multiple = bool(allow_multiple)

        self._picker = FilePicker(on_result=self._on_result)
        self._ensure_overlay(self._picker)

    # ---------------- Helpers ----------------
    def set_page(self, page: ft.Page):
        """Permite reinyectar la Page si cambió el contexto."""
        self.page = page
        self._ensure_overlay(self._picker)

    def set_allowed_extensions(self, exts: Optional[List[str]]):
        """Actualiza extensiones permitidas (o deja sin restricción con None/[])."""
        self.allowed_extensions = [e.lower().lstrip(".") for e in (exts or [])]

    def set_allow_multiple(self, allow: bool = True):
        self.allow_multiple = bool(allow)

    def _ensure_overlay(self, picker: FilePicker):
        if self.page and hasattr(self.page, "overlay") and picker not in self.page.overlay:
            self.page.overlay.append(picker)

    # ---------------- Abrir diálogo ----------------
    def open(self) -> None:
        self._ensure_overlay(self._picker)
        if self.page:
            try:
                self.page.update()
            except Exception:
                pass
        self._picker.pick_files(
            dialog_title=self.dialog_title,
            allow_multiple=self.allow_multiple,
            # None o [] => sin restricción (Flet admite None)
            allowed_extensions=self.allowed_extensions or None,
        )

    # ---------------- Resultado ----------------
    def _on_result(self, e: FilePickerResultEvent) -> None:
        # Usuario canceló
        if not e.files:
            if callable(self.on_cancel):
                try:
                    self.on_cancel()
                except Exception:
                    pass
            return

        paths = [f.path for f in e.files if f and getattr(f, "path", None)]
        if not paths:
            if callable(self.on_cancel):
                try:
                    self.on_cancel()
                except Exception:
                    pass
            return

        if self.allow_multiple and callable(self.on_select_many):
            try:
                self.on_select_many(paths)
            except Exception:
                pass
            return

        # Compatibilidad: si no hay on_select_many, enviamos el primero por on_select
        if callable(self.on_select):
            try:
                self.on_select(paths[0])
            except Exception:
                pass

    # ---------------- Botón opcional ----------------
    def get_import_button(self, text: str = "Abrir", icon=ft.icons.FILE_OPEN):
        """Devuelve un botón que abre el diálogo; usa la factory si existe."""
        if callable(_boton_importar):
            return _boton_importar(lambda: self.open())
        return ft.ElevatedButton(text, icon=icon, on_click=lambda _: self.open())
