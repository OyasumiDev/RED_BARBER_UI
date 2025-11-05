# app/views/modals/modal_promos_manager.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

import flet as ft

from app.config.application.app_state import AppState
from app.models.servicios_model import ServiciosModel
from app.models.promos_model import PromosModel

# Enums de Promos
from app.core.enums.e_promos import E_PROMO, E_PROMO_ESTADO, E_PROMO_TIPO


def _txt(v: Any) -> str:
    return "" if v is None else str(v)


def _to_decimal(s: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(s or "0")).quantize(Decimal("0.01"))
    except Exception:
        return default


class PromosManagerDialog:
    """
    Modal de gestión de promociones:
    - Lista con búsqueda/filtros básicos
    - Switch de activar/desactivar en línea
    - Crear/editar promoción (un servicio, días de semana, tipo de descuento, valor)
    - Eliminar con confirmación
    """

    def __init__(self):
        # Core/theme
        self.app_state = AppState()
        self.page = self.app_state.get_page()
        self.colors = self.app_state.get_colors()

        # Models
        self.promos = PromosModel()
        self.servicios = ServiciosModel()

        # Estado global UI
        self._dlg: Optional[ft.AlertDialog] = None
        self._mounted = False

        # Datos
        self._rows: List[Dict[str, Any]] = []
        self._serv_opts: List[Tuple[str, str]] = []  # (id_str, nombre)

        # Filtros
        self._search_q: str = ""
        self._estado_filter: Optional[str] = None  # "activa"/"inactiva"/None
        self._day_filter: Optional[str] = None     # "LUN"... "DOM" / None

        # Edición
        self._editing_id: Optional[int] = None

        # Widgets refs
        self._list_container: Optional[ft.Column] = None
        self._tf_search: Optional[ft.TextField] = None
        self._dd_estado: Optional[ft.Dropdown] = None
        self._dd_day: Optional[ft.Dropdown] = None

        # Form widgets
        self._tf_nombre: Optional[ft.TextField] = None
        self._sw_activa: Optional[ft.Switch] = None
        self._chips_days: Dict[str, ft.FilterChip] = {}
        self._dd_servicio: Optional[ft.Dropdown] = None
        self._dd_tipo: Optional[ft.Dropdown] = None
        self._tf_valor: Optional[ft.TextField] = None

        # Footer acciones
        self._btn_save: Optional[ft.FilledButton] = None
        self._btn_cancel: Optional[ft.TextButton] = None

        # Barra superior
        self._btn_nueva: Optional[ft.FilledTonalButton] = None

        # Listeners
        try:
            self.app_state.on_theme_change(self._on_theme_changed)
        except Exception:
            pass

    # ---------------------- Public API ----------------------
    def open(self, page: Optional[ft.Page] = None):
        if page:
            self.page = page
        self.colors = self.app_state.get_colors()

        # Cargar servicios para dropdown
        self._load_servicios_opts()
        # Cargar lista inicial
        self._refresh_rows()

        # Construir dialog
        self._dlg = self._build_dialog()
        self.page.dialog = self._dlg
        self._dlg.open = True
        self._mounted = True
        self.page.update()

    # ---------------------- Theme ----------------------
    def _on_theme_changed(self, *_):
        self.colors = self.app_state.get_colors()
        if self._dlg and self._dlg.open:
            self._recolor()
            self.page.update()

    def _recolor(self):
        # Recolorear controles críticos
        if self._tf_search:
            self._apply_tf_palette(self._tf_search)
        if self._tf_nombre:
            self._apply_tf_palette(self._tf_nombre)
        if self._tf_valor:
            self._apply_tf_palette(self._tf_valor)
        # Dropdowns
        for dd in (self._dd_estado, self._dd_day, self._dd_servicio, self._dd_tipo):
            if dd:
                dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)

    def _apply_tf_palette(self, tf: ft.TextField):
        tf.bgcolor = self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
        tf.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.hint_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=12)
        tf.cursor_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.border_color = self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)
        tf.focused_border_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    # ---------------------- Data ----------------------
    def _load_servicios_opts(self):
        self._serv_opts.clear()
        try:
            lista = self.servicios.listar(activo=True) or []
        except Exception:
            lista = []
        for s in lista:
            sid = s.get("id") or s.get("ID") or s.get("id_servicio")
            nom = s.get("nombre") or s.get("NOMBRE") or f"Servicio {sid}"
            if sid is not None:
                self._serv_opts.append((str(int(sid)), str(nom)))

    def _refresh_rows(self):
        # Filtro estado → activa: True/False/None
        activa: Optional[bool] = None
        if self._estado_filter:
            if self._estado_filter.lower() == E_PROMO_ESTADO.ACTIVA.value:
                activa = True
            elif self._estado_filter.lower() == E_PROMO_ESTADO.INACTIVA.value:
                activa = False

        rows = self.promos.listar(
            activa=activa,
            servicio_id=None,
            search=(self._search_q or None)
        ) or []

        # Filtro por día (client-side, según columna booleana)
        if self._day_filter:
            day_col = getattr(E_PROMO, self._day_filter).value  # e.g., "lunes"
            rows = [r for r in rows if int(r.get(day_col) or 0) == 1]

        self._rows = rows

    # ---------------------- UI builders ----------------------
    def _build_dialog(self) -> ft.AlertDialog:
        # Header con toolbar de lista
        header = self._build_list_toolbar()
        # Lista
        self._list_container = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        self._rebuild_list()

        # Formulario (nueva/editar)
        form = self._build_form()

        content = ft.Container(
            width=860,
            padding=12,
            bgcolor=self.colors.get("BG_COLOR"),
            content=ft.Column(
                expand=True,
                spacing=10,
                controls=[
                    ft.Row(
                        [ft.Text("Promociones", size=18, weight=ft.FontWeight.W_600, color=self.colors.get("FG_COLOR")),
                         ft.Container(expand=True),
                         self._btn_nueva],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    header,
                    ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)),
                    ft.Row(
                        controls=[
                            ft.Container(self._list_container, expand=True),
                        ],
                        expand=True,
                    ),
                    ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)),
                    form,
                ],
            ),
        )

        dlg = ft.AlertDialog(
            modal=True,
            content=content,
            actions=[ft.TextButton("Cerrar", on_click=lambda e: self._close())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        return dlg

    def _build_list_toolbar(self) -> ft.Control:
        self._tf_search = ft.TextField(
            label="Buscar",
            hint_text="Nombre de la promoción…",
            height=40,
            text_size=12,
            on_change=lambda e: self._on_search_change(),
            width=260,
        )
        self._apply_tf_palette(self._tf_search)

        self._dd_estado = ft.Dropdown(
            label="Estado",
            width=160,
            options=[
                ft.dropdown.Option("", "Todos"),
                ft.dropdown.Option(E_PROMO_ESTADO.ACTIVA.value, "Activa"),
                ft.dropdown.Option(E_PROMO_ESTADO.INACTIVA.value, "Inactiva"),
            ],
            on_change=lambda e: self._on_estado_filter(),
            dense=True,
        )
        self._dd_estado.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)

        # Día: usa nombres de enum E_PROMO (LUN..DOM) como keys
        self._dd_day = ft.Dropdown(
            label="Día",
            width=140,
            options=[
                ft.dropdown.Option("", "Todos"),
                ft.dropdown.Option("LUN", "Lun"),
                ft.dropdown.Option("MAR", "Mar"),
                ft.dropdown.Option("MIE", "Mié"),
                ft.dropdown.Option("JUE", "Jue"),
                ft.dropdown.Option("VIE", "Vie"),
                ft.dropdown.Option("SAB", "Sáb"),
                ft.dropdown.Option("DOM", "Dom"),
            ],
            on_change=lambda e: self._on_day_filter(),
            dense=True,
        )
        self._dd_day.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)

        self._btn_nueva = ft.FilledTonalButton(
            "Nueva",
            icon=ft.icons.ADD,
            on_click=lambda e: self._on_new(),
        )

        return ft.Row(
            spacing=8,
            controls=[
                self._tf_search,
                self._dd_estado,
                self._dd_day,
                ft.IconButton(
                    ft.icons.CLEAR_ALL,
                    tooltip="Limpiar filtros",
                    on_click=lambda e: self._clear_filters(),
                    icon_size=16,
                    style=ft.ButtonStyle(padding=0),
                ),
            ],
        )

    def _rebuild_list(self):
        if not self._list_container:
            return
        self._list_container.controls.clear()

        # Header
        header = ft.Row(
            spacing=8,
            controls=[
                ft.Container(width=64, content=ft.Text("Activa", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(expand=True, content=ft.Text("Promoción", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(width=180, content=ft.Text("Días", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(width=220, content=ft.Text("Servicio", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(width=110, content=ft.Text("Descuento", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(width=120, content=ft.Text("Acciones", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
            ],
        )
        self._list_container.controls.append(header)

        # Rows
        for r in self._rows:
            roww = self._row_view(r)
            self._list_container.controls.append(roww)

    def _row_view(self, r: Dict[str, Any]) -> ft.Control:
        rid = r.get(E_PROMO.ID.value)
        activa = (str(r.get(E_PROMO.ESTADO.value) or "").lower() == E_PROMO_ESTADO.ACTIVA.value)

        sw = ft.Switch(value=activa, scale=0.9)
        sw.on_change = lambda e, _rid=rid, _sw=sw: self._toggle_activa(_rid, _sw.value)

        nombre = ft.Text(_txt(r.get(E_PROMO.NOMBRE.value)), size=12, color=self.colors.get("FG_COLOR"))

        dias = self._dias_to_str(r)
        dias_txt = ft.Text(dias or "—", size=12, color=self.colors.get("FG_COLOR"))

        serv_label = self._serv_name_for_id(r.get(E_PROMO.SERVICIO_ID.value))
        serv_txt = ft.Text(serv_label or "—", size=12, color=self.colors.get("FG_COLOR"))

        desc_txt = ft.Text(self._format_descuento(r), size=12, color=self.colors.get("FG_COLOR"))

        btn_edit = ft.IconButton(ft.icons.EDIT, tooltip="Editar", icon_size=16,
                                 on_click=lambda e, _rid=rid: self._start_edit(_rid))
        btn_del = ft.IconButton(ft.icons.DELETE, tooltip="Eliminar", icon_size=16,
                                on_click=lambda e, _rid=rid: self._confirm_delete(_rid))

        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(width=64, content=sw),
                ft.Container(expand=True, content=nombre),
                ft.Container(width=180, content=dias_txt),
                ft.Container(width=220, content=serv_txt),
                ft.Container(width=110, content=desc_txt),
                ft.Container(width=120, content=ft.Row([btn_edit, btn_del], spacing=4)),
            ],
        )

    # ---------------------- Form ----------------------
    def _build_form(self) -> ft.Control:
        self._tf_nombre = ft.TextField(
            label="Nombre de la promoción",
            hint_text="Ej. -50% miércoles en Corte Adulto",
            height=40,
            text_size=12,
            width=420,
        )
        self._apply_tf_palette(self._tf_nombre)

        self._sw_activa = ft.Switch(label="Activa", value=True, scale=0.9)

        # Días
        days = [
            ("LUN", "Lun", E_PROMO.LUN.value),
            ("MAR", "Mar", E_PROMO.MAR.value),
            ("MIE", "Mié", E_PROMO.MIE.value),
            ("JUE", "Jue", E_PROMO.JUE.value),
            ("VIE", "Vie", E_PROMO.VIE.value),
            ("SAB", "Sáb", E_PROMO.SAB.value),
            ("DOM", "Dom", E_PROMO.DOM.value),
        ]
        self._chips_days = {}
        chips_row = []
        for key, label, _col in days:
            chip = ft.FilterChip(label=label, selected=False, dense=True)
            self._chips_days[key] = chip
            chips_row.append(chip)

        # Servicio (una sola selección)
        self._dd_servicio = ft.Dropdown(
            label="Servicio",
            width=320,
            options=[ft.dropdown.Option(idstr, name) for idstr, name in self._serv_opts],
            dense=True,
        )
        self._dd_servicio.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)

        # Tipo y valor
        self._dd_tipo = ft.Dropdown(
            label="Tipo de descuento",
            width=180,
            options=[
                ft.dropdown.Option(E_PROMO_TIPO.PORCENTAJE.value, "Porcentaje"),
                ft.dropdown.Option(E_PROMO_TIPO.MONTO.value, "Monto fijo"),
            ],
            value=E_PROMO_TIPO.PORCENTAJE.value,
            dense=True,
        )
        self._dd_tipo.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)

        self._tf_valor = ft.TextField(
            label="Valor",
            hint_text="Ej. 50 (para 50%) o 20.00 (monto)",
            height=40,
            text_size=12,
            width=160,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._apply_tf_palette(self._tf_valor)

        # Acciones
        self._btn_save = ft.FilledButton("Guardar", icon=ft.icons.SAVE, on_click=lambda e: self._save())
        self._btn_cancel = ft.TextButton("Cancelar edición", on_click=lambda e: self._cancel_edit())

        form = ft.Column(
            spacing=8,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.START,
                    controls=[
                        ft.Text("Nueva / Editar promoción", size=14, weight=ft.FontWeight.W_600,
                                color=self.colors.get("FG_COLOR")),
                        ft.Container(expand=True),
                        self._sw_activa,
                    ],
                ),
                ft.Row(spacing=10, controls=[self._tf_nombre]),
                ft.Row(spacing=8, controls=[ft.Text("Días:", size=12, color=self.colors.get("FG_COLOR"))] + chips_row),
                ft.Row(spacing=10, controls=[self._dd_servicio, self._dd_tipo, self._tf_valor]),
                ft.Row(spacing=8, controls=[self._btn_cancel, self._btn_save]),
            ],
        )
        return form

    # ---------------------- Interacciones toolbar ----------------------
    def _on_search_change(self):
        self._search_q = (self._tf_search.value or "").strip()
        self._refresh_rows()
        self._rebuild_list()
        self.page.update()

    def _on_estado_filter(self):
        v = (self._dd_estado.value or "").strip().lower()
        self._estado_filter = v or None
        self._refresh_rows()
        self._rebuild_list()
        self.page.update()

    def _on_day_filter(self):
        v = (self._dd_day.value or "").strip().upper()
        self._day_filter = v or None
        self._refresh_rows()
        self._rebuild_list()
        self.page.update()

    def _clear_filters(self):
        if self._tf_search:
            self._tf_search.value = ""
        if self._dd_estado:
            self._dd_estado.value = ""
        if self._dd_day:
            self._dd_day.value = ""
        self._search_q = ""
        self._estado_filter = None
        self._day_filter = None
        self._refresh_rows()
        self._rebuild_list()
        self.page.update()

    # ---------------------- Acciones de fila ----------------------
    def _toggle_activa(self, promo_id: int, nueva_activa: bool):
        estado = E_PROMO_ESTADO.ACTIVA.value if nueva_activa else E_PROMO_ESTADO.INACTIVA.value
        res = self.promos.actualizar_promo(promo_id, **{E_PROMO.ESTADO.value: estado})
        if res.get("status") != "success":
            self._snack_error(f"❌ {res.get('message', 'No se pudo actualizar el estado')}")
        else:
            self._snack_ok("✅ Estado actualizado.")
        self._refresh_rows()
        self._rebuild_list()
        self.page.update()

    def _start_edit(self, promo_id: int):
        row = self.promos.get_by_id(int(promo_id)) or {}
        self._editing_id = int(promo_id)
        self._fill_form_from_row(row)
        self.page.update()

    def _confirm_delete(self, promo_id: int):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar promoción"),
            content=ft.Text(f"¿Eliminar la promoción #{promo_id}? Esta acción no se puede deshacer."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_inner_dialog()),
                ft.FilledButton("Eliminar", icon=ft.icons.DELETE, on_click=lambda e, pid=promo_id: self._do_delete(pid)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def _do_delete(self, promo_id: int):
        self._close_inner_dialog()
        res = self.promos.eliminar_promo(int(promo_id))
        if res.get("status") == "success":
            self._snack_ok("🗑️ Promoción eliminada.")
            self._refresh_rows()
            self._rebuild_list()
            self.page.update()
        else:
            self._snack_error(f"❌ {res.get('message', 'No se pudo eliminar')}")

    def _close_inner_dialog(self):
        try:
            if self.page.dialog:
                self.page.dialog.open = False
                self.page.update()
        except Exception:
            pass
        # Recolocar this modal como dialog activo (si sigue abierto)
        if self._dlg and self._dlg.open:
            self.page.dialog = self._dlg

    # ---------------------- Nueva/Guardar/Cancelar ----------------------
    def _on_new(self):
        self._editing_id = None
        self._clear_form()
        self.page.update()

    def _clear_form(self):
        if self._tf_nombre: self._tf_nombre.value = ""
        if self._sw_activa: self._sw_activa.value = True
        for chip in self._chips_days.values():
            chip.selected = False
        if self._dd_servicio: self._dd_servicio.value = None
        if self._dd_tipo: self._dd_tipo.value = E_PROMO_TIPO.PORCENTAJE.value
        if self._tf_valor: self._tf_valor.value = ""

    def _fill_form_from_row(self, r: Dict[str, Any]):
        if self._tf_nombre: self._tf_nombre.value = r.get(E_PROMO.NOMBRE.value) or ""
        if self._sw_activa:
            self._sw_activa.value = (str(r.get(E_PROMO.ESTADO.value) or "").lower() == E_PROMO_ESTADO.ACTIVA.value)

        # Días
        def _b(k): return bool(int(r.get(k) or 0))
        days_map = {
            "LUN": E_PROMO.LUN.value, "MAR": E_PROMO.MAR.value, "MIE": E_PROMO.MIE.value,
            "JUE": E_PROMO.JUE.value, "VIE": E_PROMO.VIE.value, "SAB": E_PROMO.SAB.value,
            "DOM": E_PROMO.DOM.value,
        }
        for key, col in days_map.items():
            if key in self._chips_days:
                self._chips_days[key].selected = _b(col)

        # Servicio
        sid = r.get(E_PROMO.SERVICIO_ID.value)
        if sid is not None and self._dd_servicio:
            self._dd_servicio.value = str(int(sid))

        # Tipo/Valor
        if self._dd_tipo:
            v = r.get(E_PROMO.TIPO_DESC.value) or E_PROMO_TIPO.PORCENTAJE.value
            self._dd_tipo.value = v
        if self._tf_valor:
            self._tf_valor.value = _txt(r.get(E_PROMO.VALOR_DESC.value))

    def _collect_form(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        nombre = (self._tf_nombre.value or "").strip() if self._tf_nombre else ""
        if len(nombre) < 3:
            return None, "Nombre inválido (mín. 3 caracteres)."

        activa = bool(self._sw_activa.value) if self._sw_activa else True
        estado = E_PROMO_ESTADO.ACTIVA.value if activa else E_PROMO_ESTADO.INACTIVA.value

        days_map = {
            "LUN": E_PROMO.LUN.value, "MAR": E_PROMO.MAR.value, "MIE": E_PROMO.MIE.value,
            "JUE": E_PROMO.JUE.value, "VIE": E_PROMO.VIE.value, "SAB": E_PROMO.SAB.value,
            "DOM": E_PROMO.DOM.value,
        }
        dias_values = {col: 1 if self._chips_days[key].selected else 0 for key, col in days_map.items()}
        if sum(dias_values.values()) <= 0:
            return None, "Selecciona al menos un día."

        if not self._dd_servicio or not self._dd_servicio.value:
            return None, "Selecciona un servicio."
        try:
            servicio_id = int(self._dd_servicio.value)
        except Exception:
            return None, "Servicio inválido."

        tipo_desc = self._dd_tipo.value if self._dd_tipo else E_PROMO_TIPO.PORCENTAJE.value
        val_txt = (self._tf_valor.value or "").strip() if self._tf_valor else "0"
        try:
            val_dec = _to_decimal(val_txt)
        except Exception:
            return None, "Valor de descuento inválido."
        if tipo_desc == E_PROMO_TIPO.PORCENTAJE.value:
            if val_dec <= 0 or val_dec > 100:
                return None, "Porcentaje debe ser > 0 y ≤ 100."
        else:
            if val_dec < 0:
                return None, "Monto fijo debe ser ≥ 0."

        # Usuario (auditoría)
        uid = None
        try:
            sess = self.page.client_storage.get("app.user") if self.page else None
            uid = (sess or {}).get("id_usuario")
        except Exception:
            uid = None

        data = {
            E_PROMO.NOMBRE.value: nombre,
            E_PROMO.ESTADO.value: estado,
            E_PROMO.SERVICIO_ID.value: servicio_id,
            E_PROMO.TIPO_DESC.value: tipo_desc,
            E_PROMO.VALOR_DESC.value: float(val_dec),
            # fechas/hora opcionales → no usadas en este formulario (se envían nulas)
            E_PROMO.FECHA_INI.value: None,
            E_PROMO.FECHA_FIN.value: None,
            E_PROMO.HORA_INI.value: None,
            E_PROMO.HORA_FIN.value: None,
            # días:
            **dias_values,
            # auditoría
            E_PROMO.CREATED_BY.value: uid if self._editing_id is None else None,
            E_PROMO.UPDATED_BY.value: uid if self._editing_id is not None else None,
        }
        return data, None

    def _save(self):
        data, err = self._collect_form()
        if err:
            self._snack_error("❌ " + err)
            return

        if self._editing_id is None:
            # crear
            res = self.promos.crear_promo(
                nombre=data[E_PROMO.NOMBRE.value],
                servicio_id=data[E_PROMO.SERVICIO_ID.value],
                tipo_descuento=data[E_PROMO.TIPO_DESC.value],
                valor_descuento=data[E_PROMO.VALOR_DESC.value],
                estado=data[E_PROMO.ESTADO.value],
                fecha_inicio=None, fecha_fin=None,
                aplica_lunes=data[E_PROMO.LUN.value],
                aplica_martes=data[E_PROMO.MAR.value],
                aplica_miercoles=data[E_PROMO.MIE.value],
                aplica_jueves=data[E_PROMO.JUE.value],
                aplica_viernes=data[E_PROMO.VIE.value],
                aplica_sabado=data[E_PROMO.SAB.value],
                aplica_domingo=data[E_PROMO.DOM.value],
                hora_inicio=None, hora_fin=None,
                created_by=data.get(E_PROMO.CREATED_BY.value),
            )
        else:
            # actualizar
            payload = data.copy()
            payload.pop(E_PROMO.CREATED_BY.value, None)  # no se actualiza
            res = self.promos.actualizar_promo(self._editing_id, **payload)

        if res.get("status") == "success":
            self._snack_ok("✅ Promoción guardada.")
            self._editing_id = None
            self._clear_form()
            self._refresh_rows()
            self._rebuild_list()
            self.page.update()
        else:
            self._snack_error(f"❌ {res.get('message', 'No se pudo guardar')}")

    def _cancel_edit(self):
        self._editing_id = None
        self._clear_form()
        self.page.update()

    # ---------------------- Helpers UI ----------------------
    def _format_descuento(self, r: Dict[str, Any]) -> str:
        tipo = (r.get(E_PROMO.TIPO_DESC.value) or "").lower()
        val = _to_decimal(r.get(E_PROMO.VALOR_DESC.value) or 0)
        if tipo == E_PROMO_TIPO.PORCENTAJE.value:
            return f"-{val.normalize()}%"
        return f"-${val:.2f}"

    def _dias_to_str(self, r: Dict[str, Any]) -> str:
        parts = []
        if int(r.get(E_PROMO.LUN.value) or 0) == 1: parts.append("Lun")
        if int(r.get(E_PROMO.MAR.value) or 0) == 1: parts.append("Mar")
        if int(r.get(E_PROMO.MIE.value) or 0) == 1: parts.append("Mié")
        if int(r.get(E_PROMO.JUE.value) or 0) == 1: parts.append("Jue")
        if int(r.get(E_PROMO.VIE.value) or 0) == 1: parts.append("Vie")
        if int(r.get(E_PROMO.SAB.value) or 0) == 1: parts.append("Sáb")
        if int(r.get(E_PROMO.DOM.value) or 0) == 1: parts.append("Dom")
        return " ".join(parts)

    def _serv_name_for_id(self, sid: Any) -> str:
        sid_str = str(int(sid)) if sid is not None else ""
        if not sid_str:
            return ""
        # Buscar en cache local
        for _id, name in self._serv_opts:
            if _id == sid_str:
                return name
        # Si no está, refrescar servicios (pudo activarse después)
        self._load_servicios_opts()
        for _id, name in self._serv_opts:
            if _id == sid_str:
                return name
        return f"Servicio {sid_str}"

    # ---------------------- Close & feedback ----------------------
    def _close(self):
        if not self._dlg:
            return
        try:
            self._dlg.open = False
            self.page.update()
        except Exception:
            pass

    def _snack_ok(self, msg: str):
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            bgcolor=self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)),
        )
        self.page.snack_bar.open = True

    def _snack_error(self, msg: str):
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=ft.colors.WHITE),
            bgcolor=ft.colors.RED_600,
        )
        self.page.snack_bar.open = True
