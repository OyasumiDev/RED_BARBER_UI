from __future__ import annotations
import flet as ft
from typing import Callable, Optional, Set

from app.config.application.app_state import AppState


class LayoutController:
    """
    Controlador global para manejar el estado expandido/colapsado de la barra lateral.
    - Patrón singleton global (una sola instancia).
    - Permite agregar/remover listeners (NavBar, paneles, etc.).
    - Persiste el estado en client_storage.
    - Auto-repara listeners al remontar vistas.
    """

    _instance: Optional[LayoutController] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._expanded: bool = False
        self._listeners: Set[Callable[[bool], None]] = set()
        self._storage_key = "ui.nav.expanded"
        self._app = AppState()

        self._hydrate()
        print(f"[LayoutController] 💾 Hidratado desde storage → expanded={self._expanded}")

    # ======================================================
    # Estado persistente
    # ======================================================
    def _hydrate(self):
        """Carga el estado expandido desde client_storage."""
        try:
            page = self._app.get_page()
            if page:
                stored = page.client_storage.get(self._storage_key)
                if isinstance(stored, bool):
                    self._expanded = stored
        except Exception:
            pass

    def _persist(self):
        """Guarda el estado actual en client_storage."""
        try:
            page = self._app.get_page()
            if page:
                page.client_storage.set(self._storage_key, self._expanded)
        except Exception:
            pass

    # ======================================================
    # Listeners
    # ======================================================
    def _register(self, callback: Callable[[bool], None], *, label: str) -> bool:
        """Registra un listener si no existe. Retorna True si lo añadió."""
        if callback in self._listeners:
            return False
        self._listeners.add(callback)
        print(f"[LayoutController] {label} ({len(self._listeners)} total).")
        return True

    def add_listener(self, callback: Callable[[bool], None]) -> bool:
        """Agrega un listener, evitando duplicados. Retorna True si lo agregó."""
        return self._register(callback, label="👂 Listener agregado")

    def remove_listener(self, callback: Callable[[bool], None]) -> bool:
        """Elimina un listener registrado. Retorna True si lo eliminó."""
        if callback in self._listeners:
            self._listeners.remove(callback)
            print(f"[LayoutController] 🗑️ Listener eliminado ({len(self._listeners)} restantes).")
            return True
        return False

    def ensure_listener(self, callback: Callable[[bool], None]) -> bool:
        """Asegura que el listener esté registrado incluso tras remount. Retorna True si lo agregó."""
        return self._register(callback, label="✅ Listener restaurado")

    def notify_listeners(self):
        """Notifica a todos los listeners del cambio de estado."""
        print(f"[LayoutController] 🔔 Notificando {len(self._listeners)} listeners → expanded={self._expanded}")
        for cb in list(self._listeners):
            try:
                cb(self._expanded)
            except Exception as e:
                print(f"[LayoutController] ⚠️ Listener inválido eliminado: {e}")
                self._listeners.discard(cb)

    # ======================================================
    # API pública
    # ======================================================
    def toggle(self, persist: bool = True):
        """Alterna el estado expandido y notifica."""
        self._expanded = not self._expanded
        print(f"[LayoutController] 🔘 Toggle solicitado → expanded={self._expanded}")
        if persist:
            self._persist()
        self.notify_listeners()

    def set_state(self, expanded: bool, persist: bool = True):
        """Cambia el estado expandido explícitamente."""
        self._expanded = bool(expanded)
        if persist:
            self._persist()
        self.notify_listeners()

    def is_expanded(self) -> bool:
        """Devuelve el estado expandido actual."""
        return self._expanded

    def width(self, expanded_width: int, collapsed_width: int) -> int:
        """Calcula el ancho según el estado."""
        return expanded_width if self._expanded else collapsed_width
