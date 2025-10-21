# app/views/containers/home/agenda/agenda_container.py
from __future__ import annotations
import flet as ft
from datetime import date, datetime, timedelta, time
from typing import Any, Dict, List, Optional

# Core global
from app.config.application.app_state import AppState
from app.views.containers.nvar.layout_controller import LayoutController

# Models
from app.models.agenda_model import AgendaModel
from app.models.trabajadores_model import TrabajadoresModel

# Enums
from app.core.enums.e_usuarios import E_USU_ROL
from app.core.enums.e_agenda import E_AGENDA, E_AGENDA_ESTADO

# Builders
from app.ui.builders.table_builder_expansive import TableBuilderExpansive
from app.ui.builders.table_builder import TableBuilder
from app.ui.sorting.sort_manager import SortManager


# BotonFactory
from app.ui.factory.boton_factory import (
    boton_aceptar, boton_cancelar, boton_editar, boton_borrar
)

# ----------------------------- Helpers -----------------------------
def _txt(v: Any) -> str:
    return "" if v is None else str(v)

def _hfmt(v: Any) -> str:
    try:
        if isinstance(v, str):
            return v
        if isinstance(v, time):
            return v.strftime("%H:%M")
        if isinstance(v, datetime):
            return v.strftime("%H:%M")
        return str(v)
    except Exception:
        return ""

def _datefmt(d: date) -> str:
    try:
        return d.strftime("%a %d/%m/%Y")
    except Exception:
        return str(d)

def _parse_hhmm(hhmm: str) -> time:
    hh, mm = [int(x) for x in (hhmm or "").strip().split(":")]
    return time(hour=hh, minute=mm)

