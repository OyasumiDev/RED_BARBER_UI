from __future__ import annotations
import flet as ft
from typing import Any, Dict, List, Optional

# Core globales
from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController

# Modelo y enums
from app.models.trabajadores_model import TrabajadoresModel
from app.core.enums.e_trabajadores import E_TRABAJADORES, E_TRAB_TIPO, E_TRAB_ESTADO

# TableBuilder + SortManager + (opcional) Scroll controller
from app.ui.builders.table_builder import TableBuilder
from app.ui.sorting.sort_manager import SortManager
try:
    from app.ui.scroll.table_scroll_controller import ScrollTableController
except Exception:
    ScrollTableController = None  # opcional

# BotonFactory (para acciones en modo edición/nuevo)
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


class TrabajadoresContainer(ft.Container):
    """
    Módulo de trabajadores (Flet 0.23) integrado con TableBuilder v2.
    - Mantiene filtros por ID y Nombre (priorizados).
    - Ordenamiento por encabezado (SortManager).
    - Edición en línea y alta de nuevos registros.
    - Eliminar con confirmación.
    - Reactivo al ThemeController (colores se re-aplican al vuelo).
    """

    # =========================================================
    # Init
    # =========================================================
    def __init__(self):
        super().__init__()

        # Core globales
        self.app_state = AppState()
        self.page = self.app_state.page
        self.theme_ctrl = ThemeController()
        self.colors = self.theme_ctrl.get_colors()

        # Estado de edición / nuevo
        self.fila_editando: Optional[int] = None
        self.fila_nueva_en_proceso: bool = False

        # Filtros/orden
        self.sort_id_filter: Optional[str] = None
        self.sort_name_filter: Optional[str] = None
        self.orden_actual: Dict[str, Optional[str]] = {
            E_TRABAJADORES.ID.value: None,
            E_TRABAJADORES.NOMBRE.value: None,
            E_TRABAJADORES.TIPO.value: None,
            E_TRABAJADORES.COMISION.value: None,
            E_TRABAJADORES.ESTADO.value: None,
        }

        # Refs de controles de edición/nuevo (por fila)
        self._edit_controls: Dict[int, Dict[str, ft.Control]] = {}
        self._new_controls: Dict[str, ft.Control] = {}

        # Modelo
        self.model = TrabajadoresModel()

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

        # ---------------- Botones de cabecera (pill) ----------------
        def _btn(icon_name, text, on_click):
            return ft.GestureDetector(
                on_tap=on_click,
                content=ft.Container(
                    padding=10,
                    border_radius=20,
                    bgcolor=self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT),
                    content=ft.Row(
                        [
                            ft.Icon(
                                name=icon_name,
                                size=18,
                                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                            ),
                            ft.Text(
                                text,
                                size=12,
                                weight="bold",
                                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=6,
                    ),
                ),
            )

        self.import_button = _btn(
            ft.icons.FILE_DOWNLOAD_OUTLINED, "Importar", lambda e: self._on_importar()
        )
        self.export_button = _btn(
            ft.icons.FILE_UPLOAD_OUTLINED, "Exportar", lambda e: self._on_exportar()
        )
        self.add_button = _btn(ft.icons.ADD, "Agregar", lambda e: self._insertar_fila_nueva())

        # ---------------- Toolbar (filtros) ----------------
        self.sort_id_input = ft.TextField(
            label="Ordenar por ID",
            hint_text="Escribe un ID y presiona Enter",
            width=180,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=lambda e: self._aplicar_sort_id(),
            on_change=self._id_on_change_auto_reset,
        )
        self._apply_textfield_palette(self.sort_id_input)

        self.sort_id_clear_btn = ft.IconButton(
            icon=ft.icons.CLEAR,
            tooltip="Limpiar ID",
            icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            on_click=lambda e: self._limpiar_sort_id(),
        )

        self.sort_name_input = ft.TextField(
            label="Buscar por Nombre",
            hint_text="Escribe nombre y presiona Enter",
            width=260,
            on_submit=lambda e: self._aplicar_sort_nombre(),
            on_change=self._nombre_on_change_auto_reset,
        )
        self._apply_textfield_palette(self.sort_name_input)

        self.sort_name_clear_btn = ft.IconButton(
            icon=ft.icons.CLEAR,
            tooltip="Limpiar nombre",
            icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            on_click=lambda e: self._limpiar_sort_nombre(),
        )

        # ---------------- Layout raíz ----------------
        self.content = ft.Container(
            expand=True,
            bgcolor=self.colors.get("BG_COLOR"),
            padding=20,
            content=ft.Column(
                expand=True,
                alignment=ft.MainAxisAlignment.START,
                spacing=10,
                controls=[
                    ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                        controls=[self.add_button, self.import_button, self.export_button],
                    ),
                    ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                        controls=[
                            self.sort_id_input,
                            self.sort_id_clear_btn,
                            self.sort_name_input,
                            self.sort_name_clear_btn,
                        ],
                    ),
                    ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)),
                    ft.Container(
                        alignment=ft.alignment.top_center,
                        padding=ft.padding.only(top=10),
                        expand=True,
                        content=self.scroll_column,
                    ),
                ],
            ),
        )

        # ---------- TableBuilder + SortManager ----------
        self.sort_manager = SortManager()
        self.ID = E_TRABAJADORES.ID.value
        self.NOMBRE = E_TRABAJADORES.NOMBRE.value
        self.TIPO = E_TRABAJADORES.TIPO.value
        self.COMISION = E_TRABAJADORES.COMISION.value
        self.ESTADO = E_TRABAJADORES.ESTADO.value

        columns = [
            {"key": self.ID, "title": "Nómina", "width": 100, "align": "center", "formatter": self._fmt_id},
            {"key": self.NOMBRE, "title": "Nombre", "width": 300, "align": "start", "formatter": self._fmt_nombre},
            {"key": self.TIPO, "title": "Tipo", "width": 140, "align": "start", "formatter": self._fmt_tipo},
            {"key": self.COMISION, "title": "Comisión %", "width": 120, "align": "end", "formatter": self._fmt_comision},
            {"key": self.ESTADO, "title": "Estado", "width": 120, "align": "start", "formatter": self._fmt_estado},
        ]

        self.table_builder = TableBuilder(
            group="trabajadores",
            sort_manager=self.sort_manager,
            columns=columns,
            on_sort_change=self._on_sort_change,   # click en headers
            on_accept=self._on_accept_row,         # aceptar (nuevo o edición si usamos actions_builder)
            on_cancel=self._on_cancel_row,         # cancelar (nuevo o edición)
            on_edit=self._on_edit_row,             # click editar normal
            on_delete=self._on_delete_row,         # click borrar
            id_key=self.ID,
            dense_text=True,
            auto_scroll_new=True,
            actions_title="Acciones",
        )

        # Actions personalizadas: aceptar/cancelar cuando está en edición
        self.table_builder.attach_actions_builder(self._actions_builder)

        # Scroll controller (opcional, si tu helper existe)
        if ScrollTableController:
            try:
                self.stc = ScrollTableController()  # si requiere args, ajusta aquí
                self.table_builder.attach_scroll_controller(self.stc)
            except Exception:
                self.stc = None
        else:
            self.stc = None

        # Render inicial
        self._refrescar_dataset()

        # 🔄 Suscripción a cambio de tema
        cb = getattr(self.app_state, "on_theme_change", None)
        if callable(cb):
            cb(self._on_theme_changed)

    # =========================================================
    # Theme
    # =========================================================
    def _apply_textfield_palette(self, tf: ft.TextField):
        tf.bgcolor = self.colors.get("CARD_BG", ft.colors.SURFACE_VARIANT)
        tf.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.label_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf.hint_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf.cursor_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.border_color = self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)
        tf.focused_border_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _on_theme_changed(self):
        """Reaplica colores en UI y re-renderiza la tabla."""
        self.colors = self.theme_ctrl.get_colors()
        self._recolor_ui()
        self._refrescar_dataset()

    def _recolor_ui(self):
        for btn in [self.import_button, self.export_button, self.add_button]:
            if isinstance(btn.content, ft.Container):
                btn.content.bgcolor = self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)
                if isinstance(btn.content.content, ft.Row):
                    for ctrl in btn.content.content.controls:
                        if isinstance(ctrl, (ft.Icon, ft.Text)):
                            ctrl.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

        self._apply_textfield_palette(self.sort_id_input)
        self._apply_textfield_palette(self.sort_name_input)
        self.sort_id_clear_btn.icon_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        self.sort_name_clear_btn.icon_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

        self.bgcolor = self.colors.get("BG_COLOR")
        self.table_container.bgcolor = self.colors.get("BG_COLOR")
        if isinstance(self.content, ft.Container):
            self.content.bgcolor = self.colors.get("BG_COLOR")

        if self.page:
            try:
                self.page.update()
            except Exception:
                pass

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

    # =========================================================
    # Orden por encabezado (SortManager -> callback)
    # =========================================================
    def _on_sort_change(self, campo: str, grupo: Optional[str] = None, asc: Optional[bool] = None, *_, **__):
        # Toggle simple ASC/DESC en self.orden_actual
        prev = self.orden_actual.get(campo)
        nuevo = "desc" if prev == "asc" else "asc"
        self.orden_actual = {k: None for k in self.orden_actual}
        self.orden_actual[campo] = nuevo
        self._refrescar_dataset()

    def _aplicar_prioridades_y_orden(self, datos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ordered = list(datos)

        # Prioridad por ID exacto
        if self.sort_id_filter:
            id_str = str(self.sort_id_filter)
            id_key = self.ID
            ordered = sorted(ordered, key=lambda r: 0 if str(r.get(id_key)) == id_str else 1)

        # Prioridad por nombre contiene
        if self.sort_name_filter:
            texto = self.sort_name_filter.lower()
            name_key = self.NOMBRE
            ordered = sorted(ordered, key=lambda r: 0 if texto in str(r.get(name_key, "")).lower() else 1)

        # Orden por columna activa
        col_activa = next((k for k, v in self.orden_actual.items() if v), None)
        if col_activa:
            asc = self.orden_actual[col_activa] == "asc"
            def keyfn(x):
                val = x.get(col_activa)
                if col_activa in (self.ID, self.COMISION):
                    try:
                        return float(val or 0)
                    except Exception:
                        return 0.0
                return (val or "")
            ordered.sort(key=keyfn, reverse=not asc)

        return ordered

    # =========================================================
    # Dataset / Render
    # =========================================================
    def _fetch(self) -> List[Dict[str, Any]]:
        datos_result = self.model.listar() if hasattr(self.model, "listar") else []
        return datos_result if isinstance(datos_result, list) else (datos_result.get("data", []) or [])

    def _refrescar_dataset(self):
        datos = self._aplicar_prioridades_y_orden(self._fetch())
        # Monta TableBuilder en UI si aún no
        if not self.table_container.content.controls:
            self.table_container.content.controls.append(self.table_builder.build())
        # Aplica filas
        self.table_builder.set_rows(datos)
        if self.page:
            self.page.update()

    # =========================================================
    # Formatters por columna (inline edit / view)
    # =========================================================
    def _fmt_id(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        return ft.Text(_txt(value), size=12, color=fg)

    def _fmt_nombre(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = (self.fila_editando == rid) or bool(row.get("_is_new"))
        if not en_edicion:
            return ft.Text(_txt(value), size=12, color=fg)

        tf = ft.TextField(
            value=_txt(value),
            hint_text="Nombre completo",
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
        )
        self._apply_textfield_palette(tf)
        def validar(_):
            v = (tf.value or "").strip()
            ok = len(v) >= 3 and all(c.isalpha() or c.isspace() for c in v)
            tf.border_color = None if ok else ft.colors.RED
            if self.page: self.page.update()
        tf.on_change = validar

        # guardar ref
        key = rid if rid is not None else -1
        self._ensure_edit_map(key)
        self._edit_controls[key]["nombre"] = tf
        return tf

    def _fmt_tipo(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = (self.fila_editando == rid) or bool(row.get("_is_new"))
        if not en_edicion:
            return ft.Text(_txt(value), size=12, color=fg)

        dd = ft.Dropdown(
            value=value or E_TRAB_TIPO.OCASIONAL.value,
            options=[
                ft.dropdown.Option(E_TRAB_TIPO.OCASIONAL.value, "ocasional"),
                ft.dropdown.Option(E_TRAB_TIPO.PLANTA.value, "planta"),
                ft.dropdown.Option(E_TRAB_TIPO.DUENO.value, "dueno"),
            ],
            dense=True,
            width=140,
        )
        key = rid if rid is not None else -1
        self._ensure_edit_map(key)
        self._edit_controls[key]["tipo"] = dd
        return dd

    def _fmt_comision(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = (self.fila_editando == rid) or bool(row.get("_is_new"))
        if not en_edicion:
            return ft.Text(_f2(value), size=12, color=fg)

        tf = ft.TextField(
            value=_f2(value) if value is not None and not row.get("_is_new") else "",
            hint_text="Comisión %",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
        )
        self._apply_textfield_palette(tf)
        def validar(_):
            try:
                v = float(tf.value)
                tf.border_color = None if v >= 0 else ft.colors.RED
            except Exception:
                tf.border_color = ft.colors.RED
            if self.page: self.page.update()
        tf.on_change = validar

        key = rid if rid is not None else -1
        self._ensure_edit_map(key)
        self._edit_controls[key]["comision"] = tf
        return tf

    def _fmt_estado(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = (self.fila_editando == rid) or bool(row.get("_is_new"))
        if not en_edicion:
            return ft.Text(_txt(value), size=12, color=fg)

        dd = ft.Dropdown(
            value=value or E_TRAB_ESTADO.ACTIVO.value,
            options=[
                ft.dropdown.Option(E_TRAB_ESTADO.ACTIVO.value, "activo"),
                ft.dropdown.Option(E_TRAB_ESTADO.INACTIVO.value, "inactivo"),
            ],
            dense=True,
            width=120,
        )
        key = rid if rid is not None else -1
        self._ensure_edit_map(key)
        self._edit_controls[key]["estado"] = dd
        return dd

    def _ensure_edit_map(self, key: int):
        if key not in self._edit_controls:
            self._edit_controls[key] = {}

    # =========================================================
    # Actions builder (iconos por fila)
    # =========================================================
    def _actions_builder(self, row: Dict[str, Any], is_new: bool) -> ft.Control:
        rid = row.get(self.ID)

        # Fila NUEVA (aceptar/cancelar -> crear)
        if is_new:
            return ft.Row(
                [
                    boton_aceptar(lambda e, r=row: self._on_accept_row(r)),
                    boton_cancelar(lambda e, r=row: self._on_cancel_row(r)),
                ],
                spacing=8, alignment=ft.MainAxisAlignment.START
            )

        # Fila en EDICIÓN (aceptar/cancelar -> actualizar)
        if self.fila_editando == rid:
            return ft.Row(
                [
                    boton_aceptar(lambda e, r=row: self._on_accept_row(r)),
                    boton_cancelar(lambda e, r=row: self._on_cancel_row(r)),
                ],
                spacing=8, alignment=ft.MainAxisAlignment.START
            )

        # Fila NORMAL (editar/borrar)
        return ft.Row(
            [
                boton_editar(lambda e, r=row: self._on_edit_row(r)),
                boton_borrar(lambda e, r=row: self._on_delete_row(r)),
            ],
            spacing=8, alignment=ft.MainAxisAlignment.START
        )

    # =========================================================
    # Callbacks de acciones
    # =========================================================
    def _on_edit_row(self, row: Dict[str, Any]):
        self.fila_editando = row.get(self.ID)
        self._edit_controls.pop(self.fila_editando if self.fila_editando is not None else -1, None)
        self._refrescar_dataset()

    def _on_delete_row(self, row: Dict[str, Any]):
        rid = int(row.get(self.ID))
        self._confirmar_eliminar(rid)

    def _on_accept_row(self, row: Dict[str, Any]):
        # Detecta si es nueva o edición
        is_new = bool(row.get("_is_new")) or (row.get(self.ID) in (None, "", 0))
        key = (row.get(self.ID) if not is_new else -1)
        ctrls = self._edit_controls.get(key, {})

        # Validaciones comunes
        nombre_tf: ft.TextField = ctrls.get("nombre")  # type: ignore[assignment]
        tipo_dd: ft.Dropdown = ctrls.get("tipo")       # type: ignore[assignment]
        com_tf: ft.TextField = ctrls.get("comision")   # type: ignore[assignment]
        est_dd: ft.Dropdown = ctrls.get("estado")      # type: ignore[assignment]

        errores = []
        nombre_val = (nombre_tf.value or "").strip() if nombre_tf else ""
        if len(nombre_val) < 3 or not all(c.isalpha() or c.isspace() for c in nombre_val):
            if nombre_tf: nombre_tf.border_color = ft.colors.RED
            errores.append("Nombre inválido")

        try:
            com_val = float(com_tf.value) if com_tf else 0.0
            if com_val < 0:
                raise ValueError
        except Exception:
            if com_tf: com_tf.border_color = ft.colors.RED
            errores.append("Comisión inválida")

        if self.page: self.page.update()
        if errores:
            self._snack_error("❌ " + " / ".join(errores))
            return

        if is_new:
            # Crear
            res = self.model.crear_trabajador(
                nombre=nombre_val,
                tipo=(tipo_dd.value if tipo_dd else E_TRAB_TIPO.OCASIONAL.value),
                comision_porcentaje=com_val,
                telefono=None,
                email=None,
                estado=(est_dd.value if est_dd else E_TRAB_ESTADO.ACTIVO.value),
            )
            self.fila_nueva_en_proceso = False
            if res.get("status") == "success":
                self._snack_ok("✅ Trabajador agregado.")
                self._edit_controls.pop(-1, None)
                self._refrescar_dataset()
            else:
                self._snack_error(f"❌ {res.get('message')}")
        else:
            # Actualizar
            rid = int(row.get(self.ID))
            res = self.model.actualizar_trabajador(
                trabajador_id=rid,
                nombre=nombre_val,
                tipo=(tipo_dd.value if tipo_dd else E_TRAB_TIPO.OCASIONAL.value),
                comision_porcentaje=com_val,
                estado=(est_dd.value if est_dd else E_TRAB_ESTADO.ACTIVO.value),
            )
            self.fila_editando = None
            if res.get("status") == "success":
                self._snack_ok("✅ Cambios guardados correctamente.")
                self._edit_controls.pop(rid, None)
                self._refrescar_dataset()
            else:
                self._snack_error(f"❌ No se pudo guardar: {res.get('message')}")

    def _on_cancel_row(self, row: Dict[str, Any]):
        # Si era nueva -> eliminar fila temporal
        if row.get("_is_new") or (row.get(self.ID) in (None, "", 0)):
            self.fila_nueva_en_proceso = False
            # remover última fila _is_new
            rows = self.table_builder.get_rows()
            try:
                idx = next(i for i, r in enumerate(rows) if r is row or r.get("_is_new"))
                self.table_builder.remove_row_at(idx)
            except Exception:
                pass
            self._edit_controls.pop(-1, None)
            if self.page: self.page.update()
            return

        # Si era edición -> salir de edición
        rid = row.get(self.ID)
        self.fila_editando = None
        self._edit_controls.pop(rid if rid is not None else -1, None)
        self._refrescar_dataset()

    # =========================================================
    # Eliminar
    # =========================================================
    def _confirmar_eliminar(self, rid: int):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Eliminar trabajador?", color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
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
        self.page.update()

    def _do_delete(self, _e, rid: int, dlg: ft.AlertDialog):
        res = self.model.eliminar_trabajador(int(rid))
        self.page.close(dlg)
        if res.get("status") == "success":
            self._snack_ok("✅ Trabajador eliminado.")
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ No se pudo eliminar: {res.get('message')}")

    # =========================================================
    # Fila NUEVA (usa TableBuilder)
    # =========================================================
    def _insertar_fila_nueva(self, _e=None):
        if self.fila_nueva_en_proceso:
            self._snack_ok("ℹ️ Ya hay un registro nuevo en proceso.")
            return
        self.fila_nueva_en_proceso = True

        nueva = {
            self.ID: None,
            self.NOMBRE: "",
            self.TIPO: E_TRAB_TIPO.OCASIONAL.value,
            self.COMISION: "",
            self.ESTADO: E_TRAB_ESTADO.ACTIVO.value,
            "_is_new": True,
        }
        self.table_builder.add_row(nueva, auto_scroll=True)

    # =========================================================
    # Import / Export (placeholder)
    # =========================================================
    def _on_importar(self):
        self._snack_ok("ℹ️ Importar: pendiente de implementación.")

    def _on_exportar(self):
        self._snack_ok("ℹ️ Exportar: pendiente de implementación.")

    # =========================================================
    # Notificaciones
    # =========================================================
    def _snack_ok(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            bgcolor=self.colors.get("CARD_BG", ft.colors.SURFACE_VARIANT),
        )
        self.page.snack_bar.open = True
        self.page.update()

    def _snack_error(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=ft.colors.WHITE),
            bgcolor=ft.colors.RED_600,
        )
        self.page.snack_bar.open = True
        self.page.update()
