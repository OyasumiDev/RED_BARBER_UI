from __future__ import annotations
import flet as ft
from typing import Any, Dict, List, Optional

# Core global
from app.config.application.app_state import AppState
from app.views.containers.nvar.layout_controller import LayoutController

# Modelo y enums
from app.models.inventario_model import InventarioModel
from app.core.enums.e_inventario import (
    E_INVENTARIO, E_INV_CATEGORIA, E_INV_UNIDAD, E_INV_ESTADO, E_INV_MOV
)
from app.core.enums.e_usuarios import E_USU_ROL  # <- permisos por rol

# TableBuilder + SortManager + (opcional) Scroll controller
from app.ui.builders.table_builder import TableBuilder
from app.ui.sorting.sort_manager import SortManager
try:
    from app.ui.scroll.table_scroll_controller import ScrollTableController
except Exception:
    ScrollTableController = None  # opcional

# BotonFactory (acciones estándar en filas)
from app.ui.factory.boton_factory import (
    boton_aceptar, boton_cancelar, boton_editar, boton_borrar
)

# ----------------------------- Helpers -----------------------------
def _txt(v: Any) -> str:
    return "" if v is None else str(v)

def _f2(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "0.00"

def _f3(v: Any) -> str:
    try:
        return f"{float(v):.3f}"
    except Exception:
        return "0.000"




class InventarioContainer(ft.Container):
    """
    Inventario con TableBuilder v2 y permisos por rol.

    - Recepcionista: SOLO ver y filtrar/buscar. (Sin agregar, sin editar, sin borrar, sin movimientos).
    - Root: CRUD completo + movimientos (Entrada/Salida) + import/export.
    - Stock:
        * Root puede escribir stock al CREAR (stock inicial) y al EDITAR (se aplica delta como entrada/salida).
        * Recepcionista nunca edita.
    """

    # =========================================================
    # Init
    # =========================================================
    def __init__(self):
        super().__init__(expand=True)

        # Core
        self.app_state = AppState()
        self.page = self.app_state.page
        self.colors = self.app_state.get_colors()

        # ---- UI knobs (todo el módulo usa esto) ----
        self.UI = dict(
            pad_page=16,          # padding del content principal
            row_spacing=6,        # separación entre controles del toolbar (horizontal)
            row_run_spacing=6,    # separación entre "líneas" si hiciera wrap
            tf_height=36,         # alto de textfields/dropdowns
            tf_text_size=12,      # tamaño del texto en inputs
            tf_label_size=11,     # tamaño del label en inputs
            tf_pad_h=8,           # padding horizontal interno en inputs
            tf_pad_v=4,           # padding vertical interno en inputs
            pill_pad=6,           # padding de los botoncitos "pill"
            pill_icon=16,         # tamaño del icono de pill
            pill_text=11,         # tamaño del texto de pill
            icon_btn=18,          # tamaño de iconos (clear, etc.)
            # Anchos del toolbar
            w_id=110,
            w_nombre=240,
            w_categoria=168,
        )

        # Permisos por rol
        sess = None
        try:
            sess = self.page.client_storage.get("app.user") if self.page else None
        except Exception:
            pass
        role = (sess.get("rol") if isinstance(sess, dict) else "") or ""
        self.is_root = (role or "").lower() == E_USU_ROL.ROOT.value

        # recepcionista NO puede agregar/editar/borrar/mover
        self.can_add = self.is_root
        self.can_edit_existing = self.is_root
        self.can_delete = self.is_root
        self.can_move = self.is_root
        self.can_import_export = self.is_root

        # Estado
        self._mounted = False
        self._theme_listener = None
        self.layout_ctrl = LayoutController()
        self._layout_listener = None

        # Edición/nuevo
        self.fila_editando: Optional[int] = None
        self.fila_nueva_en_proceso: bool = False

        # Filtros/orden
        self.sort_id_filter: Optional[str] = None
        self.sort_name_filter: Optional[str] = None
        self.categoria_filter: Optional[str] = None
        self.only_low_stock: bool = False
        self.orden_actual: Dict[str, Optional[str]] = {
            E_INVENTARIO.ID.value: None,
            E_INVENTARIO.NOMBRE.value: None,
            E_INVENTARIO.CATEGORIA.value: None,
            E_INVENTARIO.UNIDAD.value: None,
            E_INVENTARIO.STOCK_ACTUAL.value: None,
            E_INVENTARIO.STOCK_MINIMO.value: None,
            E_INVENTARIO.COSTO_UNITARIO.value: None,
            E_INVENTARIO.PRECIO_UNITARIO.value: None,
            E_INVENTARIO.ESTADO.value: None,
        }

        # Refs de controles
        self._edit_controls: Dict[int, Dict[str, ft.Control]] = {}

        # Modelo
        self.model = InventarioModel()
        self.model.set_on_low_stock(self._on_low_stock_alert)

        # ---------- Layout base / contenedores ----------
        self.table_container = ft.Container(
            expand=True,
            alignment=ft.alignment.top_center,
            bgcolor=self.colors.get("BG_COLOR"),
            content=ft.Column(
                controls=[],
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self.scroll_anchor = ft.Container(height=1, key="bottom-anchor")
        self.scroll_column = ft.Column(
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
            controls=[self.table_container, self.scroll_anchor],
        )

        # ---------------- Botones "pill" (compactos) ----------------
        def _pill(icon_name, text, on_click):
            return ft.GestureDetector(
                on_tap=on_click,
                content=ft.Container(
                    padding=self.UI["pill_pad"],
                    border_radius=18,
                    bgcolor=self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT),
                    content=ft.Row(
                        [
                            ft.Icon(
                                icon_name,
                                size=self.UI["pill_icon"],
                                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                            ),
                            ft.Text(
                                text,
                                size=self.UI["pill_text"],
                                weight="bold",
                                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=6,
                    ),
                ),
            )

        self.import_button = _pill(ft.icons.FILE_DOWNLOAD_OUTLINED, "Importar", lambda e: self._on_importar())
        self.import_button.visible = False  # ← oculto por ahora
        self.export_button = _pill(ft.icons.FILE_UPLOAD_OUTLINED, "Exportar", lambda e: self._on_exportar())
        self.add_button = _pill(ft.icons.ADD, "Agregar", lambda e: self._insertar_fila_nueva())

        # ---------------- Toolbar (filtros) ----------------
        self.sort_id_input = ft.TextField(
            label="ID",
            hint_text="ID (Enter)",
            width=self.UI["w_id"],
            height=self.UI["tf_height"],
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=lambda e: self._aplicar_sort_id(),
            on_change=self._id_on_change_auto_reset,
            text_size=self.UI["tf_text_size"],
            content_padding=ft.padding.symmetric(
                horizontal=self.UI["tf_pad_h"],
                vertical=self.UI["tf_pad_v"],
            ),
        )
        self._apply_textfield_palette(self.sort_id_input)
        self.sort_id_input.label_style = ft.TextStyle(
            size=self.UI["tf_label_size"], color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        )
        self.sort_id_clear_btn = ft.IconButton(
            icon=ft.icons.CLEAR,
            tooltip="Limpiar ID",
            icon_size=self.UI["icon_btn"],
            icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            on_click=lambda e: self._limpiar_sort_id(),
        )

        self.sort_name_input = ft.TextField(
            label="Nombre",
            hint_text="Nombre (Enter)",
            width=self.UI["w_nombre"],
            height=self.UI["tf_height"],
            on_submit=lambda e: self._aplicar_sort_nombre(),
            on_change=self._nombre_on_change_auto_reset,
            text_size=self.UI["tf_text_size"],
            content_padding=ft.padding.symmetric(
                horizontal=self.UI["tf_pad_h"],
                vertical=self.UI["tf_pad_v"],
            ),
        )
        self._apply_textfield_palette(self.sort_name_input)
        self.sort_name_input.label_style = ft.TextStyle(
            size=self.UI["tf_label_size"], color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        )
        self.sort_name_clear_btn = ft.IconButton(
            icon=ft.icons.CLEAR,
            tooltip="Limpiar nombre",
            icon_size=self.UI["icon_btn"],
            icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            on_click=lambda e: self._limpiar_sort_nombre(),
        )

        self.categoria_dd = ft.Dropdown(
            label="Categoría",
            width=self.UI["w_categoria"],
            height=self.UI["tf_height"],
            options=[
                ft.dropdown.Option("", "Todas"),
                ft.dropdown.Option(E_INV_CATEGORIA.INSUMO.value, "Insumo"),
                ft.dropdown.Option(E_INV_CATEGORIA.HERRAMIENTA.value, "Herramienta"),
                ft.dropdown.Option(E_INV_CATEGORIA.PRODUCTO.value, "Producto"),
            ],
            on_change=lambda e: self._aplicar_categoria(),
            dense=True,
            text_style=ft.TextStyle(
                size=self.UI["tf_text_size"],
                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            ),
        )
        self.categoria_dd.label_style = ft.TextStyle(
            size=self.UI["tf_label_size"], color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        )

        self.low_stock_switch = ft.Switch(
            label="Solo bajo stock",
            value=self.only_low_stock,
            on_change=lambda e: self._toggle_low_stock(e.control.value),
            scale=0.9,  # un pelín más pequeño
        )

        self.filters_clear_btn = ft.IconButton(
            icon=ft.icons.CLEAR_ALL,
            tooltip="Limpiar filtros",
            icon_size=self.UI["icon_btn"],
            icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            on_click=lambda e: self._limpiar_filtros(),
        )

        # ---------------- Toolbar AGRUPADO (izquierda ACCIONES, derecha FILTROS) ----------------
        # Pares "campo + limpiar"
        id_group = ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.sort_id_input, self.sort_id_clear_btn],
        )
        name_group = ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.sort_name_input, self.sort_name_clear_btn],
        )

        # Izquierda: acciones (sin wrap)
        left_actions_controls: List[ft.Control] = []
        if self.can_add:
            left_actions_controls.append(self.add_button)
        if self.can_import_export:
            left_actions_controls += [self.export_button, self.import_button]  # importar está invisible
        left_actions = ft.Row(
            spacing=8,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=left_actions_controls,
        )

        # Derecha: filtros (con wrap propio)
        right_filters = ft.Row(
            wrap=True,
            spacing=self.UI["row_spacing"],
            run_spacing=self.UI["row_run_spacing"],
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                id_group,
                name_group,
                self.categoria_dd,
                self.low_stock_switch,
                self.filters_clear_btn,
            ],
        )

        # Toolbar final
        self._toolbar = ft.Container(
            padding=ft.padding.only(bottom=6),
            content=ft.Row(
                spacing=12,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    left_actions,
                    ft.Container(expand=True),  # spacer flexible
                    right_filters,
                ],
            ),
        )

        # ---------------- Content raíz ----------------
        self.content = ft.Container(
            expand=True,
            bgcolor=self.colors.get("BG_COLOR"),
            padding=self.UI["pad_page"],
            content=ft.Column(
                expand=True,
                alignment=ft.MainAxisAlignment.START,
                spacing=8,
                controls=[
                    self._toolbar,
                    ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)),
                    ft.Container(
                        alignment=ft.alignment.top_center,
                        padding=ft.padding.only(top=6),
                        expand=True,
                        content=self.scroll_column,
                    ),
                ],
            ),
        )

        # ---------- TableBuilder responsivo ----------
        self._build_table_responsive()

        # Scroll controller
        if ScrollTableController:
            try:
                self.stc = ScrollTableController()
                self.table_builder.attach_scroll_controller(self.stc)
            except Exception:
                self.stc = None
        else:
            self.stc = None

        # Render inicial
        self._refrescar_dataset()

        # Listeners de tema y layout
        try:
            self._theme_listener = self._on_theme_changed
            self.app_state.on_theme_change(self._theme_listener)
        except Exception:
            self._theme_listener = None

        try:
            self._layout_listener = self._on_layout_changed
            self.layout_ctrl.add_listener(self._layout_listener)
        except Exception:
            self._layout_listener = None

    # ---------------------------
    # Ciclo de vida
    # ---------------------------
    def did_mount(self):
        self._mounted = True
        self.page = self.app_state.get_page()
        self.colors = self.app_state.get_colors()
        self._recolor_ui()
        self._safe_update()

    def will_unmount(self):
        self._mounted = False
        if self._theme_listener:
            try: self.app_state.off_theme_change(self._theme_listener)
            except Exception: pass
            self._theme_listener = None
        if self._layout_listener:
            try: self.layout_ctrl.remove_listener(self._layout_listener)
            except Exception: pass
            self._layout_listener = None

    def _safe_update(self):
        p = getattr(self, "page", None)
        if p:
            try: p.update()
            except AssertionError: pass

    # =========================================================
    # Logging util
    # =========================================================
    def _log(self, *args, **kwargs):
        """Log a consola con prefijo del módulo."""
        try:
            print("[InventarioContainer]", *args, **kwargs)
        except Exception:
            pass

    # =========================================================
    # Theme
    # =========================================================
    def _apply_textfield_palette(self, tf: ft.TextField):
        tf.bgcolor = self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
        tf.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.label_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                                      size=self.UI["tf_label_size"])
        tf.hint_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                                     size=self.UI["tf_text_size"])
        tf.cursor_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.border_color = self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)
        tf.focused_border_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _on_theme_changed(self):
        self.colors = self.app_state.get_colors()
        self._recolor_ui()
        self._refrescar_dataset()

    def _recolor_ui(self):
        # pills
        for btn in [self.import_button, self.export_button, self.add_button]:
            if isinstance(btn.content, ft.Container):
                btn.content.bgcolor = self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)
                if isinstance(btn.content.content, ft.Row):
                    for c in btn.content.content.controls:
                        if isinstance(c, ft.Icon): c.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
                        if isinstance(c, ft.Text): c.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

        # inputs
        self._apply_textfield_palette(self.sort_id_input)
        self._apply_textfield_palette(self.sort_name_input)
        self.sort_id_clear_btn.icon_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        self.sort_name_clear_btn.icon_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        self.categoria_dd.text_style = ft.TextStyle(
            color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            size=self.UI["tf_text_size"],
        )
        self.categoria_dd.label_style = ft.TextStyle(
            color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            size=self.UI["tf_label_size"],
        )
        self.filters_clear_btn.icon_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

        # fondos
        self.bgcolor = self.colors.get("BG_COLOR")
        self.table_container.bgcolor = self.colors.get("BG_COLOR")
        if isinstance(self.content, ft.Container):
            self.content.bgcolor = self.colors.get("BG_COLOR")

        self._safe_update()

    # =========================================================
    # Layout (nvar expand/colapse)
    # =========================================================
    def _on_layout_changed(self, expanded: bool):
        # Si cambia ancho, los Wrap se recolocan solos
        self._safe_update()

    # =========================================================
    # Filtros
    # =========================================================
    def _aplicar_sort_id(self):
        v = (self.sort_id_input.value or "").strip()
        if v and not v.isdigit():
            self._snack_error("❌ ID inválido. Usa solo números.")
            return
        self.sort_id_filter = v if v else None
        self._refrescar_dataset()

    def _limpiar_sort_id(self):
        self.sort_id_input.value = ""
        self.sort_id_filter = None
        self._refrescar_dataset()

    def _id_on_change_auto_reset(self, e: ft.ControlEvent):
        if (e.control.value or "").strip() == "" and self.sort_id_filter is not None:
            self.sort_id_filter = None
            self._refrescar_dataset()

    def _aplicar_sort_nombre(self):
        texto = (self.sort_name_input.value or "").strip()
        self.sort_name_filter = texto if texto else None
        self._refrescar_dataset()

    def _limpiar_sort_nombre(self):
        self.sort_name_input.value = ""
        self.sort_name_filter = None
        self._refrescar_dataset()

    def _nombre_on_change_auto_reset(self, e: ft.ControlEvent):
        if (e.control.value or "").strip() == "" and self.sort_name_filter is not None:
            self.sort_name_filter = None
            self._refrescar_dataset()

    def _aplicar_categoria(self):
        v = (self.categoria_dd.value or "").strip()
        self.categoria_filter = v or None
        self._refrescar_dataset()

    def _toggle_low_stock(self, val: bool):
        self.only_low_stock = bool(val)
        self._refrescar_dataset()

    def _limpiar_filtros(self):
        self.sort_id_filter = None
        self.sort_name_filter = None
        self.categoria_filter = None
        self.only_low_stock = False

        self.sort_id_input.value = ""
        self.sort_name_input.value = ""
        self.categoria_dd.value = ""
        self.low_stock_switch.value = False

        self._refrescar_dataset()


    # =========================================================
    # Orden por encabezado
    # =========================================================
    def _on_sort_change(self, campo: str, grupo: Optional[str] = None, asc: Optional[bool] = None, *_, **__):
        prev = self.orden_actual.get(campo)
        nuevo = "desc" if prev == "asc" else "asc"
        self.orden_actual = {k: None for k in self.orden_actual}
        self.orden_actual[campo] = nuevo
        self._refrescar_dataset()

    def _aplicar_prioridades_y_orden(self, datos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ordered = list(datos)

        # prioridad por id
        if self.sort_id_filter:
            id_str = str(self.sort_id_filter)
            ordered = sorted(ordered, key=lambda r: 0 if str(r.get(self.ID)) == id_str else 1)

        # prioridad por nombre
        if self.sort_name_filter:
            q = self.sort_name_filter.lower()
            ordered = sorted(ordered, key=lambda r: 0 if q in str(r.get(self.NOMBRE, "")).lower() else 1)

        # orden por columna activa
        col_activa = next((k for k, v in self.orden_actual.items() if v), None)
        if col_activa:
            asc = self.orden_actual[col_activa] == "asc"

            def keyfn(x):
                val = x.get(col_activa)
                if col_activa in (self.ID, self.STOCK, self.MINIMO, self.COSTO, self.PRECIO):
                    try: return float(val or 0)
                    except Exception: return 0.0
                return (val or "")

            ordered.sort(key=keyfn, reverse=not asc)

        return ordered

    # =========================================================
    # Dataset / Render
    # =========================================================
    def _fetch(self) -> List[Dict[str, Any]]:
        estado = None
        categoria = self.categoria_filter
        rows = self.model.listar(estado=estado, categoria=categoria) or []
        if self.sort_name_filter:
            q = self.sort_name_filter.lower()
            rows = [r for r in rows if q in str(r.get(self.NOMBRE, "")).lower()]
        if self.sort_id_filter:
            rows = [r for r in rows if str(r.get(self.ID)) == str(self.sort_id_filter)]
        if self.only_low_stock:
            def _f(v):
                try: return float(v or 0)
                except Exception: return 0.0
            rows = [r for r in rows if _f(r.get(self.STOCK)) <= _f(r.get(self.MINIMO))]
        return rows

    def _refrescar_dataset(self):
        datos = self._aplicar_prioridades_y_orden(self._fetch())
        if not self.table_container.content.controls:
            self.table_container.content.controls.append(self.table_builder.build())
        self.table_builder.set_rows(datos)
        self._safe_update()

    # =========================================================
    # Formatters por columna
    # =========================================================
    def _en_edicion(self, row: Dict[str, Any]) -> bool:
        """Solo root puede editar (ya sea fila nueva o existente en edición)."""
        rid = row.get(self.ID)
        return self.is_root and ((self.fila_editando == rid) or bool(row.get("_is_new")))

    def _fmt_id(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        return ft.Text(_txt(value), size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

    def _fmt_nombre(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        if not self._en_edicion(row):
            return ft.Text(_txt(value), size=12, color=fg)
        tf = ft.TextField(
            value=_txt(value),
            hint_text="Nombre del producto",
            text_size=self.UI["tf_text_size"],
            height=self.UI["tf_height"],
            content_padding=ft.padding.symmetric(horizontal=self.UI["tf_pad_h"], vertical=self.UI["tf_pad_v"])
        )
        self._apply_textfield_palette(tf)
        def validar(_):
            v = (tf.value or "").strip()
            tf.border_color = None if len(v) >= 2 else ft.colors.RED
            self._safe_update()
        tf.on_change = validar
        key = (row.get(self.ID) if row.get(self.ID) is not None else -1)
        self._ensure_edit_map(key); self._edit_controls[key]["nombre"] = tf
        return tf

    def _fmt_categoria(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        if not self._en_edicion(row):
            return ft.Text(_txt(value), size=12, color=fg)
        dd = ft.Dropdown(
            value=value or E_INV_CATEGORIA.INSUMO.value,
            options=[
                ft.dropdown.Option(E_INV_CATEGORIA.INSUMO.value, "insumo"),
                ft.dropdown.Option(E_INV_CATEGORIA.HERRAMIENTA.value, "herramienta"),
                ft.dropdown.Option(E_INV_CATEGORIA.PRODUCTO.value, "producto"),
            ],
            dense=True, width=140, height=self.UI["tf_height"],
            text_style=ft.TextStyle(size=self.UI["tf_text_size"], color=fg),
        )
        key = (row.get(self.ID) if row.get(self.ID) is not None else -1)
        self._ensure_edit_map(key); self._edit_controls[key]["categoria"] = dd
        return dd

    def _fmt_unidad(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        if not self._en_edicion(row):
            return ft.Text(_txt(value), size=12, color=fg)
        dd = ft.Dropdown(
            value=value or E_INV_UNIDAD.PIEZA.value,
            options=[
                ft.dropdown.Option(E_INV_UNIDAD.PIEZA.value, "pieza"),
                ft.dropdown.Option(E_INV_UNIDAD.ML.value, "ml"),
                ft.dropdown.Option(E_INV_UNIDAD.GR.value, "gr"),
                ft.dropdown.Option(E_INV_UNIDAD.LT.value, "lt"),
                ft.dropdown.Option(E_INV_UNIDAD.KG.value, "kg"),
                ft.dropdown.Option(E_INV_UNIDAD.CAJA.value, "caja"),
                ft.dropdown.Option(E_INV_UNIDAD.PAQUETE.value, "paquete"),
            ],
            dense=True, width=120, height=self.UI["tf_height"],
            text_style=ft.TextStyle(size=self.UI["tf_text_size"], color=fg),
        )
        key = (row.get(self.ID) if row.get(self.ID) is not None else -1)
        self._ensure_edit_map(key); self._edit_controls[key]["unidad"] = dd
        return dd

    def _fmt_stock(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        """
        Stock:
        - Solo root lo edita (nueva o edición). Recepcionista siempre ve texto.
        """
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = self._en_edicion(row)

        if not en_edicion:
            try:
                current = float(row.get(self.STOCK) or 0)
            except Exception:
                current = 0.0
            try:
                minimo  = float(row.get(self.MINIMO) or 0)
            except Exception:
                minimo = 0.0
            col = fg if current > minimo else ft.colors.RED_600
            icon = None if current > minimo else ft.Icon(ft.icons.WARNING_AMBER_ROUNDED, size=14, color=col)
            label = ft.Text(_f3(current), size=12, color=col)
            return ft.Row([label, icon] if icon else [label], spacing=4, alignment=ft.MainAxisAlignment.END)

        # Editable (nueva o edición root)
        tf = ft.TextField(
            value=("" if row.get("_is_new") else _f3(value or 0)),
            hint_text="Stock",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_size=self.UI["tf_text_size"],
            height=self.UI["tf_height"],
            content_padding=ft.padding.symmetric(horizontal=self.UI["tf_pad_h"], vertical=self.UI["tf_pad_v"]),
        )
        self._apply_textfield_palette(tf)

        def validar(_):
            try:
                v = float((tf.value or "").replace(",", "."))
                tf.border_color = None if v >= 0 else ft.colors.RED
            except Exception:
                tf.border_color = ft.colors.RED
            self._safe_update()
        tf.on_change = validar

        key = (rid if rid is not None else -1)
        self._ensure_edit_map(key)
        self._edit_controls[key]["stock_actual"] = tf
        return tf

    def _fmt_minimo(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        if not self._en_edicion(row):
            return ft.Text(_f3(value), size=12, color=fg)
        tf = ft.TextField(
            value=_f3(value) if value is not None and not row.get("_is_new") else "",
            hint_text="Stock mínimo", keyboard_type=ft.KeyboardType.NUMBER,
            text_size=self.UI["tf_text_size"], height=self.UI["tf_height"],
            content_padding=ft.padding.symmetric(horizontal=self.UI["tf_pad_h"], vertical=self.UI["tf_pad_v"]),
        )
        self._apply_textfield_palette(tf)
        def validar(_):
            try:
                v = float((tf.value or "").replace(",", ".")); tf.border_color = None if v >= 0 else ft.colors.RED
            except Exception:
                tf.border_color = ft.colors.RED
            self._safe_update()
        tf.on_change = validar
        key = (row.get(self.ID) if row.get(self.ID) is not None else -1)
        self._ensure_edit_map(key); self._edit_controls[key]["stock_minimo"] = tf
        return tf

    def _fmt_costo(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        return self._fmt_money_editable(value, row, key_name="costo_unitario", hint="Costo $")

    def _fmt_precio(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        return self._fmt_money_editable(value, row, key_name="precio_unitario", hint="Precio $")

    def _fmt_money_editable(self, value: Any, row: Dict[str, Any], *, key_name: str, hint: str) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        if not self._en_edicion(row):
            return ft.Text(_f2(value), size=12, color=fg)
        tf = ft.TextField(
            value=_f2(value) if value is not None and not row.get("_is_new") else "",
            hint_text=hint, keyboard_type=ft.KeyboardType.NUMBER, text_size=self.UI["tf_text_size"],
            height=self.UI["tf_height"],
            content_padding=ft.padding.symmetric(horizontal=self.UI["tf_pad_h"], vertical=self.UI["tf_pad_v"]),
        )
        self._apply_textfield_palette(tf)
        def validar(_):
            try:
                v = float((tf.value or "").replace(",", ".")); tf.border_color = None if v >= 0 else ft.colors.RED
            except Exception:
                tf.border_color = ft.colors.RED
            self._safe_update()
        tf.on_change = validar
        key = (row.get(self.ID) if row.get(self.ID) is not None else -1)
        self._ensure_edit_map(key); self._edit_controls[key][key_name] = tf
        return tf

    def _fmt_estado(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        if not self._en_edicion(row):
            return ft.Text(_txt(value), size=12, color=fg)
        dd = ft.Dropdown(
            value=value or E_INV_ESTADO.ACTIVO.value,
            options=[
                ft.dropdown.Option(E_INV_ESTADO.ACTIVO.value, "activo"),
                ft.dropdown.Option(E_INV_ESTADO.INACTIVO.value, "inactivo"),
            ],
            dense=True, width=120, height=self.UI["tf_height"],
            text_style=ft.TextStyle(size=self.UI["tf_text_size"], color=fg),
        )
        key = (row.get(self.ID) if row.get(self.ID) is not None else -1)
        self._ensure_edit_map(key); self._edit_controls[key]["estado"] = dd
        return dd

    def _ensure_edit_map(self, key: int):
        if key not in self._edit_controls:
            self._edit_controls[key] = {}

    # =========================================================
    # Actions builder (iconos por fila)
    # =========================================================
    def _actions_builder(self, row: Dict[str, Any], is_new: bool) -> ft.Control:
        rid = row.get(self.ID)

        def _btn_mov(icon, tooltip, on_click):
            return ft.IconButton(
                icon=icon,
                tooltip=tooltip,
                icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                on_click=on_click,
            )

        # Nueva fila → solo root puede aceptar/cancelar
        if is_new or bool(row.get("_is_new")) or (row.get(self.ID) in (None, "", 0)):
            if not self.is_root:
                return ft.Text("—", size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
            return ft.Row(
                [
                    ft.IconButton(icon=ft.icons.CHECK, tooltip="Aceptar",
                                  icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                                  on_click=lambda e, r=row: self._on_accept_row(r)),
                    ft.IconButton(icon=ft.icons.CLOSE, tooltip="Cancelar",
                                  icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                                  on_click=lambda e, r=row: self._on_cancel_row(r)),
                ],
                spacing=6, alignment=ft.MainAxisAlignment.START
            )

        # Edición de existente
        if self.fila_editando == rid:
            if not self.is_root:
                return ft.Text("—", size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
            return ft.Row(
                [boton_aceptar(lambda e, r=row: self._on_accept_row(r)),
                 boton_cancelar(lambda e, r=row: self._on_cancel_row(r))],
                spacing=6, alignment=ft.MainAxisAlignment.START
            )

        # Fila normal existente
        if self.is_root:
            return ft.Row(
                [
                    _btn_mov(ft.icons.NORTH_EAST, "Entrada", lambda e, r=row: self._open_mov_dialog(r, E_INV_MOV.ENTRADA.value)),
                    _btn_mov(ft.icons.SOUTH_WEST, "Salida",  lambda e, r=row: self._open_mov_dialog(r, E_INV_MOV.SALIDA.value)),
                    boton_editar(lambda e, r=row: self._on_edit_row(r)),
                    boton_borrar(lambda e, r=row: self._on_delete_row(r)),
                ],
                spacing=6, alignment=ft.MainAxisAlignment.START
            )

        # Recepcionista: sin acciones
        return ft.Text("—", size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

    # =========================================================
    # Callbacks de acciones + LOGS
    # =========================================================
    def _on_edit_row(self, row: Dict[str, Any]):
        if not self.is_root:
            return
        self.fila_editando = row.get(self.ID)
        self._edit_controls.pop(self.fila_editando if self.fila_editando is not None else -1, None)
        self._refrescar_dataset()

    def _on_delete_row(self, row: Dict[str, Any]):
        if not self.is_root:
            return
        rid = int(row.get(self.ID))
        self._confirmar_eliminar(rid)

    # Helper robusto para extraer ID de crear_producto
    def _extract_created_id(self, res: Dict[str, Any]) -> Optional[int]:
        cand = [
            res.get("id"),
            res.get("item_id"),
            res.get("new_id"),
            (res.get("data") or {}).get("id") if isinstance(res.get("data"), dict) else None,
            (res.get("data") or {}).get("item_id") if isinstance(res.get("data"), dict) else None,
            (res.get("record") or {}).get("id") if isinstance(res.get("record"), dict) else None,
            (res.get("producto") or {}).get("id") if isinstance(res.get("producto"), dict) else None,
        ]
        for v in cand:
            if v is None:
                continue
            s = str(v).strip()
            if s.isdigit():
                try:
                    return int(s)
                except Exception:
                    pass
        return None

    def _guess_new_id_after_create(
        self,
        nombre: str,
        categoria: Optional[str],
        unidad: Optional[str],
        costo: float,
        precio: float,
        minimo: float,
    ) -> Optional[int]:
        """
        Fallback cuando crear_producto no devuelve ID.
        Busca en listar() por nombre (case-insensitive) y toma el de mayor ID.
        Usa categoria/unidad como hints si están disponibles.
        """
        try:
            rows = self.model.listar(estado=None, categoria=None) or []
            nombre_norm = (nombre or "").strip().casefold()

            # Primer filtro por nombre
            cand = [r for r in rows if (str(r.get(self.NOMBRE, "")).strip().casefold() == nombre_norm)]

            # Si hay muchos, afinamos por hints (no estrictos)
            def score(r: Dict[str, any]) -> int:
                s = 0
                if (r.get(self.CATEG) or "").strip() == (categoria or "").strip():
                    s += 1
                if (r.get(self.UNIDAD) or "").strip() == (unidad or "").strip():
                    s += 1
                # Hints suaves por cercanía de números (redondeados)
                try:
                    if round(float(r.get(self.COSTO) or 0), 2) == round(float(costo or 0), 2):
                        s += 1
                except Exception:
                    pass
                try:
                    if round(float(r.get(self.PRECIO) or 0), 2) == round(float(precio or 0), 2):
                        s += 1
                except Exception:
                    pass
                try:
                    if round(float(r.get(self.MINIMO) or 0), 3) == round(float(minimo or 0), 3):
                        s += 1
                except Exception:
                    pass
                try:
                    s += int(r.get(self.ID) or 0) // 1  # favorece IDs mayores
                except Exception:
                    pass
                return s

            if not cand:
                self._log("↪ _guess_new_id_after_create: sin coincidencias por nombre.")
                return None

            cand.sort(key=score, reverse=True)
            new_id = int(cand[0].get(self.ID) or 0)
            self._log("↪ _guess_new_id_after_create: candidato =", new_id, " row:", cand[0])
            return new_id if new_id > 0 else None

        except Exception as ex:
            self._log("× _guess_new_id_after_create error:", repr(ex))
            return None


    def _on_accept_row(self, row: Dict[str, Any]):
        # Recepcionista NO puede agregar ni editar
        if not self.is_root:
            self._snack_error("❌ No tienes permisos para agregar ni editar productos.")
            return

        is_new = bool(row.get("_is_new")) or (row.get(self.ID) in (None, "", 0))

        key = (row.get(self.ID) if not is_new else -1)
        ctrls = self._edit_controls.get(key, {})

        nombre_tf: ft.TextField    = ctrls.get("nombre")            # type: ignore
        categoria_dd: ft.Dropdown  = ctrls.get("categoria")         # type: ignore
        unidad_dd: ft.Dropdown     = ctrls.get("unidad")            # type: ignore
        minimo_tf: ft.TextField    = ctrls.get("stock_minimo")      # type: ignore
        costo_tf: ft.TextField     = ctrls.get("costo_unitario")    # type: ignore
        precio_tf: ft.TextField    = ctrls.get("precio_unitario")   # type: ignore
        estado_dd: ft.Dropdown     = ctrls.get("estado")            # type: ignore
        stock_tf: ft.TextField     = ctrls.get("stock_actual")      # type: ignore

        errores = []
        nombre_val = (nombre_tf.value or "").strip() if nombre_tf else ""
        if len(nombre_val) < 2:
            if nombre_tf: nombre_tf.border_color = ft.colors.RED
            errores.append("Nombre inválido")

        def _num(tf: Optional[ft.TextField], default: float = 0.0) -> float:
            try:
                return float((tf.value or "").replace(",", ".")) if tf else default
            except Exception:
                return default

        minimo_val = _num(minimo_tf, 0.0)
        if minimo_tf and minimo_val < 0:
            minimo_tf.border_color = ft.colors.RED
            errores.append("Mínimo inválido")

        costo_val  = _num(costo_tf, 0.0)
        precio_val = _num(precio_tf, 0.0)
        stock_val  = _num(stock_tf, 0.0) if stock_tf is not None else None

        cat_val = (categoria_dd.value if categoria_dd else E_INV_CATEGORIA.INSUMO.value)
        uni_val = (unidad_dd.value if unidad_dd else E_INV_UNIDAD.PIEZA.value)
        est_val = (estado_dd.value if estado_dd else E_INV_ESTADO.ACTIVO.value)

        self._log("→ _on_accept_row",
                dict(is_new=is_new, nombre=nombre_val, categoria=cat_val,
                    unidad=uni_val, minimo=minimo_val,
                    costo=costo_val, precio=precio_val, estado=est_val,
                    stock_inicial=stock_val))

        self._safe_update()
        if errores:
            self._snack_error("❌ " + " / ".join(errores))
            self._log("× Validación fallida:", errores)
            return

        if is_new:
            # 1) crear producto (sin depender de que acepte stock_inicial)
            created_with_stock = False
            try:
                res = self.model.crear_producto(
                    nombre=nombre_val,
                    categoria=cat_val,
                    unidad=uni_val,
                    stock_minimo=minimo_val,
                    costo_unitario=costo_val,
                    precio_unitario=precio_val,
                    estado=est_val,
                    stock_inicial=(stock_val or 0.0),   # puede lanzar TypeError en tu backend
                )
                created_with_stock = True
                self._log("✔ crear_producto() con stock_inicial OK:", res)
            except TypeError as ex:
                self._log("⚠️ crear_producto() sin stock_inicial (TypeError):", repr(ex))
                res = self.model.crear_producto(
                    nombre=nombre_val,
                    categoria=cat_val,
                    unidad=uni_val,
                    stock_minimo=minimo_val,
                    costo_unitario=costo_val,
                    precio_unitario=precio_val,
                    estado=est_val,
                )
                self._log("✔ crear_producto() sin stock_inicial OK:", res)

            if res.get("status") == "success":
                # 2) obtener ID del nuevo registro
                new_id = self._extract_created_id(res)
                self._log("→ ID extraído:", new_id, "| created_with_stock:", created_with_stock)

                if new_id is None:
                    # Fallback robusto por listar()
                    new_id = self._guess_new_id_after_create(
                        nombre=nombre_val,
                        categoria=cat_val,
                        unidad=uni_val,
                        costo=costo_val,
                        precio=precio_val,
                        minimo=minimo_val,
                    )
                    self._log("↪ Fallback ID via listar():", new_id)

                # 3) si hay stock inicial y tenemos id, asentarlo
                if (stock_val and stock_val > 0):
                    if new_id is not None:
                        try:
                            r2 = self.model.ingresar_stock(new_id, stock_val, motivo="Stock inicial", usuario="ui")
                            self._log("✔ ingresar_stock(stock_inicial) resp:", r2)
                        except Exception as ex:
                            self._log("× Error ingresar_stock(stock_inicial):", repr(ex))
                            self._snack_error("❌ No se pudo registrar el stock inicial.")
                    else:
                        self._log("× No se pudo determinar el ID nuevo; stock inicial NO asentado.")
                        self._snack_error("⚠️ No se pudo determinar el ID del nuevo producto; stock inicial no asentado.")

                self.fila_nueva_en_proceso = False
                self._edit_controls.pop(-1, None)
                self._snack_ok("✅ Producto agregado.")
                self._refrescar_dataset()
            else:
                self._log("× crear_producto() error:", res)
                self._snack_error(f"❌ {res.get('message')}")
            return

        # --- Edición de existente ---
        rid = int(row.get(self.ID))
        res = self.model.actualizar_producto(
            item_id=rid,
            nombre=nombre_val,
            categoria=(categoria_dd.value if categoria_dd else None),
            unidad=(unidad_dd.value if unidad_dd else None),
            stock_minimo=minimo_val,
            costo_unitario=costo_val,
            precio_unitario=precio_val,
            estado=(estado_dd.value if estado_dd else None),
        )
        self._log("✔ actualizar_producto() resp:", res)

        # Delta de stock si root cambió valor
        if stock_tf is not None:
            try:
                actual = float(row.get(self.STOCK) or 0)
                nuevo  = float((stock_tf.value or "").replace(",", ".") or actual)
                delta  = round(nuevo - actual, 6)
                self._log(f"→ Ajuste de stock (actual={actual}, nuevo={nuevo}, delta={delta})")
                if delta > 0:
                    r_in = self.model.ingresar_stock(rid, delta, motivo="Edición stock (root)", usuario="ui")
                    self._log("✔ ingresar_stock(delta>0) resp:", r_in)
                elif delta < 0:
                    r_out = self.model.retirar_stock(rid, abs(delta), motivo="Edición stock (root)", usuario="ui")
                    self._log("✔ retirar_stock(delta<0) resp:", r_out)
            except Exception as ex:
                self._log("× Error ajustando delta de stock:", repr(ex))

        self.fila_editando = None
        if res.get("status") == "success":
            self._snack_ok("✅ Cambios guardados.")
            self._edit_controls.pop(rid, None)
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ No se pudo guardar: {res.get('message')}")

        # Recepcionista NO puede agregar ni editar
        if not self.is_root:
            self._snack_error("❌ No tienes permisos para agregar ni editar productos.")
            return

        is_new = bool(row.get("_is_new")) or (row.get(self.ID) in (None, "", 0))

        key = (row.get(self.ID) if not is_new else -1)
        ctrls = self._edit_controls.get(key, {})

        nombre_tf: ft.TextField      = ctrls.get("nombre")           # type: ignore
        categoria_dd: ft.Dropdown    = ctrls.get("categoria")        # type: ignore
        unidad_dd: ft.Dropdown       = ctrls.get("unidad")           # type: ignore
        minimo_tf: ft.TextField      = ctrls.get("stock_minimo")     # type: ignore
        costo_tf: ft.TextField       = ctrls.get("costo_unitario")   # type: ignore
        precio_tf: ft.TextField      = ctrls.get("precio_unitario")  # type: ignore
        estado_dd: ft.Dropdown       = ctrls.get("estado")           # type: ignore
        stock_tf: ft.TextField       = ctrls.get("stock_actual")     # type: ignore

        errores = []
        nombre_val = (nombre_tf.value or "").strip() if nombre_tf else ""
        if len(nombre_val) < 2:
            if nombre_tf: nombre_tf.border_color = ft.colors.RED
            errores.append("Nombre inválido")

        def _num(tf: Optional[ft.TextField], default: float = 0.0) -> float:
            try: return float((tf.value or "").replace(",", ".")) if tf else default
            except Exception: return default

        minimo_val  = _num(minimo_tf, 0.0)
        if minimo_tf and minimo_val < 0:
            minimo_tf.border_color = ft.colors.RED
            errores.append("Mínimo inválido")

        costo_val   = _num(costo_tf, 0.0)
        precio_val  = _num(precio_tf, 0.0)
        stock_val   = _num(stock_tf, 0.0) if stock_tf is not None else None

        self._log("→ _on_accept_row",
                  dict(is_new=is_new, nombre=nombre_val, categoria=(categoria_dd.value if categoria_dd else None),
                       unidad=(unidad_dd.value if unidad_dd else None), minimo=minimo_val,
                       costo=costo_val, precio=precio_val, estado=(estado_dd.value if estado_dd else None),
                       stock_inicial=stock_val))

        self._safe_update()
        if errores:
            self._snack_error("❌ " + " / ".join(errores))
            self._log("× Validación fallida:", errores)
            return

        if is_new:
            # 1) crear producto
            created_with_stock = False
            try:
                res = self.model.crear_producto(
                    nombre=nombre_val,
                    categoria=(categoria_dd.value if categoria_dd else E_INV_CATEGORIA.INSUMO.value),
                    unidad=(unidad_dd.value if unidad_dd else E_INV_UNIDAD.PIEZA.value),
                    stock_minimo=minimo_val,
                    costo_unitario=costo_val,
                    precio_unitario=precio_val,
                    estado=(estado_dd.value if estado_dd else E_INV_ESTADO.ACTIVO.value),
                    stock_inicial=(stock_val or 0.0),
                )
                created_with_stock = True
                self._log("✔ crear_producto() con stock_inicial OK:", res)
            except TypeError as ex:
                # Backend no acepta stock_inicial en esta firma
                self._log("⚠️ crear_producto() sin stock_inicial (TypeError):", repr(ex))
                res = self.model.crear_producto(
                    nombre=nombre_val,
                    categoria=(categoria_dd.value if categoria_dd else E_INV_CATEGORIA.INSUMO.value),
                    unidad=(unidad_dd.value if unidad_dd else E_INV_UNIDAD.PIEZA.value),
                    stock_minimo=minimo_val,
                    costo_unitario=costo_val,
                    precio_unitario=precio_val,
                    estado=(estado_dd.value if estado_dd else E_INV_ESTADO.ACTIVO.value),
                )
                self._log("✔ crear_producto() sin stock_inicial OK:", res)

            if res.get("status") == "success":
                new_id = self._extract_created_id(res)
                self._log("→ ID extraído:", new_id, "| created_with_stock:", created_with_stock)

                # Si la firma con stock_inicial no aplicó realmente, hacemos fallback explícito
                if stock_val and stock_val > 0:
                    if (not created_with_stock) or (new_id is not None and stock_val > 0):
                        if new_id is not None:
                            try:
                                r2 = self.model.ingresar_stock(new_id, stock_val, motivo="Stock inicial", usuario="ui")
                                self._log("✔ ingresar_stock(stock_inicial) resp:", r2)
                            except Exception as ex:
                                self._log("× Error ingresar_stock(stock_inicial):", repr(ex))
                        else:
                            self._log("× Sin ID: no se pudo asentar stock inicial en fallback")
                            self._snack_error("⚠️ El modelo no devolvió ID; no se pudo asentar el stock inicial automáticamente.")

                self.fila_nueva_en_proceso = False
                self._edit_controls.pop(-1, None)
                self._snack_ok("✅ Producto agregado.")
                self._refrescar_dataset()
            else:
                self._log("× crear_producto() error:", res)
                self._snack_error(f"❌ {res.get('message')}")
        else:
            rid = int(row.get(self.ID))
            res = self.model.actualizar_producto(
                item_id=rid,
                nombre=nombre_val,
                categoria=(categoria_dd.value if categoria_dd else None),
                unidad=(unidad_dd.value if unidad_dd else None),
                stock_minimo=minimo_val,
                costo_unitario=costo_val,
                precio_unitario=precio_val,
                estado=(estado_dd.value if estado_dd else None),
            )
            self._log("✔ actualizar_producto() resp:", res)

            # Delta de stock si root cambió valor
            if stock_tf is not None:
                try:
                    actual = float(row.get(self.STOCK) or 0)
                    nuevo  = float((stock_tf.value or "").replace(",", ".") or actual)
                    delta  = round(nuevo - actual, 6)
                    self._log(f"→ Ajuste de stock (actual={actual}, nuevo={nuevo}, delta={delta})")
                    if delta > 0:
                        r_in = self.model.ingresar_stock(rid, delta, motivo="Edición stock (root)", usuario="ui")
                        self._log("✔ ingresar_stock(delta>0) resp:", r_in)
                    elif delta < 0:
                        r_out = self.model.retirar_stock(rid, abs(delta), motivo="Edición stock (root)", usuario="ui")
                        self._log("✔ retirar_stock(delta<0) resp:", r_out)
                except Exception as ex:
                    self._log("× Error ajustando delta de stock:", repr(ex))

            self.fila_editando = None
            if res.get("status") == "success":
                self._snack_ok("✅ Cambios guardados.")
                self._edit_controls.pop(rid, None)
                self._refrescar_dataset()
            else:
                self._snack_error(f"❌ No se pudo guardar: {res.get('message')}")

    def _on_cancel_row(self, row: Dict[str, Any]):
        # Solo root cancela ediciones/nuevos (recepcionista no puede crear, por lo que no llega aquí)
        if not self.is_root:
            return
        if row.get("_is_new") or (row.get(self.ID) in (None, "", 0)):
            self.fila_nueva_en_proceso = False
            rows = self.table_builder.get_rows()
            try:
                idx = next(i for i, r in enumerate(rows) if r is row or r.get("_is_new"))
                self.table_builder.remove_row_at(idx)
            except Exception:
                pass
            self._edit_controls.pop(-1, None)
            self._safe_update()
            return

        rid = row.get(self.ID)
        self.fila_editando = None
        self._edit_controls.pop(rid if rid is not None else -1, None)
        self._refrescar_dataset()

    # =========================================================
    # Eliminar
    # =========================================================
    def _confirmar_eliminar(self, rid: int):
        if not self.is_root:
            return
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Eliminar producto?", color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            content=ft.Text(
                f"Esta acción no se puede deshacer. ID: {rid}",
                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dlg)),
                ft.ElevatedButton(
                    "Eliminar",
                    icon=ft.icons.DELETE_OUTLINE,
                    bgcolor=ft.colors.RED_600,
                    color=ft.colors.WHITE,
                    on_click=lambda e: self._do_delete(e, rid, dlg),
                ),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self._safe_update()

    def _do_delete(self, _e, rid: int, dlg: ft.AlertDialog):
        if not self.is_root:
            return
        res = self.model.eliminar_producto(int(rid))
        self.page.close(dlg)
        if res.get("status") == "success":
            self._snack_ok("✅ Producto eliminado.")
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ No se pudo eliminar: {res.get('message')}")

    # =========================================================
    # Fila NUEVA
    # =========================================================
    def _insertar_fila_nueva(self, _e=None):
        if not self.can_add:
            self._snack_error("❌ Solo el usuario root puede agregar productos.")
            return
        if self.fila_nueva_en_proceso:
            self._snack_ok("ℹ️ Ya hay un registro nuevo en proceso.")
            return
        self.fila_nueva_en_proceso = True

        nueva = {
            self.ID: None,
            self.NOMBRE: "",
            self.CATEG: E_INV_CATEGORIA.INSUMO.value,
            self.UNIDAD: E_INV_UNIDAD.PIEZA.value,
            self.STOCK: "",   # root ingresará stock inicial
            self.MINIMO: "",
            self.COSTO: "",
            self.PRECIO: "",
            self.ESTADO: E_INV_ESTADO.ACTIVO.value,
            "_is_new": True,
        }
        self._log("→ insertar_fila_nueva()", nueva)
        self.table_builder.add_row(nueva, auto_scroll=True)

    # =========================================================
    # Movimientos (diálogo rápido)
    # =========================================================
    def _open_mov_dialog(self, row: Dict[str, Any], tipo: str):
        if not self.can_move:
            self._snack_error("❌ No tienes permisos para registrar movimientos.")
            return
        if tipo not in (E_INV_MOV.ENTRADA.value, E_INV_MOV.SALIDA.value):
            self._snack_error("❌ Operación no permitida.")
            return

        rid = int(row.get(self.ID))
        nombre = row.get(self.NOMBRE, "")
        tf_qty = ft.TextField(label="Cantidad", keyboard_type=ft.KeyboardType.NUMBER, autofocus=True)
        self._apply_textfield_palette(tf_qty)

        def _do_ok(_):
            try:
                qty = float(tf_qty.value or "0")
                if qty <= 0: raise ValueError
                if tipo == E_INV_MOV.ENTRADA.value:
                    res = self.model.ingresar_stock(rid, qty, motivo="Entrada UI", usuario="ui")
                else:
                    res = self.model.retirar_stock(rid, qty, motivo="Salida UI", usuario="ui")
                self._log("✔ mov_dialog", dict(tipo=tipo, id=rid, qty=qty, resp=res))
                self.page.close(dlg)
                if res.get("status") == "success":
                    self._snack_ok("✅ Movimiento registrado.")
                    self._refrescar_dataset()
                else:
                    self._snack_error(f"❌ {res.get('message')}")
            except Exception as ex:
                self._log("× mov_dialog error:", repr(ex))
                self._snack_error("❌ Cantidad inválida.")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{tipo.title()} - {nombre}", color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            content=tf_qty,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dlg)),
                ft.ElevatedButton("Aceptar", icon=ft.icons.CHECK, on_click=_do_ok),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self._safe_update()

    # =========================================================
    # Import / Export (placeholders)
    # =========================================================
    def _on_importar(self):
        if not self.can_import_export:
            self._snack_error("❌ Solo el usuario root puede importar.")
            return
        self._snack_ok("ℹ️ Importar inventario: pendiente.")

    def _on_exportar(self):
        if not self.can_import_export:
            self._snack_error("❌ Solo el usuario root puede exportar.")
            return
        self._snack_ok("ℹ️ Exportar inventario: pendiente.")

    # =========================================================
    # Notificaciones
    # =========================================================
    def _on_low_stock_alert(self, alerta: Dict[str, Any]):
        self._snack_error(alerta.get("message", "⚠️ Stock bajo"))

    def _snack_ok(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            bgcolor=self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)),
        )
        self.page.snack_bar.open = True
        self._safe_update()

    def _snack_error(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=ft.colors.WHITE),
            bgcolor=ft.colors.RED_600,
        )
        self.page.snack_bar.open = True
        self._safe_update()

    # =========================================================
    # Table responsivo (ya afinado antes)
    # =========================================================
    def _build_table_responsive(self) -> None:
        """
        TableBuilder responsivo (afinado para ~1366px).
        -> Más aire en la columna de Acciones.
        """
        SIZING = {
            "base": {
                "id": 48, "nombre": 190, "categoria": 104, "unidad": 78,
                "stock": 80, "minimo": 80, "costo": 90, "precio": 90, "estado": 72,
            },
            "min": {
                "id": 42, "nombre": 160, "categoria": 92, "unidad": 68,
                "stock": 70, "minimo": 70, "costo": 82, "precio": 82, "estado": 64,
            },
            "scale_min": 0.52,
            "side_expanded": 240,
            "side_collapsed": 84,
            "margins": (self.UI["pad_page"] * 2) + self.UI["row_spacing"] + 16 + 12,
            "actions_est_root": 204,
            "actions_est_view": 60,
            "avail_floor": 600,
            "tight_1366": 0.97,
            "tight_1280": 0.95,
            "nombre_extra_max": 24,
        }

        if not hasattr(self, "ID"):
            self.ID       = E_INVENTARIO.ID.value
            self.NOMBRE   = E_INVENTARIO.NOMBRE.value
            self.CATEG    = E_INVENTARIO.CATEGORIA.value
            self.UNIDAD   = E_INVENTARIO.UNIDAD.value
            self.STOCK    = E_INVENTARIO.STOCK_ACTUAL.value
            self.MINIMO   = E_INVENTARIO.STOCK_MINIMO.value
            self.COSTO    = E_INVENTARIO.COSTO_UNITARIO.value
            self.PRECIO   = E_INVENTARIO.PRECIO_UNITARIO.value
            self.ESTADO   = E_INVENTARIO.ESTADO.value

        self.sort_manager = SortManager()

        page_w = float(getattr(self.page, "width", 1280) or 1280)
        side_w = SIZING["side_expanded"] if page_w >= 1100 else SIZING["side_collapsed"]
        actions_est = SIZING["actions_est_root"] if self.is_root else SIZING["actions_est_view"]

        avail = page_w - side_w - SIZING["margins"] - actions_est
        avail = max(SIZING["avail_floor"], avail)

        sum_base = sum(SIZING["base"].values())
        scale = min(1.0, max(avail / sum_base, SIZING["scale_min"]))

        if page_w <= 1366:
            scale = max(SIZING["scale_min"], scale * SIZING["tight_1366"])
        if page_w <= 1280:
            scale = max(SIZING["scale_min"], scale * SIZING["tight_1280"])

        def W(k: str) -> int:
            return max(int(SIZING["base"][k] * scale), SIZING["min"][k])

        widths = {
            "id": W("id"), "nombre": W("nombre"), "categoria": W("categoria"),
            "unidad": W("unidad"), "stock": W("stock"), "minimo": W("minimo"),
            "costo": W("costo"), "precio": W("precio"), "estado": W("estado"),
        }

        slack = int(max(0, avail - sum(widths.values())))
        if slack > 0:
            widths["nombre"] += min(slack, SIZING["nombre_extra_max"])

        self._col_w = dict(widths)

        columns = [
            {"key": self.ID,     "title": "ID",    "width": widths["id"],       "align": "center", "formatter": self._fmt_id},
            {"key": self.NOMBRE, "title": "Nombre","width": widths["nombre"],   "align": "start",  "formatter": self._fmt_nombre},
            {"key": self.CATEG,  "title": "Cat.",  "width": widths["categoria"],"align": "start",  "formatter": self._fmt_categoria},
            {"key": self.UNIDAD, "title": "Uni.",  "width": widths["unidad"],   "align": "center", "formatter": self._fmt_unidad},
            {"key": self.STOCK,  "title": "Stock", "width": widths["stock"],    "align": "end",    "formatter": self._fmt_stock},
            {"key": self.MINIMO, "title": "Mín.",  "width": widths["minimo"],   "align": "end",    "formatter": self._fmt_minimo},
            {"key": self.COSTO,  "title": "Costo", "width": widths["costo"],    "align": "end",    "formatter": self._fmt_costo},
            {"key": self.PRECIO, "title": "Precio","width": widths["precio"],   "align": "end",    "formatter": self._fmt_precio},
            {"key": self.ESTADO, "title": "Est.",  "width": widths["estado"],   "align": "start",  "formatter": self._fmt_estado},
        ]

        self.table_builder = TableBuilder(
            group="inventario",
            sort_manager=self.sort_manager,
            columns=columns,
            on_sort_change=self._on_sort_change,
            on_accept=self._on_accept_row,
            on_cancel=self._on_cancel_row,
            on_edit=self._on_edit_row,
            on_delete=self._on_delete_row,
            id_key=self.ID,
            dense_text=True,
            auto_scroll_new=True,
            actions_title="Acciones",
        )
        self.table_builder.attach_actions_builder(self._actions_builder)
