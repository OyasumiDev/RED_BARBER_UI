# app/views/containers/nvar/layout_controller.py
from __future__ import annotations
from typing import Callable, Set, Optional
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

    - Persistencia en client_storage (clave: 'ui.nav.expanded')
    - Hidratación inicial desde Page (si existe) con heurística responsive
    - Listeners para reaccionar a cambios
    - Opción de auto-actualizar la Page tras cada cambio

    API:
      - attach(auto_update=True, fire_immediately=False, default_collapsed_on_small=True, small_breakpoint=1024)
      - is_expanded() -> bool
      - set(value: bool, persist=True) -> None
      - toggle(persist=True) -> None
      - width(expanded=220, collapsed=80) -> int
      - add_listener(cb, fire_immediately=False) / remove_listener(cb)
    """

    _KEY = "ui.nav.expanded"

    def __init__(self):
        self._expanded: bool = False
        self._listeners: Set[Callable[[bool], None]] = set()
        self._hydrated: bool = False
        self._auto_update: bool = True  # se puede cambiar en attach()

        # Intento de lectura temprana (si Page ya existe)
        try:
            page = AppState().page if AppState else None
            if page is not None:
                stored = page.client_storage.get(self._KEY)
                if isinstance(stored, bool):
                    self._expanded = stored
                    self._hydrated = True
        except Exception:
            # se hidratará más tarde en attach()
            pass

    # -----------------
    # Integración con Page / Hidratación
    # -----------------
    def attach(
        self,
        *,
        auto_update: bool = True,
        fire_immediately: bool = False,
        default_collapsed_on_small: bool = True,
        small_breakpoint: int = 1024,
    ) -> None:
        """
        Conecta con la Page (vía AppState), hidrata desde client_storage si procede
        y define comportamiento de auto-actualización de Page en cambios.
        """
        self._auto_update = bool(auto_update)

        if self._hydrated:
            # Ya hidratado (quizá por __init__), solo opcionalmente dispara listeners
            if fire_immediately:
                self._notify()
            return

        try:
            page = AppState().page if AppState else None
            if page is None:
                # Sin Page aún; se hidratará en la próxima llamada a attach()
                return

            stored = page.client_storage.get(self._KEY)
            if isinstance(stored, bool):
                self._expanded = stored
            else:
                # Heurística responsive para primer arranque si no hay persistencia
                if default_collapsed_on_small and hasattr(page, "window_width"):
                    ww = int(getattr(page, "window_width", 0) or 0)
                    self._expanded = ww >= int(small_breakpoint)
                else:
                    self._expanded = True  # por defecto expandido

            self._hydrated = True

            if fire_immediately:
                self._notify()

        except Exception:
            # Evitamos romper si algo falla: quedamos con default y sin hidratar.
            self._hydrated = True

    # -----------------
    # Observadores
    # -----------------
    def add_listener(self, cb: Callable[[bool], None], fire_immediately: bool = False) -> None:
        """Suscribe un callback; si fire_immediately=True, lo llama con el estado actual."""
        if cb:
            self._listeners.add(cb)
            if fire_immediately:
                try:
                    cb(self._expanded)
                except Exception:
                    pass

    def remove_listener(self, cb: Callable[[bool], None]) -> None:
        self._listeners.discard(cb)

    def _notify(self) -> None:
        for cb in tuple(self._listeners):
            try:
                cb(self._expanded)
            except Exception:
                # Nunca dejar que un listener rompa la notificación global
                pass

        # Auto update de Page si está habilitado
        if self._auto_update:
            try:
                page = AppState().page if AppState else None
                if page is not None:
                    page.update()
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
        """Devuelve el ancho recomendado según el estado actual."""
        return int(expanded) if self._expanded else int(collapsed)
