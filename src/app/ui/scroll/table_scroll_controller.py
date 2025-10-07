# app/ui/scroll/table_scroll_controller.py

from __future__ import annotations
from typing import Optional, Callable
import flet as ft


class ScrollTableController:
    """
    Control de scroll para TABLAS (horizontal + vertical) con
    soporte para auto-scroll a nuevos registros.

    Patrón composicional:
      Row (scroll=ALWAYS) -> Container(width=min_width) -> ListView
                                                    ->  [top_anchor, table_control, bottom_anchor]

    - Horizontal: Row.scroll = ALWAYS/AUTO/...
    - Vertical: ListView.scroll_to(offset=..., delta=..., key=...)
    - Auto-scroll a nueva fila: por índice (cálculo de offset) o al final (offset=-1)
    """

    def __init__(
        self,
        *,
        min_width: int = 900,             # ancho mínimo que provoca scroll horizontal
        max_height: Optional[int] = 480,  # alto visible del área vertical; None = expand
        spacing: int = 0,
        padding: int = 0,
        h_scroll: ft.ScrollMode = ft.ScrollMode.ALWAYS,
        animate_ms: int = 300,
        animate_curve: str = ft.AnimationCurve.DECELERATE,
    ) -> None:
        self._min_width = min_width
        self._max_height = max_height
        self._spacing = spacing
        self._padding = padding
        self._h_scroll_mode = h_scroll
        self._animate_ms = animate_ms
        self._animate_curve = animate_curve

        # Controles internos
        self._row_scroll: Optional[ft.Row] = None
        self._host: Optional[ft.Container] = None
        self._lv: Optional[ft.ListView] = None
        self._top_anchor = ft.Container(height=1, key="__stc_top__")
        self._bottom_anchor = ft.Container(height=1, key="__stc_bottom__")
        self._table_control: Optional[ft.Control] = None

        # Métricas de tabla para calcular offsets por fila
        self._heading_height: int = 44     # sugerencia por defecto
        self._row_height: int = 40         # sugerencia por defecto

    # =========================
    # Construcción
    # =========================
    def build(self, table_control: ft.Control) -> ft.Control:
        """Crea el wrapper de scroll para la tabla y lo devuelve listo para agregar a la vista."""
        self._table_control = table_control

        self._lv = ft.ListView(
            expand=(self._max_height is None),
            height=None if self._max_height is None else self._max_height,
            spacing=self._spacing,
            padding=self._padding,
            auto_scroll=False,
            controls=[self._top_anchor, table_control, self._bottom_anchor],
        )

        self._host = ft.Container(
            width=self._min_width,
            content=self._lv,
        )

        self._row_scroll = ft.Row(
            controls=[self._host],
            scroll=self._h_scroll_mode,
            expand=True,
        )

        return self._row_scroll

    # =========================
    # Métricas de la tabla
    # =========================
    def attach_table_metrics(self, *, heading_height: int, row_height: int) -> None:
        """
        Registra alturas para mejorar la precisión al hacer scroll por índice de fila.
        Úsalo con los valores reales de tu DataTable:
          - heading_height = heading_row_height del TableBuilder
          - row_height     = data_row_min_height (o el que uses)
        """
        self._heading_height = max(0, int(heading_height))
        self._row_height = max(1, int(row_height))

    # =========================
    # Dimensiones / modos
    # =========================
    def set_min_width(self, min_width: int) -> None:
        self._min_width = max(0, int(min_width))
        if self._host:
            self._host.width = self._min_width
            if self._host.page:
                self._host.update()

    def set_max_height(self, max_height: Optional[int]) -> None:
        self._max_height = max_height
        if self._lv:
            self._lv.expand = (max_height is None)
            self._lv.height = None if max_height is None else max_height
            if self._lv.page:
                self._lv.update()

    def set_horizontal_scroll(self, mode: ft.ScrollMode) -> None:
        self._h_scroll_mode = mode
        if self._row_scroll:
            self._row_scroll.scroll = mode
            if self._row_scroll.page:
                self._row_scroll.update()

    # =========================
    # Reemplazo / refresco
    # =========================
    def replace_table(self, new_table_control: ft.Control) -> None:
        self._table_control = new_table_control
        if self._lv:
            self._lv.controls[1] = new_table_control  # [top, table, bottom]
            if self._lv.page:
                self._lv.update()

    def refresh(self) -> None:
        if self._row_scroll and self._row_scroll.page:
            self._row_scroll.update()

    # =========================
    # Scroll vertical directo
    # =========================
    def to_top(self) -> None:
        if not self._lv:
            return
        try:
            self._lv.scroll_to(offset=0, duration=self._animate_ms, curve=self._animate_curve)
        except Exception:
            pass

    def to_bottom(self) -> None:
        if not self._lv:
            return
        try:
            # offset negativo: -1 = final garantizado
            self._lv.scroll_to(offset=-1, duration=self._animate_ms, curve=self._animate_curve)
        except Exception:
            pass

    def set_vscroll_listener(self, callback: Optional[Callable[[ft.OnScrollEvent], None]], *, interval_ms: int = 100) -> None:
        if not self._lv:
            return
        self._lv.on_scroll = callback
        self._lv.on_scroll_interval = interval_ms
        if self._lv.page:
            self._lv.update()

    # =========================
    # Auto-scroll a nuevas filas
    # =========================
    def scroll_to_row_index(self, row_index: int, *, margin_top: int = 8) -> None:
        """
        Desplaza la vista hasta aproximar la fila `row_index` a la zona visible.
        Calcula un offset vertical: heading + row_index * row_height - margin_top.
        """
        if not self._lv:
            return
        try:
            idx = max(0, int(row_index))
            offset = self._heading_height + idx * self._row_height - max(0, int(margin_top))
            if offset < 0:
                offset = 0
            self._lv.scroll_to(offset=offset, duration=self._animate_ms, curve=self._animate_curve)
        except Exception:
            # Fallback: si algo falla, al final (comportamiento más común para appends)
            self.to_bottom()

    def scroll_to_new_record(self, row_index: Optional[int] = None, *, margin_top: int = 8) -> None:
        """
        Auto-scroll tras insertar un nuevo registro.
        - Si `row_index` es None, asume append y va al final.
        - Si se pasa `row_index`, calcula offset para hacer visible esa fila.
        """
        if row_index is None:
            self.to_bottom()
        else:
            self.scroll_to_row_index(row_index, margin_top=margin_top)
