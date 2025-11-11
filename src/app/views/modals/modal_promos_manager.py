# app/views/modals/modal_promos_manager.py
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple
from decimal import Decimal

import flet as ft

HAS_FILTER_CHIP = hasattr(ft, "FilterChip")

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

    def __init__(self, on_after_close: Optional[Callable[[], None]] = None):
        # Core/theme
        self.app_state = AppState()
        self.page = self.app_state.get_page()
        self.colors = self.app_state.get_colors()
        self._on_after_close = on_after_close

        # Models
        self.promos = PromosModel()
        self.servicios = ServiciosModel()

        # Estado global UI
        self._dlg: Optional[ft.AlertDialog] = None
        self._mounted = False

        # Datos
        self._rows: List[Dict[str, Any]] = []
        self._serv_opts: List[Dict[str, Any]] = []  # {"id": str, "nombre": str, "precio": Decimal}
        self._serv_price_map: Dict[str, Decimal] = {}

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
        self._chips_days: Dict[str, ft.Control] = {}
        self._dd_servicio: Optional[ft.Dropdown] = None
        self._tf_valor: Optional[ft.TextField] = None
        self._txt_precio_servicio: Optional[ft.Text] = None
        self._txt_precio_final: Optional[ft.Text] = None
        self._precio_base_actual: Decimal = Decimal("0.00")
        self._precio_final_actual: Decimal = Decimal("0.00")
        self._form_container: Optional[ft.Container] = None
        self._form_visible = False

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
        if self._dlg:
            self._dlg.on_dismiss = self._handle_dismiss
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
        for dd in (self._dd_estado, self._dd_day, self._dd_servicio):
            if dd:
                dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)

    def _apply_tf_palette(self, tf: ft.TextField):
        tf.bgcolor = self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
        tf.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.hint_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=12)
        tf.cursor_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.border_color = self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)
        tf.focused_border_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _dialog_width(self) -> int:
        win = self.app_state.window_width or (getattr(self.page, "window_width", None)) or 1024
        try:
            win_int = int(win)
        except Exception:
            win_int = 1024
        return max(520, min(760, win_int - 120))

    def _get_servicio_precio(self, servicio_id: Optional[str]) -> Decimal:
        if not servicio_id:
            return Decimal("0.00")
        cached = self._serv_price_map.get(servicio_id)
        if cached is not None:
            return cached
        try:
            data = self.servicios.get_by_id(int(servicio_id))
        except Exception:
            data = None
        if data:
            precio = Decimal(str(data.get("precio_base") or data.get("PRECIO_BASE") or 0)).quantize(Decimal("0.01"))
            self._serv_price_map[servicio_id] = precio
            return precio
        return Decimal("0.00")

    def _update_precio_preview(self):
        servicio_id = self._dd_servicio.value if self._dd_servicio else None
        base = self._get_servicio_precio(servicio_id)
        val_txt = (self._tf_valor.value or "").strip() if self._tf_valor else "0"
        val_txt = val_txt.replace(",", ".")
        try:
            desc = _to_decimal(val_txt)
        except Exception:
            desc = Decimal("0.00")
        if desc < Decimal("0.00"):
            desc = Decimal("0.00")
        if desc > base:
            desc = base
        final = (base - desc).quantize(Decimal("0.01"))
        self._precio_base_actual = base
        self._precio_final_actual = final
        if self._txt_precio_servicio:
            self._txt_precio_servicio.value = f"Servicio: ${base:.2f}"
        if self._txt_precio_final:
            self._txt_precio_final.value = f"Total con promo: ${final:.2f}"
        if self.page:
            try:
                self.page.update()
            except Exception:
                pass

    def _on_servicio_change(self):
        self._update_precio_preview()

    def _on_valor_change(self):
        self._update_precio_preview()

    def _set_day_chip_state(self, chip: ft.Control, value: bool) -> None:
        if hasattr(chip, "selected"):
            chip.selected = value  # type: ignore[attr-defined]
        else:
            setattr(chip, "value", value)

    def _get_day_chip_state(self, chip: ft.Control) -> bool:
        if hasattr(chip, "selected"):
            return bool(getattr(chip, "selected"))
        return bool(getattr(chip, "value", False))

    def _set_form_visible(self, visible: bool):
        self._form_visible = visible
        if self._form_container:
            self._form_container.visible = visible
        if not visible:
            self._editing_id = None
        if self.page:
            try:
                self.page.update()
            except Exception:
                pass

    # ---------------------- Data ----------------------
    def _load_servicios_opts(self):
        self._serv_opts.clear()
        self._serv_price_map = {}
        try:
            lista = self.servicios.listar(activo=True) or []
        except Exception:
            lista = []
        for s in lista:
            sid = s.get("id") or s.get("ID") or s.get("id_servicio")
            nom = s.get("nombre") or s.get("NOMBRE") or f"Servicio {sid}"
            precio = s.get("precio_base") or s.get("PRECIO_BASE") or s.get("precio")
            if sid is not None:
                sid_str = str(int(sid))
                precio_dec = Decimal(str(precio or "0")).quantize(Decimal("0.01"))
                self._serv_opts.append({"id": sid_str, "nombre": str(nom), "precio": precio_dec})
                self._serv_price_map[sid_str] = precio_dec

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
            width=self._dialog_width(),
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
                ft.Container(expand=2, content=ft.Text("Promoción", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(width=130, content=ft.Text("Días", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(expand=2, content=ft.Text("Servicio", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(width=90, content=ft.Text("Descuento", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(width=80, content=ft.Text("Final $", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
                ft.Container(width=90, content=ft.Text("Acciones", size=12, weight=ft.FontWeight.W_500, color=self.colors.get("FG_COLOR"))),
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
        final_txt = ft.Text(self._format_precio_final(r), size=12, color=self.colors.get("FG_COLOR"))

        btn_edit = ft.IconButton(ft.icons.EDIT, tooltip="Editar", icon_size=16,
                                 on_click=lambda e, _rid=rid: self._start_edit(_rid))
        btn_del = ft.IconButton(ft.icons.DELETE, tooltip="Eliminar", icon_size=16,
                                on_click=lambda e, _rid=rid: self._confirm_delete(_rid))

        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(width=64, content=sw),
                ft.Container(expand=2, content=nombre),
                ft.Container(width=130, content=dias_txt),
                ft.Container(expand=2, content=serv_txt),
                ft.Container(width=90, content=desc_txt),
                ft.Container(width=80, content=final_txt),
                ft.Container(width=90, content=ft.Row([btn_edit, btn_del], spacing=4)),
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
        chips_row: List[ft.Control] = []
        for key, label, _col in days:
            if HAS_FILTER_CHIP:
                chip = ft.FilterChip(label=label, selected=False, dense=True)  # type: ignore[attr-defined]
            else:
                chip = ft.Checkbox(label=label, value=False, scale=0.9)
            self._chips_days[key] = chip
            chips_row.append(chip)

        # Servicio (una sola selección)
        self._dd_servicio = ft.Dropdown(
            label="Servicio",
            width=320,
            options=[ft.dropdown.Option(opt["id"], opt["nombre"]) for opt in self._serv_opts],
            dense=True,
            on_change=lambda e: self._on_servicio_change(),
        )
        self._dd_servicio.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)

        # Valor fijo
        self._tf_valor = ft.TextField(
            label="Descuento fijo ($)",
            hint_text="Monto a restar (ej. 20.00)",
            height=40,
            text_size=12,
            width=160,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: self._on_valor_change(),
        )
        self._apply_tf_palette(self._tf_valor)

        self._txt_precio_servicio = ft.Text(
            "Servicio: $0.00",
            size=11,
            color=self.colors.get("FG_COLOR"),
        )
        self._txt_precio_final = ft.Text(
            "Total con promo: $0.00",
            size=11,
            color=self.colors.get("FG_COLOR"),
        )

        # Acciones
        self._btn_save = ft.FilledButton("Guardar", icon=ft.icons.SAVE, on_click=lambda e: self._save())
        self._btn_cancel = ft.TextButton("Cancelar edición", on_click=lambda e: self._cancel_edit())

        column = ft.Column(
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
                ft.Row(spacing=10, controls=[self._dd_servicio, self._tf_valor]),
                ft.Row(
                    spacing=16,
                    controls=[
                        self._txt_precio_servicio,
                        self._txt_precio_final,
                    ],
                ),

                ft.Row(spacing=8, controls=[self._btn_cancel, self._btn_save]),
            ],
        )
        self._form_container = ft.Container(
            visible=self._form_visible,
            animate_opacity=200,
            animate_size=200,
            content=column,
        )
        self._update_precio_preview()
        return self._form_container

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
        self._set_form_visible(True)

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
        self._set_form_visible(True)

    def _clear_form(self):
        if self._tf_nombre: self._tf_nombre.value = ""
        if self._sw_activa: self._sw_activa.value = True
        for chip in self._chips_days.values():
            self._set_day_chip_state(chip, False)
        if self._dd_servicio: self._dd_servicio.value = None
        if self._tf_valor: self._tf_valor.value = ""
        self._update_precio_preview()

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
                self._set_day_chip_state(self._chips_days[key], _b(col))

        # Servicio
        sid = r.get(E_PROMO.SERVICIO_ID.value)
        if sid is not None and self._dd_servicio:
            self._dd_servicio.value = str(int(sid))

        # Tipo/Valor
        if self._tf_valor:
            self._tf_valor.value = _txt(r.get(E_PROMO.VALOR_DESC.value))
        self._update_precio_preview()

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
        dias_values = {
            col: 1 if self._get_day_chip_state(self._chips_days[key]) else 0
            for key, col in days_map.items()
        }
        if sum(dias_values.values()) <= 0:
            return None, "Selecciona al menos un día."

        if not self._dd_servicio or not self._dd_servicio.value:
            return None, "Selecciona un servicio."
        try:
            servicio_id = int(self._dd_servicio.value)
        except Exception:
            return None, "Servicio inv?lido."

        tipo_desc = E_PROMO_TIPO.MONTO.value
        val_txt = (self._tf_valor.value or '').strip() if self._tf_valor else '0'
        val_txt = val_txt.replace(',', '.')
        try:
            val_dec = _to_decimal(val_txt)
        except Exception:
            return None, "Valor de descuento inv?lido."
        if val_dec < 0:
            return None, "Monto fijo debe ser ? 0."

        precio_base = self._get_servicio_precio(str(self._dd_servicio.value))
        if val_dec > precio_base:
            return None, f"El descuento (${val_dec:.2f}) no puede superar el precio del servicio (${precio_base:.2f})."
        precio_final = (precio_base - val_dec).quantize(Decimal('0.01'))

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
            E_PROMO.PRECIO_FINAL.value: float(precio_final),
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
                precio_final=data[E_PROMO.PRECIO_FINAL.value],
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
            self._set_form_visible(False)
            self._refresh_rows()
            self._rebuild_list()
            self.page.update()
        else:
            self._snack_error(f"❌ {res.get('message', 'No se pudo guardar')}")

    def _cancel_edit(self):
        self._editing_id = None
        self._clear_form()
        self._set_form_visible(False)

    # ---------------------- Helpers UI ----------------------
    def _format_descuento(self, r: Dict[str, Any]) -> str:
        tipo = (r.get(E_PROMO.TIPO_DESC.value) or "").lower()
        val = _to_decimal(r.get(E_PROMO.VALOR_DESC.value) or 0)
        if tipo == E_PROMO_TIPO.PORCENTAJE.value:
            pct_txt = format(val.normalize(), "f").rstrip("0").rstrip(".")
            pct_txt = pct_txt or "0"
            return f"-{pct_txt}%"
        return f"-${val:.2f}"

    def _format_precio_final(self, r: Dict[str, Any]) -> str:
        final_val = r.get(E_PROMO.PRECIO_FINAL.value)
        final_dec: Optional[Decimal] = None
        if final_val is not None:
            try:
                final_dec = Decimal(str(final_val)).quantize(Decimal("0.01"))
            except Exception:
                final_dec = None
        if final_dec is None:
            base = self._get_servicio_precio(str(r.get(E_PROMO.SERVICIO_ID.value) or ""))
            desc = _to_decimal(r.get(E_PROMO.VALOR_DESC.value) or 0)
            if desc > base:
                desc = base
            final_dec = (base - desc).quantize(Decimal("0.01"))
        if final_dec < Decimal("0.00"):
            final_dec = Decimal("0.00")
        return f"${final_dec:.2f}"

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
        for opt in self._serv_opts:
            if opt['id'] == sid_str:
                return opt['nombre']
        # Intentar obtenerlo directamente si no est? en cache
        try:
            data = self.servicios.get_by_id(int(sid_str))
        except Exception:
            data = None
        if data:
            nombre = data.get('nombre') or data.get('NOMBRE') or f'Servicio {sid_str}'
            precio = Decimal(str(data.get('precio_base') or data.get('PRECIO_BASE') or 0)).quantize(Decimal('0.01'))
            self._serv_opts.append({'id': sid_str, 'nombre': nombre, 'precio': precio})
            self._serv_price_map[sid_str] = precio
            return nombre
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
        self._handle_dismiss()

    def _handle_dismiss(self, _=None):
        if not self._mounted:
            return
        self._mounted = False
        if self._on_after_close:
            try:
                self._on_after_close()
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