# ===================================================================
#  Agenda por día (expansible)
# ===================================================================
class AgendaContainer(ft.Container):
    """
    - Barra superior: rango (semana), selección de fecha base, filtro por estado/trabajador, botón "Nueva cita".
    - Tabla expansible: 1 fila por día (rango semanal). Al expandir: tabla hija con citas del día.
    - Cualquier rol puede crear/editar/eliminar (según requerimiento indicado).
    """

    def __init__(self):
        super().__init__(expand=True)

        # Core
        self.app_state = AppState()
        self.page = self.app_state.page
        self.colors = self.app_state.get_colors()
        self.layout_ctrl = LayoutController()

        # Permisos
        sess = None
        try:
            sess = self.page.client_storage.get("app.user") if self.page else None
        except Exception:
            pass
        role = (sess.get("rol") if isinstance(sess, dict) else "") or ""
        self.is_root = (role or "").lower() == E_USU_ROL.ROOT.value

        self.can_add = True
        self.can_edit = True
        self.can_delete = True

        # Estado general
        self._mounted = False
        self._theme_listener = None
        self._layout_listener = None

        # Modelos
        self.model = AgendaModel()
        self.trab_model = TrabajadoresModel()

        # Semana y filtros
        today = date.today()
        self.base_day: date = today
        self.days_span: int = 7

        self.filter_estado: Optional[str] = None
        self.filter_trab_id: Optional[int] = None

        # Refs
        # { "YYYY-MM-DD:<id or -1>": { key->control } }
        self._edit_controls: Dict[str, Dict[str, ft.Control]] = {}
        self._day_tables: Dict[str, TableBuilder] = {}

        # UI base
        self._build_toolbar()
        self._build_body()

        # Listeners
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

    # ---------------------------------------------------------------
    # Toolbar
    # ---------------------------------------------------------------
    def _build_toolbar(self):
        self.dp_base = ft.DatePicker()
        self.base_day_btn = ft.TextButton(
            _datefmt(self.base_day),
            on_click=lambda e: self._open_datepicker(self.dp_base, self._on_pick_base_date)
        )

        self.prev_btn = ft.IconButton(ft.icons.ARROW_BACK, tooltip="Semana anterior", on_click=lambda e: self._move_span(-1))
        self.next_btn = ft.IconButton(ft.icons.ARROW_FORWARD, tooltip="Siguiente semana", on_click=lambda e: self._move_span(1))
        self.today_btn = ft.TextButton("Hoy", on_click=lambda e: self._set_today())

        self.estado_dd = ft.Dropdown(
            width=150, label="Estado",
            options=[ft.dropdown.Option("", "Todos")] + [ft.dropdown.Option(s.value, s.value.title()) for s in E_AGENDA_ESTADO],
            on_change=lambda e: self._apply_estado_filter()
        )
        self.estado_dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        self.trab_dd = ft.Dropdown(width=220, label="Trabajador", on_change=lambda e: self._apply_trab_filter())
        self.trab_dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        self._fill_trabajadores_dropdown()

        self.new_btn = ft.FilledButton("Nueva cita", icon=ft.icons.ADD, on_click=lambda e: self._insert_new_for_day(self.base_day))
        self.clear_btn = ft.IconButton(ft.icons.CLEAR_ALL, tooltip="Limpiar filtros", on_click=lambda e: self._clear_filters())

        self.toolbar = ft.Row(
            controls=[
                self.prev_btn, self.base_day_btn, self.next_btn, self.today_btn,
                ft.VerticalDivider(),
                self.estado_dd, self.trab_dd, self.clear_btn,
                ft.Container(expand=True),
                self.new_btn,
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=8,
        )

    def _open_datepicker(self, dp: ft.DatePicker, on_change):
        dp.on_change = lambda e: on_change(e.control.value)
        self.page.overlay.append(dp)
        dp.pick_date()

    def _on_pick_base_date(self, d: Optional[date]):
        if d:
            self.base_day = d
            self.base_day_btn.text = _datefmt(self.base_day)
            self._refrescar_dataset()

    def _move_span(self, weeks: int):
        self.base_day = self.base_day + timedelta(days=7 * weeks)
        self.base_day_btn.text = _datefmt(self.base_day)
        self._refrescar_dataset()

    def _set_today(self):
        self.base_day = date.today()
        self.base_day_btn.text = _datefmt(self.base_day)
        self._refrescar_dataset()

    def _apply_estado_filter(self):
        v = (self.estado_dd.value or "").strip()
        self.filter_estado = v or None
        self._refrescar_dataset()

    def _apply_trab_filter(self):
        v = (self.trab_dd.value or "").strip()
        try:
            self.filter_trab_id = int(v) if v else None
        except Exception:
            self.filter_trab_id = None
        self._refrescar_dataset()

    def _clear_filters(self):
        self.estado_dd.value = ""
        self.trab_dd.value = ""
        self.filter_estado = None
        self.filter_trab_id = None
        self._refrescar_dataset()

    def _fill_trabajadores_dropdown(self):
        try:
            rows = self.trab_model.listar(estado=None) or []
        except Exception:
            rows = []
        opts = [ft.dropdown.Option("", "Todos")]
        for r in rows:
            tid = r.get("id") or r.get("ID") or r.get("trabajador_id")
            nom = r.get("nombre") or r.get("NOMBRE") or r.get("name") or f"Trabajador {tid}"
            if tid is not None:
                opts.append(ft.dropdown.Option(str(tid), nom))
        self.trab_dd.options = opts

    # ---------------------------------------------------------------
    # Body
    # ---------------------------------------------------------------
    def _build_body(self):
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

        # columnas del grupo (días)
        self.GDIA = "dia"       # date ISO
        self.GRES = "resumen"   # resumen del día
        self.GCNT = "citas"     # conteo

        columns = [
            {"key": self.GDIA, "title": "Día", "width": 220, "align": "start", "formatter": self._fmt_day_title},
            {"key": self.GRES, "title": "Resumen", "width": 520, "align": "start", "formatter": self._fmt_day_resumen},
            {"key": self.GCNT, "title": "N°", "width": 60, "align": "center", "formatter": lambda v, r: ft.Text(str(v or 0))},
        ]

        self.expansive = TableBuilderExpansive(
            group="agenda_dias",
            columns=columns,
            row_id_key=self.GDIA,
            detail_builder=self._detail_builder_for_day,
        )

        col = self.table_container.content
        col.controls.clear()
        col.controls.append(self.toolbar)
        col.controls.append(ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)))
        col.controls.append(self.expansive.build())

        self.content = ft.Container(
            expand=True,
            bgcolor=self.colors.get("BG_COLOR"),
            padding=20,
            content=self.table_container,
        )

        self._refrescar_dataset()

    # ---------------------------------------------------------------
    # Dataset
    # ---------------------------------------------------------------
    def _range_days(self) -> List[date]:
        base = self.base_day
        monday = base - timedelta(days=(base.weekday() % 7))  # 0 lunes .. 6 domingo
        return [monday + timedelta(days=i) for i in range(self.days_span)]

    def _fetch_group_rows(self) -> List[Dict[str, Any]]:
        ds = self._range_days()
        start_dt = datetime.combine(ds[0], time.min)
        end_dt = datetime.combine(ds[-1], time.max) if ds else datetime.combine(self.base_day, time.max)

        rows = self.model.listar_por_rango(
            inicio=start_dt,
            fin=end_dt,
            estado=self.filter_estado,
            trabajador_id=self.filter_trab_id
        ) or []

        # index por día (a partir de fecha_inicio)
        by_day: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            ini = r.get(E_AGENDA.INICIO.value)
            if not ini:
                continue
            if isinstance(ini, str):
                try:
                    ini = datetime.fromisoformat(ini)
                except Exception:
                    continue
            d = ini.date()
            key = d.isoformat()
            by_day.setdefault(key, []).append(r)

        groups = []
        for d in ds:
            key = d.isoformat()
            citas = by_day.get(key, [])
            # resumen: primeras 3 con hora - cliente
            pills = []
            sorted_day = sorted(citas, key=lambda x: (x.get(E_AGENDA.INICIO.value) or ""))
            for ev in sorted_day[:3]:
                h = _hfmt(ev.get(E_AGENDA.INICIO.value))
                cli = ev.get(E_AGENDA.CLIENTE_NOM.value) or ""
                pills.append(f"{h} {cli}".strip())
            groups.append({
                self.GDIA: key,
                self.GRES: " · ".join(pills) if pills else "—",
                self.GCNT: len(citas),
                "_date_obj": d,
            })
        return groups

    def _refrescar_dataset(self):
        data = self._fetch_group_rows()
        self.expansive.set_rows(data)
        self._safe_update()

    # ---------------------------------------------------------------
    # Formatters (grupo día)
    # ---------------------------------------------------------------
    def _fmt_day_title(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        try:
            d = row.get("_date_obj") or date.fromisoformat(value)
        except Exception:
            d = self.base_day
        return ft.Row([
            ft.Text(_datefmt(d), size=14, weight="bold", color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            ft.Container(expand=True),
            ft.IconButton(ft.icons.ADD, tooltip="Nueva cita en este día",
                          on_click=lambda e, d=d: self._insert_new_for_day(d))
        ], alignment=ft.MainAxisAlignment.START)

    def _fmt_day_resumen(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        return ft.Text(_txt(value), size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

    # ---------------------------------------------------------------
    # Detail builder (tabla hija por día)
    # ---------------------------------------------------------------
    def _detail_builder_for_day(self, group_row: Dict[str, Any]) -> ft.Control:
        DIA = group_row[self.GDIA]  # ISO
        self._day_tables.pop(DIA, None)

        ID      = E_AGENDA.ID.value
        # alias de UI (derivados de INICIO/FIN y TITULO)
        H_INI   = "hora_inicio"
        H_FIN   = "hora_fin"
        CLIENTE = E_AGENDA.CLIENTE_NOM.value
        SERV    = "servicio"
        TRAB    = E_AGENDA.TRABAJADOR_ID.value
        EST     = E_AGENDA.ESTADO.value
        NOTAS   = E_AGENDA.NOTAS.value

        columns = [
            {"key": H_INI,   "title": "Inicio",    "width": 90,  "align": "center", "formatter": lambda v, r, dia=DIA: self._fmt_hora_cell(v, r, dia, key=H_INI)},
            {"key": H_FIN,   "title": "Fin",       "width": 90,  "align": "center", "formatter": lambda v, r, dia=DIA: self._fmt_hora_cell(v, r, dia, key=H_FIN)},
            {"key": CLIENTE, "title": "Cliente",   "width": 220, "align": "start",  "formatter": lambda v, r, dia=DIA: self._fmt_text_cell(v, r, dia, key=CLIENTE, hint='Nombre cliente')},
            {"key": SERV,    "title": "Servicio",  "width": 180, "align": "start",  "formatter": lambda v, r, dia=DIA: self._fmt_text_cell(v, r, dia, key=SERV, hint='Servicio')},
            {"key": TRAB,    "title": "Trabajador","width": 200, "align": "start",  "formatter": lambda v, r, dia=DIA: self._fmt_trab_cell(v, r, dia, key=TRAB)},
            {"key": EST,     "title": "Estado",    "width": 140, "align": "start",  "formatter": lambda v, r, dia=DIA: self._fmt_estado_cell(v, r, dia, key=EST)},
            {"key": NOTAS,   "title": "Notas",     "width": 280, "align": "start",  "formatter": lambda v, r, dia=DIA: self._fmt_text_cell(v, r, dia, key=NOTAS, hint='Notas/Ubicación')},
        ]

        tb = TableBuilder(
            group=f"agenda_citas_{DIA}",
            columns=columns,
            id_key=ID,
            sort_manager=SortManager(),              # ← agregado
            on_accept=lambda row, dia=DIA: self._on_accept_row(dia, row),
            on_cancel=lambda row, dia=DIA: self._on_cancel_row(dia, row),
            on_edit=lambda row, dia=DIA: self._on_edit_row(dia, row),
            on_delete=lambda row, dia=DIA: self._on_delete_row(dia, row),
            dense_text=True,
            auto_scroll_new=True,
            actions_title="Acciones",
        )

        tb.attach_actions_builder(lambda r, is_new, dia=DIA: self._actions_builder(dia, r, is_new))

        d_obj = group_row.get("_date_obj") or date.fromisoformat(DIA)
        rows = self.model.listar_por_dia(
            dia=d_obj,
            estado=self.filter_estado,
            trabajador_id=self.filter_trab_id
        ) or []

        # Derivar alias de UI a partir de columnas reales
        for r in rows:
            ini = r.get(E_AGENDA.INICIO.value)
            fin = r.get(E_AGENDA.FIN.value)
            if isinstance(ini, str):
                try:
                    ini = datetime.fromisoformat(ini)
                except Exception:
                    ini = None
            if isinstance(fin, str):
                try:
                    fin = datetime.fromisoformat(fin)
                except Exception:
                    fin = None
            r["hora_inicio"] = _hfmt(ini)
            r["hora_fin"] = _hfmt(fin)
            r["servicio"] = r.get(E_AGENDA.TITULO.value, "")

        self._day_tables[DIA] = tb
        wrapper = ft.Container(padding=10, content=tb.build())
        tb.set_rows(rows)
        return wrapper

    # ---------------------------------------------------------------
    # Formatters celdas (grilla hija)
    # ---------------------------------------------------------------
    def _ensure_edit_map(self, dia_iso: str, row_id: Any):
        key = f"{dia_iso}:{row_id if row_id is not None else -1}"
        if key not in self._edit_controls:
            self._edit_controls[key] = {}
        return key

    def _fmt_hora_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(_hfmt(value), size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf = ft.TextField(value=_hfmt(value) if not row.get("_is_new") else "", hint_text="HH:MM",
                          keyboard_type=ft.KeyboardType.DATETIME, text_size=12,
                          content_padding=ft.padding.symmetric(horizontal=8, vertical=6))
        self._apply_textfield_palette(tf)
        def validar(_):
            ok = True
            try:
                t = (tf.value or "").strip()
                hh, mm = [int(x) for x in t.split(":")]
                ok = (0 <= hh < 24 and 0 <= mm < 60)
            except Exception:
                ok = False
            tf.border_color = None if ok else ft.colors.RED
            self._safe_update()
        tf.on_change = validar
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = tf
        return tf

    def _fmt_text_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str, hint: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(_txt(value), size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf = ft.TextField(value=_txt(value) if not row.get("_is_new") else "", hint_text=hint, text_size=12,
                          content_padding=ft.padding.symmetric(horizontal=8, vertical=6))
        self._apply_textfield_palette(tf)
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = tf
        return tf

    def _fmt_trab_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            label = row.get("trabajador_nombre") or str(value or "")
            return ft.Text(label, size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        # dropdown trabajadores
        opts = []
        try:
            trs = self.trab_model.listar(estado=None) or []
        except Exception:
            trs = []
        for r in trs:
            tid = r.get("id") or r.get("ID") or r.get("trabajador_id")
            nom = r.get("nombre") or r.get("NOMBRE") or r.get("name") or f"Trabajador {tid}"
            if tid is not None:
                opts.append(ft.dropdown.Option(str(tid), nom))
        dd = ft.Dropdown(value=str(value) if value is not None else None, options=opts, width=200, dense=True)
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = dd
        return dd

    def _fmt_estado_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(str(value or ""), size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        dd = ft.Dropdown(
            value=value or E_AGENDA_ESTADO.PROGRAMADA.value,
            options=[ft.dropdown.Option(s.value, s.value.title()) for s in E_AGENDA_ESTADO],
            width=140, dense=True
        )
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = dd
        return dd

    # ---------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------
    def _actions_builder(self, dia_iso: str, row: Dict[str, Any], is_new: bool) -> ft.Control:
        rid = row.get(E_AGENDA.ID.value)
        if is_new or bool(row.get("_is_new")) or (rid in (None, "", 0)):
            return ft.Row(
                [ft.IconButton(icon=ft.icons.CHECK, tooltip="Aceptar", on_click=lambda e, r=row: self._on_accept_row(dia_iso, r)),
                 ft.IconButton(icon=ft.icons.CLOSE, tooltip="Cancelar", on_click=lambda e, r=row: self._on_cancel_row(dia_iso, r))],
                spacing=6, alignment=ft.MainAxisAlignment.START
            )
        if row.get("_editing", False):
            return ft.Row(
                [boton_aceptar(lambda e, r=row: self._on_accept_row(dia_iso, r)),
                 boton_cancelar(lambda e, r=row: self._on_cancel_row(dia_iso, r))],
                spacing=6, alignment=ft.MainAxisAlignment.START
            )
        return ft.Row(
            [boton_editar(lambda e, r=row: self._on_edit_row(dia_iso, r)),
             boton_borrar(lambda e, r=row: self._on_delete_row(dia_iso, r))],
            spacing=6, alignment=ft.MainAxisAlignment.START
        )

    # ---------------------------------------------------------------
    # CRUD
    # ---------------------------------------------------------------
    def _insert_new_for_day(self, d: date):
        if not self.can_add:
            self._snack_error("❌ No tienes permisos para crear citas.")
            return
        dia_iso = d.isoformat()
        tb = self._day_tables.get(dia_iso)
        if not tb:
            self.expansive.expand_row(dia_iso)
            tb = self._day_tables.get(dia_iso)
        if not tb:
            return
        row = {
            E_AGENDA.ID.value: None,
            # alias de UI
            "hora_inicio": "",
            "hora_fin": "",
            "servicio": "",
            E_AGENDA.CLIENTE_NOM.value: "",
            E_AGENDA.TRABAJADOR_ID.value: None,
            E_AGENDA.ESTADO.value: E_AGENDA_ESTADO.PROGRAMADA.value,
            E_AGENDA.NOTAS.value: "",
            "_is_new": True,
            "_editing": True,
        }
        tb.add_row(row, auto_scroll=True)
        self._safe_update()

    def _on_edit_row(self, dia_iso: str, row: Dict[str, Any]):
        if not self.can_edit:
            return
        row["_editing"] = True
        self._refresh_day_table(dia_iso)

    def _on_cancel_row(self, dia_iso: str, row: Dict[str, Any]):
        if row.get("_is_new"):
            tb = self._day_tables.get(dia_iso)
            if tb:
                rows = tb.get_rows()
                try:
                    idx = next(i for i, r in enumerate(rows) if r is row or r.get("_is_new"))
                    tb.remove_row_at(idx)
                except Exception:
                    pass
            self._edit_controls.pop(f"{dia_iso}:-1", None)
            self._safe_update()
            return
        row["_editing"] = False
        self._refresh_day_table(dia_iso)

    def _on_accept_row(self, dia_iso: str, row: Dict[str, Any]):
        if not (self.can_add or self.can_edit):
            self._snack_error("❌ No tienes permisos.")
            return

        key = f"{dia_iso}:{row.get(E_AGENDA.ID.value) if row.get(E_AGENDA.ID.value) is not None else -1}"
        ctrls = self._edit_controls.get(key, {})

        def _val(tf: Optional[ft.TextField]) -> str:
            return (tf.value or "").strip() if tf else ""

        # recoger campos (alias UI)
        h_ini = _val(ctrls.get("hora_inicio"))
        h_fin = _val(ctrls.get("hora_fin"))
        cliente = _val(ctrls.get(E_AGENDA.CLIENTE_NOM.value))
        servicio = _val(ctrls.get("servicio"))
        notas = _val(ctrls.get(E_AGENDA.NOTAS.value))
        estado_dd: ft.Dropdown = ctrls.get(E_AGENDA.ESTADO.value)  # type: ignore
        trab_dd: ft.Dropdown = ctrls.get(E_AGENDA.TRABAJADOR_ID.value)  # type: ignore
        estado = estado_dd.value if estado_dd else E_AGENDA_ESTADO.PROGRAMADA.value
        trabajador_id = int(trab_dd.value) if trab_dd and (trab_dd.value or "").isdigit() else None

        # validar
        errores = []
        try:
            ti = _parse_hhmm(h_ini); tf_ = _parse_hhmm(h_fin)
            if tf_ <= ti: errores.append("Fin debe ser > Inicio")
        except Exception:
            errores.append("Horas inválidas (usa HH:MM)")
        if len(servicio) < 2: errores.append("Servicio inválido")
        if len(cliente) < 2: errores.append("Cliente inválido")
        if trabajador_id is None: errores.append("Selecciona un trabajador")

        if errores:
            self._snack_error("❌ " + " / ".join(errores)); return

        d = date.fromisoformat(dia_iso)
        inicio_dt = datetime.combine(d, _parse_hhmm(h_ini))
        fin_dt = datetime.combine(d, _parse_hhmm(h_fin))

        # usuario para auditoría (si está disponible)
        uid = None
        try:
            sess = self.page.client_storage.get("app.user")
            uid = (sess or {}).get("id_usuario")
        except Exception:
            uid = None

        if row.get(E_AGENDA.ID.value) in (None, "", 0):
            res = self.model.crear_cita(
                titulo=servicio,
                inicio=inicio_dt,
                fin=fin_dt,
                todo_dia=False,
                color=None,
                notas=notas,
                trabajador_id=trabajador_id,
                cliente_nombre=cliente,
                cliente_tel=None,
                estado=estado,
                created_by=uid
            )
            if res.get("status") == "success":
                self._snack_ok("✅ Cita creada.")
            else:
                self._snack_error(f"❌ {res.get('message', 'No se pudo crear')}")
        else:
            rid = int(row.get(E_AGENDA.ID.value))
            res = self.model.actualizar_cita(
                cita_id=rid,
                titulo=servicio,
                inicio=inicio_dt,
                fin=fin_dt,
                todo_dia=False,
                color=None,
                notas=notas,
                trabajador_id=trabajador_id,
                cliente_nombre=cliente,
                cliente_tel=None,
                estado=estado,
                updated_by=uid
            )
            if res.get("status") == "success":
                self._snack_ok("✅ Cambios guardados.")
            else:
                self._snack_error(f"❌ {res.get('message', 'No se pudo actualizar')}")

        self._edit_controls.pop(key, None)
        self._refresh_day_table(dia_iso)
        self._refrescar_dataset()

    def _on_delete_row(self, dia_iso: str, row: Dict[str, Any]):
        if not self.can_delete:
            self._snack_error("❌ No tienes permisos para eliminar.")
            return
        rid = row.get(E_AGENDA.ID.value)
        if not rid:
            return
        res = self.model.eliminar_cita(int(rid))
        if res.get("status") == "success":
            self._snack_ok("🗑️ Cita eliminada.")
            self._refresh_day_table(dia_iso)
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ {res.get('message', 'No se pudo eliminar')}")

    def _refresh_day_table(self, dia_iso: str):
        tb = self._day_tables.get(dia_iso)
        if not tb:
            return
        d = date.fromisoformat(dia_iso)
        rows = self.model.listar_por_dia(
            dia=d,
            estado=self.filter_estado,
            trabajador_id=self.filter_trab_id
        ) or []
        for r in rows:
            ini = r.get(E_AGENDA.INICIO.value)
            fin = r.get(E_AGENDA.FIN.value)
            if isinstance(ini, str):
                try: ini = datetime.fromisoformat(ini)
                except Exception: ini = None
            if isinstance(fin, str):
                try: fin = datetime.fromisoformat(fin)
                except Exception: fin = None
            r["hora_inicio"] = _hfmt(ini)
            r["hora_fin"] = _hfmt(fin)
            r["servicio"] = r.get(E_AGENDA.TITULO.value, "")
        tb.set_rows(rows)
        self._safe_update()

    # ---------------------------------------------------------------
    # Theme/Layout/Update
    # ---------------------------------------------------------------
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

    def _on_theme_changed(self):
        self.colors = self.app_state.get_colors()
        self._recolor_ui()
        self._refrescar_dataset()

    def _on_layout_changed(self, expanded: bool):
        self._safe_update()

    def _apply_textfield_palette(self, tf: ft.TextField):
        tf.bgcolor = self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
        tf.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.label_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf.hint_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf.cursor_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.border_color = self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)
        tf.focused_border_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _recolor_ui(self):
        if isinstance(self.content, ft.Container):
            self.content.bgcolor = self.colors.get("BG_COLOR")
        self.table_container.bgcolor = self.colors.get("BG_COLOR")
        self.estado_dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        self.trab_dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        self._safe_update()

    def _safe_update(self):
        p = getattr(self, "page", None)
        if p:
            try: p.update()
            except AssertionError: pass

    # ---------------------------------------------------------------
    # Notificaciones
    # ---------------------------------------------------------------
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
