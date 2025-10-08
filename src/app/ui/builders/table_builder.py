# app/ui/builders/table_builder.py
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
import flet as ft

# BotonFactory (acciones de fila)
from app.ui.factory.boton_factory import (
    boton_aceptar, boton_cancelar, boton_editar, boton_borrar
)

# SortManager
from app.ui.sorting.sort_manager import SortManager

# Scroll controller
from app.ui.scroll.table_scroll_controller import ScrollTableController

ColumnFormatter = Callable[[Any, Dict[str, Any]], ft.Control]
ActionsBuilder = Callable[[Dict[str, Any], bool], ft.Control]


class TableBuilder:
    """
    TableBuilder v2 (compat con tu Flet):
    - DataTable + SortManager + BotonFactory
    - Scroll automático a nuevas filas
    - Header opcional vía build_view()
    - Ancho/alineación por columna, formatters por celda
    - Mutaciones parciales (add/update/remove)
    """

    def __init__(
        self,
        *,
        group: str,
        sort_manager: SortManager,
        columns: List[Dict[str, Any]],
        # callbacks
        on_sort_change: Optional[Callable[[str, str, Optional[bool]], None]] = None,
        on_accept: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_cancel: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_edit: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_delete: Optional[Callable[[Dict[str, Any]], None]] = None,
        # estilo / métricas
        column_spacing: int = 24,
        heading_row_height: int = 44,
        data_row_height: int = 40,   # <- mantenemos el nombre externo
        actions_title: str = "Acciones",
        actions_width: Optional[int] = 140,
        dense_text: bool = True,
        # identificación de filas
        id_key: Optional[str] = None,
        is_new_row_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
        # scroll
        scroll_controller: Optional[ScrollTableController] = None,
        auto_scroll_new: bool = True,
        auto_scroll_target: str = "last",  # "last" | "first"
        auto_scroll_margin_top: int = 8,
        # acciones personalizadas
        actions_builder: Optional[ActionsBuilder] = None,
    ) -> None:

        self.group = group
        self.sort = sort_manager

        self.on_sort_change = on_sort_change
        self.on_accept = on_accept
        self.on_cancel = on_cancel
        self.on_edit = on_edit
        self.on_delete = on_delete

        self.columns = columns
        self.actions_title = actions_title
        self.actions_width = actions_width

        # estado de datos
        self._rows_data: List[Dict[str, Any]] = []

        # Métricas internas unificadas
        self._heading_row_height = heading_row_height
        self._row_height = data_row_height

        # tipografías compactas
        self._text_size = 12 if dense_text else 14

        # identificación de filas
        self._id_key = id_key
        self._is_new_row_fn = is_new_row_fn

        # scroll
        self._stc: Optional[ScrollTableController] = scroll_controller
        self._auto_scroll_new = auto_scroll_new
        self._auto_scroll_target = auto_scroll_target
        self._auto_scroll_margin_top = auto_scroll_margin_top

        # acciones personalizadas por fila
        self._actions_builder = actions_builder

        # header opcional (sólo con build_view)
        self._header_title: Optional[str] = None
        self._header_controls: List[ft.Control] = []
        self._header_align: ft.MainAxisAlignment = ft.MainAxisAlignment.END

        # ⚠️ IMPORTANTE: usa data_row_min_height (no data_row_height)
        self._table = ft.DataTable(
            columns=[],
            rows=[],
            column_spacing=column_spacing,
            heading_row_height=self._heading_row_height,
            data_row_min_height=self._row_height,  # <- compat
            show_checkbox_column=False,
        )

    # -------- Header opcional (para build_view) --------
    def set_header(
        self,
        *,
        title: Optional[str] = None,
        controls: Optional[List[ft.Control]] = None,
        alignment: ft.MainAxisAlignment = ft.MainAxisAlignment.END,
    ) -> None:
        self._header_title = title
        self._header_controls = controls or []
        self._header_align = alignment

    def _build_header_row(self) -> Optional[ft.Row]:
        if not self._header_title and not self._header_controls:
            return None
        left: List[ft.Control] = []
        if self._header_title:
            left.append(ft.Text(self._header_title, size=self._text_size + 2, weight="bold"))
        return ft.Row(
            controls=[
                ft.Row(left, alignment=ft.MainAxisAlignment.START, expand=True),
                ft.Row(self._header_controls, alignment=self._header_align),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # -------- Scroll controller --------
    def attach_scroll_controller(self, stc: ScrollTableController) -> None:
        self._stc = stc
        self._stc.attach_table_metrics(
            heading_height=self._heading_row_height,
            row_height=self._row_height,
        )

    # -------- Construcción --------
    def build(self) -> ft.DataTable:
        self._build_headers()
        self._rebuild_rows()
        if self._stc:
            self._stc.attach_table_metrics(
                heading_height=self._heading_row_height,
                row_height=self._row_height,
            )
        return self._table

    def build_view(self) -> ft.Control:
        self.build()
        parts: List[ft.Control] = []
        header = self._build_header_row()
        if header:
            parts.append(header)
            parts.append(ft.Divider(height=2))
        parts.append(self._table)
        return ft.Column(controls=parts, expand=False, spacing=6)

    def _build_headers(self) -> None:
        cols: List[ft.DataColumn] = []
        for col in self.columns:
            key = col["key"]
            title = col["title"]
            width = col.get("width")
            align = self._to_alignment(col.get("align", "start"))

            header_ctrl = self.sort.create_header(
                titulo=title,
                campo=key,
                grupo=self.group,
                width=width,
                text_size=self._text_size,
                on_click=self.on_sort_change
            )
            header_wrapped: ft.Control = ft.Container(header_ctrl, alignment=align)
            if width:
                header_wrapped = ft.Container(header_ctrl, width=width, alignment=align)

            cols.append(ft.DataColumn(label=header_wrapped))

        actions_text = ft.Text(self.actions_title, size=self._text_size, weight="bold")
        actions_label: ft.Control = (
            ft.Container(actions_text, width=self.actions_width, alignment=ft.alignment.center_left)
            if self.actions_width else actions_text
        )
        cols.append(ft.DataColumn(label=actions_label))
        self._table.columns = cols

    # -------- Render filas --------
    def _cell_from_value(
        self, value: Any, row: Dict[str, Any], formatter: Optional[ColumnFormatter], width: Optional[int], align: str
    ) -> ft.DataCell:
        if formatter:
            content = formatter(value, row)
        else:
            content = ft.Text("" if value is None else str(value), size=self._text_size)

        alignment = self._to_alignment(align)
        content = ft.Container(content, alignment=alignment) if not width else ft.Container(content, width=width, alignment=alignment)
        return ft.DataCell(content)

    def _actions_for_row(self, row: Dict[str, Any]) -> ft.DataCell:
        is_new = self._is_new_row(row)
        if self._actions_builder:
            return ft.DataCell(self._actions_builder(row, is_new))

        if is_new:
            return ft.DataCell(
                ft.Row(
                    [boton_aceptar(lambda e, r=row: self.on_accept and self.on_accept(r)),
                     boton_cancelar(lambda e, r=row: self.on_cancel and self.on_cancel(r))],
                    spacing=8, alignment=ft.MainAxisAlignment.START
                )
            )
        return ft.DataCell(
            ft.Row(
                [boton_editar(lambda e, r=row: self.on_edit and self.on_edit(r)),
                 boton_borrar(lambda e, r=row: self.on_delete and self.on_delete(r))],
                spacing=8, alignment=ft.MainAxisAlignment.START
            )
        )

    def _build_row(self, row: Dict[str, Any]) -> ft.DataRow:
        cells: List[ft.DataCell] = []
        for col in self.columns:
            key = col["key"]
            formatter: Optional[ColumnFormatter] = col.get("formatter")
            value = row.get(key, None)
            width = col.get("width")
            align = col.get("align", "start")
            cells.append(self._cell_from_value(value, row, formatter, width, align))
        cells.append(self._actions_for_row(row))
        return ft.DataRow(cells=cells)

    def _rebuild_rows(self) -> None:
        self._table.rows = [self._build_row(r) for r in self._rows_data]

    # -------- API pública de datos --------
    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        self._rows_data = rows or []
        self._rebuild_rows()
        self._soft_update()
        if self._stc and self._auto_scroll_new:
            self._auto_scroll_to_new_rows()

    def add_row(self, row: Dict[str, Any], *, auto_scroll: Optional[bool] = None) -> None:
        self._rows_data.append(row)
        self._table.rows.append(self._build_row(row))
        self._soft_update()

        do_scroll = self._auto_scroll_new if auto_scroll is None else auto_scroll
        if do_scroll and self._stc:
            self._scroll_to_index(len(self._rows_data) - 1)

    def update_row_at(self, index: int, new_row: Dict[str, Any]) -> None:
        if 0 <= index < len(self._rows_data):
            self._rows_data[index] = new_row
            self._table.rows[index] = self._build_row(new_row)
            self._soft_update()

    def update_row_by_id(self, id_value: Any, new_row: Dict[str, Any]) -> bool:
        idx = self._index_by_id(id_value)
        if idx is None:
            return False
        self.update_row_at(idx, new_row)
        return True

    def remove_row_at(self, index: int) -> None:
        if 0 <= index < len(self._rows_data):
            del self._rows_data[index]
            del self._table.rows[index]
            self._soft_update()

    def remove_row_by_id(self, id_value: Any) -> bool:
        idx = self._index_by_id(id_value)
        if idx is None:
            return False
        self.remove_row_at(idx)
        return True

    def refresh(self) -> None:
        self._rebuild_rows()
        self._soft_update()

    def get_rows(self) -> List[Dict[str, Any]]:
        return list(self._rows_data)

    # -------- Utilidades --------
    def get_sort_state(self) -> Dict[str, Optional[object]]:
        key, asc = self.sort.get(self.group)
        return {"key": key, "asc": asc}

    def set_column_formatter(self, key: str, formatter: Optional[ColumnFormatter]) -> None:
        for col in self.columns:
            if col["key"] == key:
                if formatter:
                    col["formatter"] = formatter
                elif "formatter" in col:
                    del col["formatter"]
                break
        self._rebuild_rows()
        self._soft_update()

    def set_columns(self, columns: List[Dict[str, Any]]) -> None:
        self.columns = columns or []
        self._build_headers()
        self._rebuild_rows()
        self._soft_update()

    def attach_actions_builder(self, builder: ActionsBuilder) -> None:
        self._actions_builder = builder
        self.refresh()

    def _auto_scroll_to_new_rows(self) -> None:
        indices = [i for i, r in enumerate(self._rows_data) if r.get("_is_new") is True]
        if not indices:
            return
        idx = indices[-1] if self._auto_scroll_target == "last" else indices[0]
        self._scroll_to_index(idx)

    def _scroll_to_index(self, idx: int) -> None:
        if not self._stc:
            return
        try:
            self._stc.scroll_to_row_index(idx, margin_top=self._auto_scroll_margin_top)
        except Exception:
            try:
                self._stc.scroll_to_new_record()
            except Exception:
                pass

    def _index_by_id(self, id_value: Any) -> Optional[int]:
        if self._id_key is None:
            return None
        for i, r in enumerate(self._rows_data):
            if r.get(self._id_key) == id_value:
                return i
        return None

    def _has_valid_id(self, row: Dict[str, Any]) -> bool:
        if self._id_key:
            val = row.get(self._id_key, None)
            return val not in (None, "", 0)
        for k in ("id", "ID", "id_trabajador", "numero_nomina", "uuid"):
            if k in row and row.get(k) not in (None, "", 0):
                return True
        return False

    def _is_new_row(self, row: Dict[str, Any]) -> bool:
        if self._is_new_row_fn:
            try:
                return bool(self._is_new_row_fn(row))
            except Exception:
                pass
        if self._has_valid_id(row):
            return False
        if row.get("_is_new", False):
            return True
        return True if not self._has_valid_id(row) else False

    def _to_alignment(self, align: str) -> ft.alignment.Alignment:
        if align == "center":
            return ft.alignment.center
        if align in ("end", "right"):
            return ft.alignment.center_right
        return ft.alignment.center_left

    def _soft_update(self) -> None:
        try:
            self._table.update()
            return
        except Exception:
            pass
        p = getattr(self._table, "page", None)
        if p is not None:
            try:
                p.update()
            except Exception:
                pass
