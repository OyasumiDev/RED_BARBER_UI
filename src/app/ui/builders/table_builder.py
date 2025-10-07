# app/ui/builders/table_builder.py

from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
import flet as ft

# BotonFactory (helpers)
from app.ui.factory.boton_factory import (
    boton_aceptar, boton_cancelar, boton_editar, boton_borrar
)

# SortManager
from app.ui.sorting.sort_manager import SortManager

# Scroll controller (scroll vertical/horizontal de la tabla)
from app.ui.scroll.table_scroll_controller import ScrollTableController


ColumnFormatter = Callable[[Any, Dict[str, Any]], ft.Control]


class TableBuilder:
    """
    TableBuilder: DataTable integrada con SortManager y BotonFactory,
    con soporte opcional de auto-scroll a nuevas filas usando ScrollTableController.

    Reglas de acciones:
      - Fila NUEVA -> Aceptar / Cancelar
      - Fila EXISTENTE -> Editar / Borrar

    Detecta "fila nueva" así (en orden):
      1) is_new_row_fn(row) si se proporciona
      2) id_key si se proporcionó y row[id_key] está vacío/None/0
      3) fallback: si no veo un id típico y row["_is_new"] es True
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
        data_row_min_height: int = 40,
        actions_title: str = "Acciones",
        actions_width: Optional[int] = 140,
        actions_padding: int = 4,
        dense_text: bool = True,
        # identificación de filas
        id_key: Optional[str] = None,
        is_new_row_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
        # scroll
        scroll_controller: Optional[ScrollTableController] = None,
        auto_scroll_new: bool = True,
        auto_scroll_target: str = "last",  # "last" | "first"
        auto_scroll_margin_top: int = 8,
    ) -> None:
        """
        columns: lista de dicts:
          - key (str)        -> llave del dato en la fila
          - title (str)      -> texto del encabezado
          - width (int|None) -> ancho del header (opcional)
          - formatter (callable|None) -> ColumnFormatter(value, row) -> ft.Control
        """
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
        self.actions_padding = actions_padding

        # estado de datos
        self._rows_data: List[Dict[str, Any]] = []

        # control raíz
        self._table = ft.DataTable(
            columns=[], rows=[],
            column_spacing=column_spacing,
            heading_row_height=heading_row_height,
            data_row_min_height=data_row_min_height,
            show_checkbox_column=False,
        )

        # tipografías compactas (opcional)
        self._text_size = 12 if dense_text else 14

        # métricas para scroll controller
        self._heading_row_height = heading_row_height
        self._data_row_min_height = data_row_min_height

        # identificación de filas
        self._id_key = id_key
        self._is_new_row_fn = is_new_row_fn

        # scroll
        self._stc: Optional[ScrollTableController] = scroll_controller
        self._auto_scroll_new = auto_scroll_new
        self._auto_scroll_target = auto_scroll_target
        self._auto_scroll_margin_top = auto_scroll_margin_top

    # ===========================
    # Integración Scroll Controller
    # ===========================
    def attach_scroll_controller(self, stc: ScrollTableController) -> None:
        """Adjunta/actualiza el ScrollTableController y sincroniza métricas."""
        self._stc = stc
        self._stc.attach_table_metrics(
            heading_height=self._heading_row_height,
            row_height=self._data_row_min_height,
        )

    # ===========================
    # Construcción de tabla
    # ===========================
    def build(self) -> ft.DataTable:
        """Devuelve el control DataTable listo para agregarse a la vista."""
        self._build_headers()
        self._rebuild_rows()

        # Si ya tenemos un scroll controller, sincroniza métricas
        if self._stc:
            self._stc.attach_table_metrics(
                heading_height=self._heading_row_height,
                row_height=self._data_row_min_height,
            )
        return self._table

    def _build_headers(self) -> None:
        cols: List[ft.DataColumn] = []

        for col in self.columns:
            key = col["key"]
            title = col["title"]
            width = col.get("width")
            header_ctrl = self.sort.create_header(
                titulo=title,
                campo=key,
                grupo=self.group,
                width=width,
                text_size=self._text_size,
                on_click=self.on_sort_change  # la vista decide reconsultar/ordenar
            )
            cols.append(ft.DataColumn(label=header_ctrl))

        # Columna de acciones
        actions_label = (
            ft.Container(
                ft.Text(self.actions_title, size=self._text_size, weight="bold"),
                width=self.actions_width,
            )
            if self.actions_width
            else ft.Text(self.actions_title, size=self._text_size, weight="bold")
        )
        cols.append(ft.DataColumn(label=actions_label))

        self._table.columns = cols

    # ===========================
    # Render filas
    # ===========================
    def _cell_from_value(
        self, value: Any, row: Dict[str, Any], formatter: Optional[ColumnFormatter]
    ) -> ft.DataCell:
        if formatter:
            ctrl = formatter(value, row)
            return ft.DataCell(ctrl)
        text = "" if value is None else str(value)
        return ft.DataCell(ft.Text(text, size=self._text_size))

    def _has_valid_id(self, row: Dict[str, Any]) -> bool:
        """
        Devuelve True si la fila aparenta tener un ID persistido.
        Se usa para decidir acciones (Aceptar/Cancelar vs Editar/Borrar).
        """
        if self._id_key:
            val = row.get(self._id_key, None)
            return val not in (None, "", 0)
        # Heurística por claves comunes si no se configuró id_key:
        for k in ("id", "ID", "id_trabajador", "numero_nomina", "uuid"):
            if k in row and row.get(k) not in (None, "", 0):
                return True
        return False

    def _is_new_row(self, row: Dict[str, Any]) -> bool:
        """Regla unificada de 'fila nueva'."""
        if self._is_new_row_fn:
            try:
                return bool(self._is_new_row_fn(row))
            except Exception:
                pass
        # Si ya tiene ID válido, NO es nueva aunque alguien ponga _is_new=True
        if self._has_valid_id(row):
            return False
        # Si no hay ID válido, considerar nueva si el flag está presente o si no hay ID en absoluto
        if row.get("_is_new", False):
            return True
        # No hay ID detectado y tampoco _is_new -> asume nueva si falta cualquier id común
        return True if not self._has_valid_id(row) else False

    def _actions_for_row(self, row: Dict[str, Any]) -> ft.DataCell:
        is_new = self._is_new_row(row)

        if is_new:
            # ✅ Botones nativos (evitan wrappers que absorben eventos)
            btns = ft.Row(
                [
                    ft.ElevatedButton(
                        text="Aceptar",
                        icon=ft.icons.CHECK,
                        on_click=(lambda e, r=row: self.on_accept and self.on_accept(r)),
                        height=36,
                    ),
                    ft.OutlinedButton(
                        text="Cancelar",
                        icon=ft.icons.CLOSE,
                        on_click=(lambda e, r=row: self.on_cancel and self.on_cancel(r)),
                        height=36,
                    ),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.START,
            )
            # ⚠️ No envolver en Container para no interceptar taps
            return ft.DataCell(btns)

        # 🔁 Para existentes, mantenemos tu BotonFactory (estilo unificado)
        btns = ft.Row(
            [
                boton_editar(lambda e, r=row: self.on_edit and self.on_edit(r)),
                boton_borrar(lambda e, r=row: self.on_delete and self.on_delete(r)),
            ],
            spacing=6, alignment=ft.MainAxisAlignment.START
        )
        # En acciones existentes es seguro un Container fino para ancho fijo
        container = ft.Container(
            btns,
            width=self.actions_width,
            padding=ft.padding.symmetric(horizontal=self.actions_padding),
            alignment=ft.alignment.center_left,
        ) if self.actions_width else btns

        return ft.DataCell(container)


    def _build_row(self, row: Dict[str, Any]) -> ft.DataRow:
        cells: List[ft.DataCell] = []
        for col in self.columns:
            key = col["key"]
            formatter: Optional[ColumnFormatter] = col.get("formatter")
            value = row.get(key, None)
            cells.append(self._cell_from_value(value, row, formatter))
        cells.append(self._actions_for_row(row))
        return ft.DataRow(cells=cells)

    def _rebuild_rows(self) -> None:
        self._table.rows = [self._build_row(r) for r in self._rows_data]

    # ===========================
    # API pública de datos
    # ===========================
    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        """
        Establece las filas a renderizar. La vista controla el orden.
        Para marcar una fila como nueva (Aceptar/Cancelar):
           - Recomendado: deja el ID None/""/0 (usa id_key), y opcional _is_new=True.
           - Alternativa si no tienes id_key: usa row["_is_new"] = True (y sin ID típico).
        """
        self._rows_data = rows or []
        self._rebuild_rows()
        if self._table.page:
            self._table.update()

        # Auto-scroll a la(s) fila(s) nueva(s) si corresponde
        if self._stc and self._auto_scroll_new:
            self._auto_scroll_to_new_rows()

    def refresh(self) -> None:
        self._rebuild_rows()
        if self._table.page:
            self._table.update()

    # ===========================
    # Utilidades
    # ===========================
    def get_sort_state(self) -> Dict[str, Optional[object]]:
        key, asc = self.sort.get(self.group)
        return {"key": key, "asc": asc}

    def _auto_scroll_to_new_rows(self) -> None:
        """
        Busca filas con _is_new == True y hace scroll automático.
        Nota: si tu contenedor pone _is_new=True en edición de registros existentes,
        esta rutina NO cambia acciones (eso lo decide _is_new_row), solo el scroll.
        """
        indices = [i for i, r in enumerate(self._rows_data) if r.get("_is_new") is True]
        if not indices:
            return

        idx = indices[-1] if self._auto_scroll_target == "last" else indices[0]
        try:
            # Desplazamiento con las métricas ya informadas al ScrollTableController
            self._stc.scroll_to_row_index(idx, margin_top=self._auto_scroll_margin_top)  # type: ignore[union-attr]
        except Exception:
            # fallback: ir al final si algo falla
            self._stc.scroll_to_new_record()  # type: ignore[union-attr]
