# app/views/containers/nvar/layout_controller.py

from __future__ import annotations
from typing import Callable, Set
from app.helpers.class_singleton import class_singleton

# AppState puede no estar disponible en import-time en algunos contextos;
# protegemos su uso con try/except.
try:
    from app.config.application.app_state import AppState
except Exception:
    AppState = None


@class_singleton
class LayoutController:
    """
    Controlador ÚNICO del estado de la barra lateral.
    - is_expanded() -> bool
    - toggle()/set(value) con persistencia en client_storage
    - width(expanded=220, collapsed=80) -> int
    - add_listener(cb), remove_listener(cb): notifica cambios a quien lo necesite
    """
    _KEY = "ui.nav.expanded"

    def __init__(self):
        self._expanded: bool = False
        self._listeners: Set[Callable[[bool], None]] = set()

        # Cargar valor persistido si existe
        try:
            page = AppState().page if AppState else None
            if page is not None:
                stored = page.client_storage.get(self._KEY)
                if isinstance(stored, bool):
                    self._expanded = stored
        except Exception:
            pass

    # -----------------
    # Observadores
    # -----------------
    def add_listener(self, cb: Callable[[bool], None]) -> None:
        self._listeners.add(cb)

    def remove_listener(self, cb: Callable[[bool], None]) -> None:
        self._listeners.discard(cb)

    def _notify(self) -> None:
        for cb in tuple(self._listeners):
            try:
                cb(self._expanded)
            except Exception:
                pass

    # -----------------
    # API de estado
    # -----------------
    def is_expanded(self) -> bool:
        return self._expanded

    def set(self, value: bool, *, persist: bool = True) -> None:
        nv = bool(value)
        if nv == self._expanded:
            return
        self._expanded = nv
        if persist:
            try:
                page = AppState().page if AppState else None
                if page is not None:
                    page.client_storage.set(self._KEY, nv)
            except Exception:
                pass
        self._notify()

    def toggle(self, *, persist: bool = True) -> None:
        self.set(not self._expanded, persist=persist)

    def width(self, expanded: int = 220, collapsed: int = 80) -> int:
        return expanded if self._expanded else collapsed
