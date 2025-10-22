# app/views/containers/home/servicios/servicios_container.py
from __future__ import annotations
"""
Contenedor de UI (Flet 0.23.0) para gestionar el catálogo de Servicios en RED_BARBER_UI.

- Shell persistente: no recrea contenedores padres.
- PubSub: publica "db:refrescar_datos" tras operaciones y se suscribe para refrescar.
- Roles:
  * ROOT  → CRUD completo (Agregar / Editar / Eliminar).
  * Otros → Solo lectura (sin botón Agregar ni columna Acciones).

Detección de rol (prioridad):
  a) page.session["session_user"]["rol"]
  b) AppState().usuario.rol
  c) AppState().get_user_role()
Si no se resuelve → lectura solamente.

Adaptación flexible al modelo (ServiciosModel):
- Lectura: se intenta en orden list()/get_all()/fetch_all()/query() y fallback all()/listar().
- Soporta formatos de respuesta: lista simple, dict {"items": [...], "total": N}, tupla ([...], total).

Normalización robusta de campos por registro:
- id:         id, id_servicio, servicio_id
- nombre:     nombre, servicio, display_name
- tipo:       tipo, tipo_servicio, clave_tipo, enum.value
- precio:     precio, precio_base, costo   → Decimal
- activo:     activo (bool/0-1), estado ('activo'/'inactivo')

UI/Toolbar (alineada a la izquierda, sin título "Servicios"):
- ROOT: [Agregar servicio] [ID] [Nombre] [X limpiar]
- No-root: [ID] [Nombre] [X limpiar]

Edición en línea (sin modal):
- Agregar: inserta fila nueva editable arriba.
- Editar: convierte la fila en controles in-row.
- Aceptar/Cancelar por fila.
- Confirmación de borrado con diálogo ligero.

Python 3.12.7 — Español en etiquetas y logs — sin dependencias nuevas.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple

import flet as ft

# Estado / Tema
from app.config.application.app_state import AppState

# Modelo y apoyo de roles
from app.models.servicios_model import ServiciosModel  # API flexible
from app.core.enums.e_servicios import E_SERV_TIPO
try:
    from app.models.usuarios_model import UsuariosModel
except Exception:
    UsuariosModel = None  # opcional

# Modal de alerta (si existe)
try:
    from app.views.modals.modal_alert import ModalAlert
except Exception:
    ModalAlert = None

# Layout (shell) opcional
try:
    from app.views.containers.nvar.layout_controller import LayoutController
except Exception:
    LayoutController = None


# ==============================
# Helpers locales
# ==============================
def _txt(v: Any) -> str:
    return "" if v is None else str(v)

def _bool(v: Any) -> bool:
    try:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            vv = v.strip().lower()
            if vv in ("1", "true", "sí", "si", "activo", "on"):
                return True
            if vv in ("0", "false", "no", "inactivo", "off"):
                return False
        return bool(int(v))
    except Exception:
        return False

def _to_decimal(s: str) -> Decimal:
    s = (s or "").strip().replace(",", ".")
    if s == "":
        return Decimal("0")
    return Decimal(s)


class ServiciosContainer(ft.UserControl):
    """
    Contenedor principal de Servicios.
    """

    # Claves canónicas del contenedor (tras normalización)
    ID = "id"
    NOMBRE = "nombre"
    TIPO = "tipo"
    PRECIO = "precio"        # Decimal
    ACTIVO = "activo"        # bool

    TOPIC_REFRESH = "db:refrescar_datos"

    # Key para opción "Otro" en Tipo
    OPT_OTRO = "__OTRO__"

    def __init__(self):
        super().__init__()

        # Core / theme
        self.app_state = AppState()
        self.page = getattr(self.app_state, "get_page", lambda: None)() or getattr(self.app_state, "page", None)
        self.colors = self._resolve_colors()

        # UI knobs (compacto/denso)
        self.UI: Dict[str, Any] = dict(
            pad_page=16,
            row_spacing=6,
            row_run_spacing=6,
            tf_height=36,
            tf_text_size=12,
            tf_label_size=11,
            tf_pad_h=8,
            tf_pad_v=4,
            icon_btn=18,
            w_buscar=260,
            w_id=140,
            table_max_w=900,
        )

        # Permisos
        self._rol: Optional[str] = None
        self._is_root: bool = False
        self._can_edit: bool = False

        # Modelo
        self.model = ServiciosModel()

        # Dataset
        self._raw: List[Any] = []                # respuesta cruda del modelo
        self._data: List[Dict[str, Any]] = []    # normalizados
        self._filtered: List[Dict[str, Any]] = []
        self._total: Optional[int] = None
        self._sort_nombre_asc: bool = True

        # Filtros
        self._filter_id: Optional[int] = None
        self._filter_name: str = ""

        # Edición in-row
        self._row_editing_key: Optional[int] = None       # id o id temporal (negativo)
        self._new_row_active: bool = False
        self._tmp_id_seed: int = -1
        self._edit_controls: Dict[int, Dict[str, ft.Control]] = {}

        # UI refs
        self._table: Optional[ft.DataTable] = None
        # Contenedor centrado para la tabla
        self._table_container = ft.Container(
            expand=True,
            content=ft.Row([], alignment=ft.MainAxisAlignment.CENTER),
        )
        self._header_row: Optional[ft.Row] = None
        self._dialog: Optional[ft.AlertDialog] = None  # solo para confirmar borrado

        # Toolbar controls (ID + Nombre)
        self._id_tf = ft.TextField(
            label="ID",
            hint_text="ID",
            width=self.UI["w_id"],
            height=self.UI["tf_height"],
            text_size=self.UI["tf_text_size"],
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._on_filters_change,
        )
        self._apply_textfield_palette(self._id_tf)

        self._nombre_tf = ft.TextField(
            label="Buscar por nombre",
            hint_text="Escribe un nombre…",
            width=self.UI["w_buscar"],
            height=self.UI["tf_height"],
            text_size=self.UI["tf_text_size"],
            on_change=self._on_filters_change,
        )
        self._apply_textfield_palette(self._nombre_tf)

        self._btn_clear_filters = ft.IconButton(
            icon=ft.icons.CLEAR,
            tooltip="Limpiar filtros",
            icon_size=self.UI["icon_btn"],
            on_click=lambda e: self._clear_filters(),
        )

        self._btn_agregar: Optional[ft.Control] = None

        # Resolver rol antes de construir toolbar
        self._resolver_rol_usuario()

        # Botón agregar (visible solo para root) → inserta fila nueva inline
        self._btn_agregar = ft.FilledTonalButton(
            text="Agregar servicio",
            icon=ft.icons.ADD,
            on_click=lambda e: self._insertar_fila_nueva(),
            disabled=not self._is_root,
        )

        # PubSub
        self._pubsub_unsub: Optional[Callable[[], None]] = None

        # Shell layout opcional
        self.layout_ctrl = LayoutController() if LayoutController else None
        self._layout_listener = None

    # ---------------- Ciclo de vida ----------------
    def did_mount(self):
        self._resolver_rol_usuario()
        print(f"[Servicios][ROL] rol_resuelto={self._rol} is_root={self._is_root}")
        if self._btn_agregar:
            self._btn_agregar.disabled = not self._is_root

        self._subscribe_pubsub()
        self._cargar_datos()
        self._repaint_table()

        if self.layout_ctrl and not self._layout_listener:
            def _on_layout_change(_expanded: bool):
                try:
                    self.update()
                except Exception:
                    pass
            self._layout_listener = _on_layout_change
            try:
                self.layout_ctrl.add_listener(self._layout_listener)
            except Exception:
                self._layout_listener = None

    def will_unmount(self):
        if self.layout_ctrl and self._layout_listener:
            try:
                self.layout_ctrl.remove_listener(self._layout_listener)
            except Exception:
                pass
            self._layout_listener = None

        if self._pubsub_unsub:
            try:
                self._pubsub_unsub()
            except Exception:
                pass
            self._pubsub_unsub = None

    # ---------------- Build ----------------
    def build(self) -> ft.Control:
        header = self._build_header()
        self._build_table()
        return ft.Container(
            expand=True,
            bgcolor=self.colors.get("BG_COLOR") if self.colors else None,
            padding=self.UI["pad_page"],
            content=ft.Column(
                expand=True,
                spacing=8,
                controls=[
                    header,
                    ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT) if self.colors else None),
                    self._table_container,
                ],
            ),
        )

    # =========================================================
    # Header / Tabla
    # =========================================================
    def _build_header(self) -> ft.Control:
        # Construcción de fila de filtros
        filtros_row_controls: List[ft.Control] = [self._id_tf, self._nombre_tf, self._btn_clear_filters]

        if self._is_root:
            # ROOT: agregar + filtros, todos alineados a la izquierda
            header_controls = [self._btn_agregar, *filtros_row_controls]
            header = ft.Row(
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=self.UI["row_spacing"] + 2,
                controls=header_controls,
            )
            self._log("[Servicios][HEADER] render=root_toolbar")
        else:
            # No-root: sólo filtros
            header = ft.Row(
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=self.UI["row_spacing"] + 2,
                controls=filtros_row_controls,
            )
            self._log("[Servicios][HEADER] render=recep_toolbar")

        self._header_row = header
        return header

    def _build_table(self) -> ft.Control:
        cols: List[ft.DataColumn] = [
            ft.DataColumn(ft.Text("ID", size=12, color=self.colors.get("TABLE_HEADER_TXT", None))),
            ft.DataColumn(
                label=ft.Row(
                    spacing=6,
                    controls=[
                        ft.Text("Nombre", size=12, color=self.colors.get("TABLE_HEADER_TXT", None)),
                        ft.IconButton(
                            icon=ft.icons.SORT_BY_ALPHA,
                            tooltip="Ordenar por nombre",
                            icon_size=16,
                            on_click=lambda e: self._toggle_sort_nombre(),
                        ),
                    ],
                )
            ),
            ft.DataColumn(ft.Text("Tipo", size=12, color=self.colors.get("TABLE_HEADER_TXT", None))),
            ft.DataColumn(ft.Text("Precio", size=12, color=self.colors.get("TABLE_HEADER_TXT", None))),
            ft.DataColumn(ft.Text("Activo", size=12, color=self.colors.get("TABLE_HEADER_TXT", None))),
        ]
        if self._is_root:
            cols.append(ft.DataColumn(ft.Text("Acciones", size=12, color=self.colors.get("TABLE_HEADER_TXT", None))))

        self._table = ft.DataTable(
            columns=cols,
            rows=[],
            heading_row_color=self.colors.get("TABLE_HEADER_BG", self.colors.get("CARD_BG", ft.colors.SURFACE_VARIANT)) if self.colors else None,
            data_row_min_height=38,
            divider_thickness=1,
            heading_text_style=ft.TextStyle(size=12, weight=ft.FontWeight.W_600, color=self.colors.get("TABLE_HEADER_TXT", None)),
            column_spacing=24,
        )
        # Centrar tabla: colocarla dentro de un Row centrado
        self._table_container.content = ft.Row(
            controls=[ft.Container(self._table, width=self.UI["table_max_w"])],
            alignment=ft.MainAxisAlignment.CENTER,
        )
        return self._table_container

    # ======= Celdas (vista) =======
    def _build_tipo_tag(self, tipo_val: str) -> ft.Control:
        bg = self.colors.get("TYPE_TAG_BG", ft.colors.with_opacity(0.08, ft.colors.RED_600))
        fg = self.colors.get("TYPE_TAG_TXT", self.colors.get("FG_COLOR"))
        return ft.Container(
            bgcolor=bg,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=12,
            content=ft.Text(_txt(tipo_val), size=11, color=fg),
        )

    def _build_price_cell(self, precio_txt: str) -> ft.Control:
        bg = self.colors.get("PRICE_BG", None)
        fg = self.colors.get("PRICE_TXT", None)
        if not bg and not fg:
            return ft.Text(precio_txt, size=12, color=self.colors.get("FG_COLOR"))
        return ft.Container(
            bgcolor=bg,
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            content=ft.Text(precio_txt, size=12, weight=ft.FontWeight.W_500, color=fg or self.colors.get("FG_COLOR")),
        )

    # ======= Helpers edición in-row =======
    def _row_key(self, r: Dict[str, Any]) -> int:
        rid = r.get(self.ID)
        if isinstance(rid, int):
            return rid
        return int(r.get("_temp_id"))

    def _is_new(self, r: Dict[str, Any]) -> bool:
        return bool(r.get("_is_new"))

    def _en_edicion(self, r: Dict[str, Any]) -> bool:
        if self._row_editing_key is None:
            return False
        key = self._row_key(r)
        return key == self._row_editing_key

    def _ensure_edit_map(self, key: int) -> Dict[str, ft.Control]:
        if key not in self._edit_controls:
            self._edit_controls[key] = {}
        return self._edit_controls[key]

    def _build_tipo_dropdown(self, value: Optional[str], key: int, on_change_cb: Callable[[Any], None]) -> ft.Dropdown:
        opts = [ft.dropdown.Option(t.value, t.value.replace("_", " ").lower()) for t in E_SERV_TIPO]
        opts.append(ft.dropdown.Option(self.OPT_OTRO, "Otro (escribir)"))
        dd = ft.Dropdown(
            value=(value if value in [t.value for t in E_SERV_TIPO] else self.OPT_OTRO) if value else None,
            options=opts,
            width=220,
            height=self.UI["tf_height"],
            dense=True,
            text_style=ft.TextStyle(size=self.UI["tf_text_size"]),
            on_change=on_change_cb,
        )
        return dd

    def _fmt_nombre_edit(self, r: Dict[str, Any], key: int) -> ft.Control:
        tf = ft.TextField(
            value=_txt(r.get(self.NOMBRE)),
            height=self.UI["tf_height"],
            text_size=self.UI["tf_text_size"],
            autofocus=self._is_new(r),
        )
        self._apply_textfield_palette(tf)
        self._ensure_edit_map(key)["tf_nombre"] = tf
        return tf

    def _fmt_tipo_edit(self, r: Dict[str, Any], key: int) -> ft.Control:
        current = _txt(r.get(self.TIPO)) or ""
        mp = self._ensure_edit_map(key)

        def _on_dd_change(_e=None):
            custom.visible = (dd.value == self.OPT_OTRO)
            self.update()

        dd = self._build_tipo_dropdown(current, key, _on_dd_change)
        mp["dd_tipo"] = dd

        # Campo "Otro"
        custom_init = "" if current in [t.value for t in E_SERV_TIPO] else current
        custom = ft.TextField(
            value=custom_init,
            height=self.UI["tf_height"],
            text_size=self.UI["tf_text_size"],
            visible=(not current or current not in [t.value for t in E_SERV_TIPO]),
        )
        self._apply_textfield_palette(custom)
        mp["tf_tipo_custom"] = custom

        return ft.Row(spacing=8, controls=[dd, custom])

    def _fmt_precio_edit(self, r: Dict[str, Any], key: int) -> ft.Control:
        try:
            val = f"{Decimal(str(r.get(self.PRECIO, '0'))):.2f}"
        except Exception:
            val = ""
        tf = ft.TextField(
            value=val,
            height=self.UI["tf_height"],
            text_size=self.UI["tf_text_size"],
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._apply_textfield_palette(tf)
        self._ensure_edit_map(key)["tf_precio"] = tf
        return tf

    def _fmt_activo_edit(self, r: Dict[str, Any], key: int) -> ft.Control:
        sw = ft.Switch(value=bool(r.get(self.ACTIVO, True)), scale=0.9, disabled=not self._is_root)
        self._ensure_edit_map(key)["sw_activo"] = sw
        return sw

    def _mark_invalid(self, ctl: ft.TextField, invalid: bool):
        ctl.border_color = ft.colors.RED if invalid else None

    def _validate_row_controls(self, key: int) -> Tuple[bool, Dict[str, str]]:
        mp = self._edit_controls.get(key, {})
        errors: Dict[str, str] = {}

        tf_nombre: ft.TextField = mp.get("tf_nombre")
        dd_tipo: ft.Dropdown = mp.get("dd_tipo")
        tf_tipo_custom: ft.TextField = mp.get("tf_tipo_custom")
        tf_precio: ft.TextField = mp.get("tf_precio")

        # nombre
        nombre_ok = tf_nombre and len((tf_nombre.value or "").strip()) >= 1
        self._mark_invalid(tf_nombre, not nombre_ok)
        if not nombre_ok:
            errors["nombre"] = "Requerido."

        # tipo
        tipo_ok = True
        if dd_tipo and dd_tipo.value == self.OPT_OTRO:
            tipo_ok = tf_tipo_custom and len((tf_tipo_custom.value or "").strip()) >= 1
            self._mark_invalid(tf_tipo_custom, not tipo_ok)
            if not tipo_ok:
                errors["tipo"] = "Especifica el tipo."

        # precio
        precio_ok = True
        try:
            p = _to_decimal(tf_precio.value or "0") if tf_precio else Decimal("0")
            if p < Decimal("0"):
                precio_ok = False
        except InvalidOperation:
            precio_ok = False
        self._mark_invalid(tf_precio, not precio_ok)
        if not precio_ok:
            errors["precio"] = "Decimal inválido (>= 0)."

        return (nombre_ok and tipo_ok and precio_ok), errors

    def _collect_patch(self, key: int) -> Dict[str, Any]:
        mp = self._edit_controls.get(key, {})
        tf_nombre: ft.TextField = mp.get("tf_nombre")
        dd_tipo: ft.Dropdown = mp.get("dd_tipo")
        tf_tipo_custom: ft.TextField = mp.get("tf_tipo_custom")
        tf_precio: ft.TextField = mp.get("tf_precio")
        sw_activo: ft.Switch = mp.get("sw_activo")

        tipo = (tf_tipo_custom.value or "").strip() if (dd_tipo and dd_tipo.value == self.OPT_OTRO) else ((dd_tipo.value or "").strip() if dd_tipo else "")
        precio = _to_decimal(tf_precio.value or "0") if tf_precio else Decimal("0")
        activo = 1 if (sw_activo.value if sw_activo else True) else 0

        return {
            self.NOMBRE: (tf_nombre.value or "").strip(),
            self.TIPO: tipo,
            self.PRECIO: precio,  # ¡mantener Decimal!
            self.ACTIVO: activo,
        }

    # ======= Filas =======
    def _row_for_service(self, s: Dict[str, Any]) -> ft.DataRow:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE) if self.colors else None
        idv = s.get(self.ID)
        key = self._row_key(s)
        is_edit = self._en_edicion(s)

        # Log fila
        self._log(f"[Servicios][ROW] acciones_render={self._is_root} id={idv if idv is not None else 'new'}")

        # Vista normal
        if not is_edit:
            try:
                precio_txt = f"{Decimal(str(s.get(self.PRECIO, '0'))):.2f}"
            except Exception:
                precio_txt = "—"

            cells: List[ft.DataCell] = [
                ft.DataCell(ft.Text(_txt(idv) if idv is not None else "—", size=12, color=fg)),
                ft.DataCell(ft.Text(_txt(s.get(self.NOMBRE, "—")), size=12, color=fg)),
                ft.DataCell(self._build_tipo_tag(_txt(s.get(self.TIPO, "—")))),
                ft.DataCell(self._build_price_cell(precio_txt)),
                ft.DataCell(
                    ft.Icon(ft.icons.CHECK_CIRCLE, size=16, color=ft.colors.GREEN_400)
                    if bool(s.get(self.ACTIVO, True)) else ft.Icon(ft.icons.CANCEL, size=16, color=ft.colors.RED_400)
                ),
            ]
            if self._is_root:
                actions = ft.Row(
                    spacing=6,
                    controls=[
                        ft.IconButton(
                            icon=ft.icons.EDIT,
                            tooltip="Editar",
                            icon_size=18,
                            on_click=lambda e, item=s: self._on_edit_row(item),
                        ),
                        ft.IconButton(
                            icon=ft.icons.DELETE,
                            tooltip="Eliminar",
                            icon_size=18,
                            on_click=lambda e, item=s: self._confirm_delete(item),
                        ),
                    ],
                )
                cells.append(ft.DataCell(actions))
            return ft.DataRow(cells=cells)

        # Modo edición (in-row)
        mp = self._ensure_edit_map(key)
        cells_edit: List[ft.DataCell] = [
            ft.DataCell(ft.Text(_txt(idv) if idv is not None else "Nuevo", size=12, color=fg)),
            ft.DataCell(self._fmt_nombre_edit(s, key)),
            ft.DataCell(self._fmt_tipo_edit(s, key)),
            ft.DataCell(self._fmt_precio_edit(s, key)),
            ft.DataCell(self._fmt_activo_edit(s, key)),
        ]

        # Acciones edición
        if self._is_root:
            actions_edit = ft.Row(
                spacing=6,
                controls=[
                    ft.IconButton(
                        icon=ft.icons.CHECK,
                        tooltip="Aceptar",
                        icon_size=18,
                        on_click=lambda e, item=s: self._on_accept_row(item),
                    ),
                    ft.IconButton(
                        icon=ft.icons.CLOSE,
                        tooltip="Cancelar",
                        icon_size=18,
                        on_click=lambda e, item=s: self._on_cancel_row(item),
                    ),
                ],
            )
            cells_edit.append(ft.DataCell(actions_edit))

        return ft.DataRow(cells=cells_edit)

    # =========================================================
    # Dataset / filtros / orden / render
    # =========================================================
    def _cargar_datos(self):
        try:
            # Sólo pasamos q si hay filtro por nombre; ID se aplica client-side
            qvalue = (self._filter_name or "").strip() or None
            items, total, metodo = self._fetch_servicios(
                q=qvalue,
                activo=None,  # traemos todos y filtramos client-side si hace falta
            )
            self._log(f"[Servicios] método_lectura={metodo} filtros={{'q': {bool(qvalue)}, 'activo': None}}")
            self._raw = items or []
            # normalizar
            normalized: List[Dict[str, Any]] = []
            for it in (self._raw or []):
                try:
                    norm = self._normalize_service(it)
                    normalized.append(norm)
                except Exception as _ex:
                    self._log(f"[Servicios] normalize: error en item → {_ex}")
            self._data = normalized
            self._total = total
            self._aplicar_filtro_y_orden()
            self._repaint_table()
            self._log(f"INFO: datos cargados → {len(self._data)}")
        except Exception as ex:
            self._data, self._filtered = [], []
            self._error_modal_o_snack(f"Error cargando servicios: {ex}")

    def _aplicar_filtro_y_orden(self):
        fid = self._filter_id
        q = (self._filter_name or "").strip().lower()

        def _matches(r: Dict[str, Any]) -> bool:
            if isinstance(fid, int) and r.get(self.ID) != fid:
                # permitir ver la fila nueva aunque no matche el filtro
                return self._is_new(r)
            if q:
                nombre = str(r.get(self.NOMBRE, "")).lower()
                if q not in nombre and not self._is_new(r):
                    return False
            return True

        self._filtered = [r for r in self._data if _matches(r)]

        # Orden por nombre (fila nueva al inicio)
        self._filtered.sort(key=lambda r: (0 if self._is_new(r) else 1, str(r.get(self.NOMBRE, "")).lower()), reverse=not self._sort_nombre_asc)

    def _repaint_table(self):
        if not self._table:
            return
        try:
            self._table.rows = [self._row_for_service(r) for r in self._filtered]
            self.update()
        except Exception:
            pass

    def _toggle_sort_nombre(self):
        self._sort_nombre_asc = not self._sort_nombre_asc
        self._aplicar_filtro_y_orden()
        self._repaint_table()

    # --- Filtros (ID + Nombre) ---
    def _on_filters_change(self, e: ft.ControlEvent):
        id_raw = (self._id_tf.value or "").strip()
        name_raw = (self._nombre_tf.value or "").strip()

        try:
            self._filter_id = int(id_raw) if id_raw != "" else None
        except Exception:
            self._filter_id = None

        self._filter_name = name_raw

        self._aplicar_filtro_y_orden()
        self._repaint_table()

        count_ref = len(self._filtered or self._data)
        self._log(f"[Servicios][SEARCH] id={self._filter_id if self._filter_id is not None else ''} q='{self._filter_name or ''}' count={count_ref}")

    def _clear_filters(self):
        self._id_tf.value = ""
        self._nombre_tf.value = ""
        self._filter_id = None
        self._filter_name = ""
        self._aplicar_filtro_y_orden()
        self._repaint_table()

    # =========================================================
    # Edición inline: agregar / editar / aceptar / cancelar
    # =========================================================
    def _insertar_fila_nueva(self):
        if not self._is_root:
            return
        if self._row_editing_key is not None or self._new_row_active:
            self._error_modal_o_snack("Hay una edición en curso. Cancela o acepta antes de crear otra.")
            return

        temp_id = self._tmp_id_seed
        self._tmp_id_seed -= 1

        nueva = {
            self.ID: None,
            self.NOMBRE: "",
            self.TIPO: "",
            self.PRECIO: Decimal("0"),
            self.ACTIVO: True,
            "_is_new": True,
            "_temp_id": temp_id,
        }

        # Insertar al inicio de _data
        self._data.insert(0, nueva)
        self._new_row_active = True
        self._row_editing_key = temp_id

        # Recalcular filtros pero siempre manteniendo la nueva visible
        self._aplicar_filtro_y_orden()
        # Forzar nueva al inicio de _filtered
        self._filtered = [r for r in self._filtered if r is not nueva]
        self._filtered.insert(0, nueva)

        self._log("[Servicios][EDIT] inline start id=new")
        self._repaint_table()

    def _on_edit_row(self, item: Dict[str, Any]):
        if not self._is_root:
            return
        if self._row_editing_key is not None:
            self._error_modal_o_snack("Ya hay una fila en edición. Acepta o cancela primero.")
            return
        key = self._row_key(item)
        self._row_editing_key = key
        self._new_row_active = False
        self._log(f"[Servicios][EDIT] inline start id={item.get(self.ID)}")
        self._repaint_table()

    def _on_cancel_row(self, item: Dict[str, Any]):
        key = self._row_key(item)
        is_new = self._is_new(item)
        self._log(f"[Servicios][EDIT] inline cancel id={'new' if is_new else item.get(self.ID)}")

        # Limpiar refs
        if key in self._edit_controls:
            self._edit_controls.pop(key, None)

        if is_new:
            # Quitar la fila temporal
            try:
                self._data = [r for r in self._data if r is not item]
            except Exception:
                pass
            self._new_row_active = False

        self._row_editing_key = None
        self._aplicar_filtro_y_orden()
        self._repaint_table()

    def _on_accept_row(self, item: Dict[str, Any]):
        if not self._is_root:
            return
        key = self._row_key(item)
        ok, errors = self._validate_row_controls(key)
        if not ok:
            self._error_modal_o_snack("Revisa los campos marcados en rojo.")
            self.update()
            return

        patch = self._collect_patch(key)
        try:
            if self._is_new(item):
                res, used = self._model_create(patch, return_used=True)
                self._log(f"[Servicios][SAVE] method={used} id=new patch={patch}")
            else:
                sid = int(item.get(self.ID))
                res, used = self._model_update(sid, patch, return_used=True)
                self._log(f"[Servicios][SAVE] method={used} id={sid} patch={patch}")

            if self._is_ok(res):
                self._publish_refresh()
                # Limpiar estado de edición
                self._edit_controls.pop(key, None)
                self._row_editing_key = None
                self._new_row_active = False
                # Recargar dataset desde backend
                self._cargar_datos()
            else:
                raise RuntimeError(self._err_msg(res))
        except Exception as ex:
            self._log(f"[Servicios][ERROR] {ex}")
            self._error_modal_o_snack(f"Error al guardar: {ex}")

    # =========================================================
    # Confirmación de borrado
    # =========================================================
    def _confirm_delete(self, item: Dict[str, Any]):
        if not self._is_root:
            return
        if self._is_new(item):
            # Si es nueva sin persistir, simplemente cancelar
            self._on_cancel_row(item)
            return

        sid = int(item.get(self.ID))

        def _do_delete(_e=None):
            try:
                res = self._model_delete(sid)
                if self._is_ok(res):
                    self._publish_refresh()
                    self._cargar_datos()
                else:
                    raise RuntimeError(self._err_msg(res))
            except Exception as ex:
                self._log(f"[Servicios][ERROR] {ex}")
                self._error_modal_o_snack(f"Error al eliminar: {ex}")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar eliminación"),
            content=ft.Text(f"¿Eliminar el servicio #{sid}? Esta acción no se puede deshacer."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_dialog()),
                ft.FilledButton("Eliminar", icon=ft.icons.DELETE, on_click=lambda e: (self._close_dialog(), _do_delete())),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._dialog = dlg
        self.page.dialog = dlg
        try:
            dlg.open = True
            self.page.update()
        except Exception:
            pass

    def _close_dialog(self):
        if self._dialog:
            try:
                self._dialog.open = False
                self.page.update()
            except Exception:
                pass
            self._dialog = None

    # =========================================================
    # Modelo: API flexible (create/update/delete)
    # =========================================================
    def _model_create(self, data: Dict[str, Any], *, return_used: bool = False):
        used = "none"
        # Preferir create(data)
        if hasattr(self.model, "create") and callable(getattr(self.model, "create")):
            used = "create"
            res = self.model.create({
                "nombre": data.get(self.NOMBRE),
                "tipo": data.get(self.TIPO),
                # map a precio_base sin convertir a float
                "precio_base": data.get(self.PRECIO),
                "activo": data.get(self.ACTIVO, 1),
                "monto_libre": 0,
            })
            return (res, used) if return_used else res
        # add(...)
        if hasattr(self.model, "add") and callable(getattr(self.model, "add")):
            used = "add"
            try:
                res = self.model.add(
                    nombre=data.get(self.NOMBRE),
                    tipo=data.get(self.TIPO),
                    precio=data.get(self.PRECIO),
                    activo=data.get(self.ACTIVO, 1),
                    monto_libre=0,
                )
            except TypeError:
                res = self.model.add({
                    "nombre": data.get(self.NOMBRE),
                    "tipo": data.get(self.TIPO),
                    "precio": data.get(self.PRECIO),
                    "activo": data.get(self.ACTIVO, 1),
                    "monto_libre": 0,
                })
            return (res, used) if return_used else res
        # crear_servicio(...)
        if hasattr(self.model, "crear_servicio") and callable(getattr(self.model, "crear_servicio")):
            used = "crear_servicio"
            try:
                res = self.model.crear_servicio(
                    nombre=data.get(self.NOMBRE),
                    tipo=data.get(self.TIPO),
                    precio_base=data.get(self.PRECIO),
                    monto_libre=0,
                    activo=data.get(self.ACTIVO, 1),
                )
            except TypeError:
                # sin kwargs opcionales
                res = self.model.crear_servicio(
                    nombre=data.get(self.NOMBRE),
                    tipo=data.get(self.TIPO),
                    precio_base=data.get(self.PRECIO),
                    activo=data.get(self.ACTIVO, 1),
                )
            return (res, used) if return_used else res
        res = {"status": "error", "message": "API de creación no disponible."}
        return (res, used) if return_used else res

    def _model_update(self, sid: int, patch: Dict[str, Any], *, return_used: bool = False):
        used = "none"
        # update(id, patch) o update(id, **patch)
        if hasattr(self.model, "update") and callable(getattr(self.model, "update")):
            try:
                res = self.model.update(sid, patch)
                used = "update(dict)"
            except TypeError:
                res = self.model.update(sid, **self._to_model_patch(patch))
                used = "update(kwargs)"
            return (res, used) if return_used else res
        # edit(id, patch) o edit(id, **patch)
        if hasattr(self.model, "edit") and callable(getattr(self.model, "edit")):
            try:
                res = self.model.edit(sid, patch)
                used = "edit(dict)"
            except TypeError:
                res = self.model.edit(sid, **self._to_model_patch(patch))
                used = "edit(kwargs)"
            return (res, used) if return_used else res
        # patch(id, **patch) — fallback genérico si existiera
        if hasattr(self.model, "patch") and callable(getattr(self.model, "patch")):
            res = self.model.patch(sid, **self._to_model_patch(patch))
            used = "patch(kwargs)"
            return (res, used) if return_used else res
        # actualizar_servicio(...)
        if hasattr(self.model, "actualizar_servicio") and callable(getattr(self.model, "actualizar_servicio")):
            res = self.model.actualizar_servicio(
                sid,
                nombre=patch.get(self.NOMBRE),
                tipo=patch.get(self.TIPO),
                precio_base=patch.get(self.PRECIO),
                activo=patch.get(self.ACTIVO),
            )
            used = "actualizar_servicio"
            return (res, used) if return_used else res
        res = {"status": "error", "message": "API de actualización no disponible."}
        return (res, used) if return_used else res

    def _to_model_patch(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Mapea claves del contenedor a posibles nombres del modelo."""
        mp: Dict[str, Any] = {}
        if self.NOMBRE in patch: mp["nombre"] = patch[self.NOMBRE]
        if self.TIPO in patch:   mp["tipo"] = patch[self.TIPO]
        if self.PRECIO in patch: mp["precio"] = patch[self.PRECIO]  # el modelo lo normaliza a precio_base
        if self.ACTIVO in patch: mp["activo"] = patch[self.ACTIVO]
        return mp

    def _model_delete(self, sid: int) -> Dict[str, Any]:
        if hasattr(self.model, "delete") and callable(getattr(self.model, "delete")):
            return self.model.delete(sid)
        if hasattr(self.model, "remove") and callable(getattr(self.model, "remove")):
            return self.model.remove(sid)
        if hasattr(self.model, "eliminar_servicio") and callable(getattr(self.model, "eliminar_servicio")):
            return self.model.eliminar_servicio(sid)
        return {"status": "error", "message": "API de eliminación no disponible."}

    # =========================================================
    # Lectura flexible + normalización
    # =========================================================
    def _fetch_servicios(
        self,
        *,
        q: Optional[str] = None,
        activo: Optional[bool] = None,
        tipo: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[Any], Optional[int], str]:
        """
        Intenta leer con:
            list(**filtros) → get_all(**filtros) → fetch_all(**filtros) → query(**filtros) → all() → listar()
        Soporta formatos:
            - lista simple
            - dict {"items":[...], "total":N, ...}
            - tupla ([...], total)
        Devuelve: (items, total|None, metodo_usado)
        """
        filtros: Dict[str, Any] = {}
        if activo is not None:
            filtros["activo"] = activo
        if tipo:
            filtros["tipo"] = tipo
        if q:
            filtros["q"] = q
            filtros["search"] = q  # posibles nombres
        if limit is not None:
            filtros["limit"] = limit
        if offset is not None:
            filtros["offset"] = offset

        def _extract(res: Any) -> Tuple[List[Any], Optional[int]]:
            if isinstance(res, dict) and "items" in res:
                return list(res.get("items") or []), (res.get("total") if isinstance(res.get("total"), int) else None)
            if isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], list):
                return list(res[0]), (res[1] if isinstance(res[1], int) else None)
            if isinstance(res, list):
                return list(res), None
            return [], None

        def _try(method_name: str, kmap: Optional[Dict[str, str]] = None) -> Optional[Tuple[List[Any], Optional[int], str]]:
            if not hasattr(self.model, "method_name") and not hasattr(self.model, method_name):
                return None
            fn = getattr(self.model, method_name)
            if not callable(fn):
                return None

            kwargs = {}
            for k, v in filtros.items():
                if v is None:
                    continue
                key = k
                if kmap and k in kmap:
                    key = kmap[k]
                kwargs[key] = v

            try:
                res = fn(**kwargs) if kwargs else fn()
                items, total = _extract(res)
                return items, total, method_name
            except TypeError:
                reduced = {}
                for k in ("activo", "search", "q", "tipo", "limit", "offset"):
                    if k in kwargs:
                        reduced[k] = kwargs[k]
                try:
                    res = fn(**reduced) if reduced else fn()
                    items, total = _extract(res)
                    return items, total, method_name
                except TypeError:
                    res = fn()
                    items, total = _extract(res)
                    return items, total, method_name
            except Exception:
                return None

        # 1) list
        out = _try("list") or _try("list", {"q": "search"}) or _try("list", {"q": "nombre__icontains"})
        if out:
            return out
        # 2) get_all
        out = _try("get_all") or _try("get_all", {"q": "search"}) or _try("get_all", {"q": "nombre__icontains"})
        if out:
            return out
        # 3) fetch_all
        out = _try("fetch_all") or _try("fetch_all", {"q": "search"}) or _try("fetch_all", {"q": "nombre__icontains"})
        if out:
            return out
        # 4) query
        out = _try("query") or _try("query", {"q": "search"}) or _try("query", {"q": "nombre__icontains"})
        if out:
            return out
        # 5) all (sin filtros)
        out = _try("all")
        if out:
            return out
        # 6) fallback listar()
        if hasattr(self.model, "listar") and callable(getattr(self.model, "listar")):
            try:
                res = self.model.listar(activo=activo, search=q)
            except TypeError:
                res = self.model.listar()
            items, total = _extract(res)
            return items, total, "listar"

        return [], None, "none"

    def _normalize_service(self, item: Any) -> Dict[str, Any]:
        """
        Normaliza un registro de servicio a las claves canónicas:
        {id, nombre, tipo, precio(Decimal), activo(bool)}
        """
        def _get(o: Any, key: str, default=None):
            if isinstance(o, dict):
                if key in o:
                    return o.get(key, default)
            try:
                if hasattr(o, key):
                    return getattr(o, key)
            except Exception:
                pass
            return default

        faltantes: List[str] = []

        # id
        idv = (
            _get(item, "id", None)
            or _get(item, "id_servicio", None)
            or _get(item, "servicio_id", None)
        )
        if idv is None:
            faltantes.append("id")
        try:
            idv = int(idv) if idv is not None else None
        except Exception:
            idv = None

        # nombre
        nombre = (
            _get(item, "nombre", None)
            or _get(item, "servicio", None)
            or _get(item, "display_name", None)
        )
        if not nombre:
            faltantes.append("nombre")
            nombre = "—"

        # tipo (acepta enum value)
        tipo = (
            _get(item, "tipo", None)
            or _get(item, "tipo_servicio", None)
            or _get(item, "clave_tipo", None)
        )
        if hasattr(tipo, "value"):  # enum
            try:
                tipo = tipo.value
            except Exception:
                pass
        if not tipo:
            faltantes.append("tipo")
            tipo = "—"

        # precio
        precio_raw = (
            _get(item, "precio", None)
            or _get(item, "precio_base", None)
            or _get(item, "costo", None)
        )
        try:
            precio = Decimal(str(precio_raw)) if precio_raw is not None else Decimal("0")
        except Exception:
            precio = Decimal("0")
            faltantes.append("precio")

        # activo
        activo_raw = _get(item, "activo", None)
        if activo_raw is None:
            estado = _get(item, "estado", None)
            if isinstance(estado, str):
                activo_raw = estado.strip().lower() == "activo"
        activo = _bool(activo_raw) if activo_raw is not None else True

        if faltantes:
            self._log(f"[Servicios] normalize: faltantes={','.join(faltantes)}")

        return {
            self.ID: idv,
            self.NOMBRE: nombre,
            self.TIPO: tipo,
            self.PRECIO: precio,
            self.ACTIVO: activo,
        }

    # =========================================================
    # Permisos / tema / pubsub / feedback
    # =========================================================
    def _resolver_rol_usuario(self):
        """
        Prioridad:
          a) page.session["session_user"]["rol"]
          b) AppState().usuario.rol
          c) AppState().get_user_role()
        Fallbacks:
          - page.session["session_user"] variantes de claves (ROL/role)
          - page.client_storage["app.user"]["rol"]
          - username == 'root'
        Determina:
          - self._rol (str | None)
          - self._is_root (bool)
          - self._can_edit (bool)
        """
        rol = None
        username = None
        fuente = "none"
        caps = {}

        # ---- a) page.session["session_user"] ----
        try:
            sess = getattr(self.page, "session", None)
            get = getattr(sess, "get", None)
            sess_user = None
            if callable(get):
                sess_user = sess.get("session_user")
            elif isinstance(sess, dict):
                sess_user = sess.get("session_user")

            if isinstance(sess_user, dict):
                username = (sess_user.get("username") or sess_user.get("user") or "").strip()
                rol = (sess_user.get("rol") or sess_user.get("role") or sess_user.get("ROL") or "").strip()
                caps = sess_user.get("capabilities") or {}
                if rol:
                    fuente = "page.session.session_user"
        except Exception:
            pass

        # ---- b) AppState().usuario.rol ----
        if not rol:
            try:
                u = getattr(self.app_state, "usuario", None)
                if isinstance(u, dict):
                    username = username or (u.get("username") or u.get("user") or "").strip()
                    rol = (u.get("rol") or u.get("role") or "").strip() or rol
                    caps = caps or u.get("capabilities") or {}
                    if rol:
                        fuente = "AppState.usuario(dict)"
                elif u and hasattr(u, "rol"):
                    username = username or (getattr(u, "username", "") or getattr(u, "user", "") or "")
                    rol = (getattr(u, "rol", "") or getattr(u, "role", "") or "").strip() or rol
                    if rol:
                        fuente = "AppState.usuario(obj)"
            except Exception:
                pass

        # ---- c) AppState().get_user_role() ----
        if not rol:
            try:
                if hasattr(self.app_state, "get_user_role"):
                    r2 = self.app_state.get_user_role()
                    if r2:
                        rol = str(r2).strip()
                        fuente = "AppState.get_user_role()"
            except Exception:
                pass

        # ---- fallback: client_storage["app.user"] ----
        if not rol:
            try:
                cs = getattr(self.page, "client_storage", None)
                if cs:
                    cu = cs.get("app.user")
                    if isinstance(cu, dict):
                        username = username or (cu.get("username") or cu.get("user") or "").strip()
                        rol = (cu.get("rol") or cu.get("role") or "").strip() or rol
                        caps = caps or cu.get("capabilities") or {}
                        if rol:
                            fuente = "client_storage.app.user"
            except Exception:
                pass

        # Normaliza rol
        r_low = (rol or "").strip().lower() or None
        self._rol = r_low

        # ---- Cálculo de permisos ----
        is_root = False
        can_edit = False
        try:
            if UsuariosModel and hasattr(UsuariosModel, "role_is_root"):
                is_root = bool(UsuariosModel.role_is_root(rol)) or bool(UsuariosModel.role_is_root(r_low))
        except Exception:
            is_root = False

        if not is_root:
            if (r_low in {"root", "admin", "superadmin", "administrator"}) or (username or "").strip().lower() == "root":
                is_root = True

        if isinstance(caps, dict):
            try:
                is_root = is_root or bool(caps.get("usuarios_admin")) or bool(caps.get("configuracion"))
                can_edit = bool(caps.get("servicios_editar")) or is_root
            except Exception:
                can_edit = is_root

        if not isinstance(caps, dict):
            can_edit = is_root

        self._is_root = bool(is_root)
        self._can_edit = bool(can_edit or self._is_root)

        print(f"[Servicios] rol_resuelto={self._rol} is_root={self._is_root} fuente={fuente}")

        # Aplicar a UI si ya existe
        if self._btn_agregar:
            self._btn_agregar.disabled = not self._is_root

        # Re-armar tabla si ya existe
        if self._table:
            self._build_table()
            self._aplicar_filtro_y_orden()
            self._repaint_table()

    def _apply_textfield_palette(self, tf: ft.TextField):
        if not self.colors:
            return
        tf.bgcolor = self.colors.get("FIELD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
        tf.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.label_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=self.UI["tf_label_size"])
        tf.hint_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=self.UI["tf_text_size"])
        tf.cursor_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.border_color = self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)
        tf.focused_border_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _subscribe_pubsub(self):
        try:
            pubsub = getattr(self.page, "pubsub", None)
            if not pubsub:
                return

            def _listener(*args, **kwargs):
                topic = None
                data = None
                if len(args) == 2:
                    topic, data = args
                elif len(args) == 1 and isinstance(args[0], dict):
                    topic = args[0].get("topic")
                    data = args[0].get("data")
                elif "topic" in kwargs:
                    topic = kwargs.get("topic")
                    data = kwargs.get("data")

                if topic == self.TOPIC_REFRESH:
                    self._log("INFO: pubsub → refresh recibido.")
                    self._cargar_datos()

            if hasattr(pubsub, "subscribe"):
                unsub = pubsub.subscribe(_listener)
                self._pubsub_unsub = unsub if callable(unsub) else (lambda: None)
            elif hasattr(pubsub, "add_listener"):
                pubsub.add_listener(_listener)
                self._pubsub_unsub = lambda: pubsub.remove_listener(_listener) if hasattr(pubsub, "remove_listener") else None

        except Exception:
            self._pubsub_unsub = None

    def _publish_refresh(self):
        pubsub = getattr(self.page, "pubsub", None)
        if not pubsub:
            return
        try:
            if hasattr(pubsub, "publish"):
                pubsub.publish(self.TOPIC_REFRESH, True)
                self._log(f"[Servicios][PUBSUB] refrescar_datos enviado (publish)")
            elif hasattr(pubsub, "send_all"):
                pubsub.send_all(self.TOPIC_REFRESH, True)
                self._log(f"[Servicios][PUBSUB] refrescar_datos enviado (send_all)")
        except Exception as ex:
            self._log(f"[Servicios][ERROR] Notificando pubsub: {ex}")

    def _error_modal_o_snack(self, msg: str):
        if ModalAlert:
            try:
                ModalAlert(self.page).show_error(msg)
                return
            except Exception:
                pass
        try:
            self.page.snack_bar = ft.SnackBar(ft.Text(msg))
            self.page.snack_bar.open = True
            self.page.update()
        except Exception:
            pass

    def _is_ok(self, res: Any) -> bool:
        if isinstance(res, dict):
            st = (res.get("status") or "").lower()
            return st == "success" or res.get("ok") is True
        return bool(res)

    def _err_msg(self, res: Any) -> str:
        if isinstance(res, dict):
            return _txt(res.get("message") or res.get("error") or "Operación no exitosa.")
        return _txt(res)

    def _log(self, *args, **kwargs):
        try:
            print("[ServiciosContainer]", *args, **kwargs)
        except Exception:
            pass

    # =========================================================
    # Theme helpers
    # =========================================================
    def _resolve_colors(self) -> Dict[str, str]:
        """
        Intenta obtener paleta específica del área 'servicios'.
        """
        try:
            # get_colors(area, dark) o get_colors(area=..., dark=?)
            if hasattr(self.app_state, "get_dark_mode") and hasattr(self.app_state, "get_colors"):
                dark = bool(self.app_state.get_dark_mode()) if callable(self.app_state.get_dark_mode) else False
                try:
                    return self.app_state.get_colors("servicios", dark)  # firma (area, dark)
                except TypeError:
                    return self.app_state.get_colors(area="servicios", dark=dark)  # firma (area=?, dark=?)
            elif hasattr(self.app_state, "get_colors"):
                try:
                    return self.app_state.get_colors("servicios")
                except TypeError:
                    return self.app_state.get_colors(area="servicios")
        except Exception:
            pass
        # Fallback global
        try:
            return self.app_state.get_colors()
        except Exception:
            return {}
