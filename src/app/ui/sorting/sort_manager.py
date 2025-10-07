# app/ui/sorting/sort_manager.py

from __future__ import annotations
import flet as ft
from typing import Callable, Dict, Optional, Tuple, List, Set


class SortManager:
    """
    Gestor de sorting (orden) por grupos, independiente de la UI.
    - Maneja estado tri-state: None -> asc (▲) -> desc (▼) -> None
    - Actualiza todos los headers del grupo para reflejar el estado activo
    - Permite callbacks por header y listeners por grupo
    - Ofrece utilidades para integrarte con SQL / filtros

    Conceptos:
      * grupo: identificador de tabla/lista (e.g., "trabajadores", "inventario")
      * campo: nombre del campo por el que se ordena (e.g., "nombre")

    Métodos clave:
      - create_header(...): crea un header clickable (GestureDetector) con '▲', '▼' o ' -'
      - get(grupo): (key, asc)  -> (str|None, bool|None)
      - set(grupo, key, asc): fija el estado programáticamente
      - clear(grupo): limpia el estado del grupo
      - on_change(grupo, callback): suscribe listener de grupo
      - off_change(grupo, callback): desuscribe
      - order_clause(grupo, map_campos): helper para obtener "ORDER BY ..." SQL
    """

    # Símbolos (puedes cambiar los strings si lo necesitas)
    ARROW_UP = " ▲"
    ARROW_DOWN = " ▼"
    ARROW_NONE = " -"

    def __init__(self) -> None:
        # Estado por grupo: {"key": Optional[str], "asc": Optional[bool]}
        self._state: Dict[str, Dict[str, Optional[object]]] = {}
        # Labels registrados por (grupo, campo)
        self._labels: Dict[Tuple[str, str], ft.Text] = {}
        # Listeners por grupo (llamados en cada cambio de estado)
        self._group_listeners: Dict[str, Set[Callable[[str, Optional[str], Optional[bool]], None]]] = {}

    # -----------------------------
    # Estado interno
    # -----------------------------
    def _ensure_group(self, grupo: str) -> Dict[str, Optional[object]]:
        if grupo not in self._state:
            self._state[grupo] = {"key": None, "asc": None}
        return self._state[grupo]

    def _suffix_for(self, active: bool, asc: Optional[bool]) -> str:
        if not active:
            return self.ARROW_NONE
        if asc is True:
            return self.ARROW_UP
        if asc is False:
            return self.ARROW_DOWN
        return self.ARROW_NONE

    def _compute_next(self, grupo: str, campo: str, tri_state: bool) -> Tuple[Optional[str], Optional[bool]]:
        st = self._ensure_group(grupo)
        if st["key"] != campo:
            return campo, True  # nuevo campo -> asc
        # mismo campo -> toggle
        if st["asc"] is True:
            return campo, False
        if st["asc"] is False:
            return (None, None) if tri_state else (campo, True)
        # None -> asc
        return campo, True

    def _notify_group(self, grupo: str) -> None:
        st = self._ensure_group(grupo)
        for cb in list(self._group_listeners.get(grupo, set())):
            try:
                cb(grupo, st["key"], st["asc"])
            except Exception:
                # no romper la UI si un listener lanza
                pass

    # -----------------------------
    # API pública de estado
    # -----------------------------
    def get(self, grupo: str) -> Tuple[Optional[str], Optional[bool]]:
        st = self._ensure_group(grupo)
        return st["key"], st["asc"]

    def set(self, grupo: str, key: Optional[str], asc: Optional[bool], *, notify: bool = True) -> None:
        self._state[grupo] = {"key": key, "asc": asc}
        # Refrescar todos los headers del grupo
        for (g, campo), txt in list(self._labels.items()):
            if g != grupo:
                continue
            active = (key == campo)
            suffix = self._suffix_for(active, asc if active else None)
            base_title = getattr(txt, "data", None) or txt.value
            # si value trae sufijo previo, recupera base desde data
            if txt.data:
                base_title = txt.data
            txt.value = f"{base_title}{suffix}"
            if txt.page:
                txt.update()
        if notify:
            self._notify_group(grupo)

    def clear(self, grupo: str, *, notify: bool = True) -> None:
        self.set(grupo, None, None, notify=notify)

    # -----------------------------
    # Suscripción por grupo
    # -----------------------------
    def on_change(self, grupo: str, callback: Callable[[str, Optional[str], Optional[bool]], None]) -> None:
        if grupo not in self._group_listeners:
            self._group_listeners[grupo] = set()
        self._group_listeners[grupo].add(callback)

    def off_change(self, grupo: str, callback: Callable[[str, Optional[str], Optional[bool]], None]) -> None:
        if grupo in self._group_listeners:
            self._group_listeners[grupo].discard(callback)

    # -----------------------------
    # Headers ordenables
    # -----------------------------
    def create_header(
        self,
        *,
        titulo: str,
        campo: str,
        grupo: str,
        width: Optional[int] = None,
        tri_state: bool = True,
        text_size: int = 12,
        weight: str = "bold",
        on_click: Optional[Callable[[str, str, Optional[bool]], None]] = None,
    ) -> ft.Control:
        """
        Crea un encabezado ordenable:
          - Muestra '▲', '▼' o ' - '
          - Cambia estado del grupo al click
          - on_click(grupo, campo|"" si None, asc)
        """
        st = self._ensure_group(grupo)
        active = (st["key"] == campo)
        suffix = self._suffix_for(active, st["asc"] if active else None)

        txt = ft.Text(f"{titulo}{suffix}", size=text_size, weight=weight)
        # Guardar el título base para recalcular valor en cada update
        txt.data = titulo
        self._labels[(grupo, campo)] = txt

        def _tap(_):
            new_key, new_asc = self._compute_next(grupo, campo, tri_state)
            self.set(grupo, new_key, new_asc)  # ya refresca y notifica listeners
            if on_click:
                on_click(grupo, new_key or "", new_asc)

        label = ft.GestureDetector(
            on_tap=_tap,
            mouse_cursor=ft.MouseCursor.CLICK,
            content=ft.Row([txt], alignment=ft.MainAxisAlignment.START, spacing=4),
        )
        return ft.Container(label, width=width) if width else label

    # -----------------------------
    # Utilidades para integración
    # -----------------------------
    @staticmethod
    def to_sql_order(grupo: str, state: Tuple[Optional[str], Optional[bool]], field_map: Dict[str, str]) -> str:
        """
        Devuelve un fragmento "ORDER BY ..." o cadena vacía.
        field_map: mapea el campo lógico a columna SQL (e.g. {"nombre": "t.nombre"})
        """
        key, asc = state
        if not key or asc is None:
            return ""
        col = field_map.get(key, key)
        return f" ORDER BY {col} {'ASC' if asc else 'DESC'} "

    def order_clause(self, grupo: str, field_map: Dict[str, str]) -> str:
        """Atajo a partir del estado interno del grupo."""
        return self.to_sql_order(grupo, self.get(grupo), field_map)

    # -----------------------------
    # Aliases de limpieza (compat)
    # -----------------------------
    def clear_sort(self, grupo: Optional[str] = None, *, notify: bool = True) -> None:
        """
        Alias de compatibilidad para limpiar el orden.
        - Si 'grupo' es None, limpia todos los grupos conocidos.
        - Si 'grupo' es un string, limpia solo ese grupo.
        """
        if grupo is None:
            # Limpiar todos los grupos que tengamos registrados (estado o labels)
            grupos = set(self._state.keys()) | {g for (g, _c) in self._labels.keys()}
            for g in grupos:
                self.clear(g, notify=notify)
        else:
            self.clear(grupo, notify=notify)

    def clear_order(self, grupo: Optional[str] = None, *, notify: bool = True) -> None:
        """Alias adicional por si en algún sitio se usa 'clear_order'."""
        self.clear_sort(grupo, notify=notify)
