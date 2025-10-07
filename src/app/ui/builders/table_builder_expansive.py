# app/ui/builders/table_builder_expansive.py

from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
import uuid
import flet as ft

from app.ui.factory.boton_factory import (
    boton_aceptar, boton_cancelar, boton_editar, boton_borrar
)
from app.ui.sorting.sort_manager import SortManager
from app.ui.scroll.table_scroll_controller import ScrollTableController


CellFormatter = Callable[[Any, Dict[str, Any]], ft.Control]
DetailBuilder = Callable[[Dict[str, Any]], ft.Control]


class TableBuilderExpansive:
    """
    Tabla expansiva (por fila) con sorting independiente, scroll H/V y auto-scroll a nuevas filas.

    - Header con SortManager (por instancia, group único).
    - Fila -> ExpansionTile con título (celdas) y detalle (detail_builder).
    - Columna de acciones con BotonFactory.
    - Estado de expansión persistente por 'row_id_key' (recomendado).
    - Auto-scroll al nuevo registro (_is_new=True) si hay ScrollTableController adjunto.

    Columns: lista de dicts
      - key (str)                  -> nombre del campo en la fila
      - title (str)                -> cabecera
      - width (int|None)          -> ancho fijo sugerido (para layout consistente)
      - formatter (CellFormatter) -> opcional: value,row -> Control
    """

    def __init__(
        self,
        *,
        # Sorting
        sort_manager: Optional[SortManager] = None,
        group: Optional[str] = None,
        # Estructura
        columns: List[Dict[str, Any]],
        row_id_key: Optional[str] = None,           # clave estable (ej. "id_trabajador") para preservar expansión
        detail_builder: Optional[DetailBuilder] = None,  # contenido al expandir (si None, no muestra contenido)
        # Callbacks acciones de fila
        on_sort_change: Optional[Callable[[str, str, Optional[bool]], None]] = None,
        on_accept: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_cancel: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_edit: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_delete: Optional[Callable[[Dict[str, Any]], None]] = None,
        # Apariencia / métricas
        header_height: int = 44,
        row_height: int = 48,
        actions_title: str = "Acciones",
        actions_width: Optional[int] = 140,
        dense_text: bool = True,
        # Scroll
        scroll_controller: Optional[ScrollTableController] = None,
        auto_scroll_new: bool = True,
        auto_scroll_target: str = "last",   # "last" | "first"
        auto_scroll_margin_top: int = 8,
    ) -> None:
        # Sorting (independiente por instancia)
        self.sort = sort_manager or SortManager()
        self.group = group or f"exp_table_{uuid.uuid4().hex[:8]}"
        self.on_sort_change = on_sort_change

        # Estructura
        self.columns = columns
        self.row_id_key = row_id_key
        self.detail_builder = detail_builder

        # Acciones
        self.on_accept = on_accept
        self.on_cancel = on_cancel
        self.on_edit = on_edit
        self.on_delete = on_delete

        # Apariencia / métricas
        self._header_height = max(0, int(header_height))
        self._row_height = max(1, int(row_height))
        self.actions_title = actions_title
        self.actions_width = actions_width
        self._text_size = 12 if dense_text else 14

        # Scroll
        self._stc: Optional[ScrollTableController] = scroll_controller
        self._auto_scroll_new = auto_scroll_new
        self._auto_scroll_target = auto_scroll_target
        self._auto_scroll_margin_top = auto_scroll_margin_top

        # Estado
        self._rows: List[Dict[str, Any]] = []
        self._expanded_keys: set = set()      # keys expandidas (por row_id_key)
        self._root: Optional[ft.Column] = None
        self._rows_container: Optional[ft.Column] = None  # lista de ExpansionTiles

        # Wiring: mantener expansión al resortear
        # Si no hay callback externo de sort, aplicamos sort en memoria
        self.sort.on_change(self.group, self._on_sort_change_internal)

    # -----------------------------
    # Integración con Scroll Controller
    # -----------------------------
    def attach_scroll_controller(self, stc: ScrollTableController) -> None:
        self._stc = stc
        self._stc.attach_table_metrics(
            heading_height=self._header_height,
            row_height=self._row_height,
        )

    # -----------------------------
    # Construcción
    # -----------------------------
    def build(self) -> ft.Control:
        """Devuelve el control raíz (header + filas expansivas)."""
        header = self._build_header_row()
        self._rows_container = ft.Column(spacing=0)  # lista de tiles
        self._root = ft.Column([header, self._rows_container], spacing=8)
        self._rebuild_rows()
        # Ajustar métricas al STC si está adjunto
        if self._stc:
            self._stc.attach_table_metrics(
                heading_height=self._header_height,
                row_height=self._row_height,
            )
        return self._root

    def _build_header_row(self) -> ft.Control:
        """Crea una 'fila' de header con sort headers + label de acciones."""
        header_cells: List[ft.Control] = []
        for col in self.columns:
            title = col["title"]
            key = col["key"]
            width = col.get("width")
            hdr = self.sort.create_header(
                titulo=title,
                campo=key,
                grupo=self.group,
                width=width,
                text_size=self._text_size,
                on_click=self.on_sort_change  # la vista puede interceptar y recargar
            )
            header_cells.append(hdr)

        # Acciones
        actions_label = ft.Container(
            ft.Text(self.actions_title, size=self._text_size, weight="bold"),
            width=self.actions_width,
        ) if self.actions_width else ft.Text(self.actions_title, size=self._text_size, weight="bold")

        header_cells.append(actions_label)

        # Header como Row de ancho variable (h-scroll lo da el STC externo)
        header_row = ft.Container(
            ft.Row(header_cells, alignment=ft.MainAxisAlignment.START, spacing=16),
            height=self._header_height,
            alignment=ft.alignment.center_left,
        )
        return header_row

    # -----------------------------
    # Render filas expansivas
    # -----------------------------
    def _make_title_row(self, row: Dict[str, Any]) -> ft.Control:
        """Construye la 'fila' visual (celdas) que se ve cuando NO está expandida."""
        cells: List[ft.Control] = []
        for col in self.columns:
            key = col["key"]
            width = col.get("width")
            fmt: Optional[CellFormatter] = col.get("formatter")
            value = row.get(key)
            ctrl = fmt(value, row) if fmt else ft.Text("" if value is None else str(value), size=self._text_size)
            cell = ft.Container(ctrl, width=width, alignment=ft.alignment.center_left)
            cells.append(cell)

        # acciones (en trailing del tile; aquí sólo reservamos espacio visual si quieres)
        if self.actions_width:
            cells.append(ft.Container(width=self.actions_width))
        return ft.Row(cells, alignment=ft.MainAxisAlignment.START, spacing=16)

    def _actions_trailing(self, row: Dict[str, Any]) -> ft.Control:
        is_new = bool(row.get("_is_new", False))
        if is_new:
            content = ft.Row(
                [
                    boton_aceptar(lambda e, r=row: self.on_accept and self.on_accept(r)),
                    boton_cancelar(lambda e, r=row: self.on_cancel and self.on_cancel(r)),
                ],
                spacing=4,
            )
        else:
            content = ft.Row(
                [
                    boton_editar(lambda e, r=row: self.on_edit and self.on_edit(r)),
                    boton_borrar(lambda e, r=row: self.on_delete and self.on_delete(r)),
                ],
                spacing=4,
            )
        return ft.Container(content, width=self.actions_width, alignment=ft.alignment.center_right)

    def _row_key(self, row: Dict[str, Any], idx: int) -> str:
        if self.row_id_key and self.row_id_key in row:
            return f"key:{row[self.row_id_key]}"
        # fallback por índice: no sobrevivirá a resorting si cambian índices
        return f"idx:{idx}"

    def _build_one_tile(self, row: Dict[str, Any], idx: int) -> ft.ExpansionTile:
        title_row = self._make_title_row(row)
        trailing = self._actions_trailing(row)
        rkey = self._row_key(row, idx)
        initially_expanded = (rkey in self._expanded_keys)

        # Nota: Flet 0.23.0 soporta on_change con e.data == "true"/"false"
        def _on_change(e: ft.ControlEvent):
            expanded = (str(e.data).lower() == "true")
            if expanded:
                self._expanded_keys.add(rkey)
            else:
                self._expanded_keys.discard(rkey)

        tile = ft.ExpansionTile(
            title=title_row,
            trailing=trailing,
            initially_expanded=initially_expanded,
            maintain_state=True,  # evita perder estado interno del detalle
            on_change=_on_change,
            controls=[self.detail_builder(row)] if self.detail_builder else [],  # contenido expandido
        )
        return tile

    def _rebuild_rows(self) -> None:
        tiles = [self._build_one_tile(r, i) for i, r in enumerate(self._rows)]
        if self._rows_container:
            self._rows_container.controls = tiles
            if self._rows_container.page:
                self._rows_container.update()

    # -----------------------------
    # API de datos
    # -----------------------------
    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        """
        Establece filas. Si no hay callback externo de sort, aplica sort en memoria usando SortManager.
        Conserva estado de expansión por 'row_id_key'. Si no hay row_id_key, la expansión por índice
        podría perderse al resortear.
        """
        rows = rows or []
        self._rows = self._apply_sort_if_needed(rows)
        self._rebuild_rows()

        # Auto-scroll a nuevas filas
        if self._stc and self._auto_scroll_new:
            self._auto_scroll_to_new()

    def refresh(self) -> None:
        self._rebuild_rows()

    # -----------------------------
    # Sorting
    # -----------------------------
    def _on_sort_change_internal(self, grupo: str, key: Optional[str], asc: Optional[bool]) -> None:
        """
        Listener del SortManager de esta instancia.
        - Si hay callback externo -> se delega (la vista puede reconsultar DB).
        - Si no, se aplica sort en memoria y se mantiene expansión.
        """
        if self.on_sort_change:
            # vista se encarga de recargar/ordenar y luego llamar set_rows()
            self.on_sort_change(grupo, key or "", asc)
            return

        # sort en memoria (simple): claves ausentes -> ""
        self._rows = self._apply_sort_now(self._rows, key, asc)
        self._rebuild_rows()

    def _apply_sort_if_needed(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        key, asc = self.sort.get(self.group)
        return self._apply_sort_now(rows, key, asc)

    @staticmethod
    def _safe_key(row: Dict[str, Any], k: Optional[str]) -> Any:
        if not k:
            return 0
        v = row.get(k, "")
        # normalizar tipos distintos
        try:
            return (v is None, str(v).lower())
        except Exception:
            return (v is None, v)

    def _apply_sort_now(self, rows: List[Dict[str, Any]], key: Optional[str], asc: Optional[bool]) -> List[Dict[str, Any]]:
        if not key or asc is None:
            return rows
        try:
            return sorted(rows, key=lambda r: self._safe_key(r, key), reverse=(asc is False))
        except Exception:
            return rows

    # -----------------------------
    # Auto-scroll a nuevas filas
    # -----------------------------
    def _auto_scroll_to_new(self) -> None:
        indices = [i for i, r in enumerate(self._rows) if r.get("_is_new") is True]
        if not indices:
            return
        idx = indices[-1] if self._auto_scroll_target == "last" else indices[0]
        try:
            self._stc.scroll_to_row_index(idx, margin_top=self._auto_scroll_margin_top)  # type: ignore[union-attr]
        except Exception:
            self._stc.scroll_to_new_record()  # type: ignore[union-attr]
