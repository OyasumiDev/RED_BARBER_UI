from __future__ import annotations
import flet as ft
from datetime import date, datetime, timedelta, time
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Core global
from app.config.application.app_state import AppState
from app.views.containers.nvar.layout_controller import LayoutController

# Models
from app.models.agenda_model import AgendaModel
from app.models.trabajadores_model import TrabajadoresModel
from app.models.servicios_model import ServiciosModel  # catálogo de servicios
from app.models.cortes_model import CortesModel

# Enums
from app.core.enums.e_usuarios import E_USU_ROL
from app.core.enums.e_agenda import E_AGENDA, E_AGENDA_ESTADO

# Builders
from app.ui.builders.table_builder_expansive import TableBuilderExpansive
from app.ui.builders.table_builder import TableBuilder
from app.ui.sorting.sort_manager import SortManager

# Modal de fecha/hora (AM/PM o 24h; sin segundos)
from app.views.modals.modal_datetime_picker import DateTimeModalPicker

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
DEFAULT_DURATION_MIN = 60  # duración por defecto para nuevas citas

DOT = "\u00b7"      # ·
EM_DASH = "\u2014"  # —
NBSP = "\u00a0"     # no-break space


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


def _valid_hhmm(hhmm: str) -> bool:
    try:
        hh, mm = [int(x) for x in (hhmm or "").strip().split(":")]
        return 0 <= hh < 24 and 0 <= mm < 60
    except Exception:
        return False


def _only_digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


# ===================================================================
#  Agenda por día (expansible) — SIN NOTAS
# ===================================================================
class AgendaContainer(ft.Container):
    """
    - Toolbar compacta: filtros (estado) + 'Nueva cita'.
    - Tabla expansible: 1 fila por día (SIEMPRE muestra la semana).
    - Rango de trabajo: semana actual (lunes→domingo) sin navegación manual.
    - Integrada con Trabajadores/Servicios + Teléfono cliente.
    - UX 14": columnas angostas, tipografía 11, acciones compactas.
    - SIN campo 'Notas' en UI ni en guardado.
    """

    def __init__(self):
        super().__init__(expand=True)

        # Core
        self.app_state = AppState()
        self.page = self.app_state.page
        # ✅ paleta del área AGENDA vía AppState
        self.colors = self.app_state.get_colors("agenda")
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
        self.serv_model = ServiciosModel()  # catálogo (sin pivot con trabajador)
        self.cortes_model = CortesModel()

        # Cache simple de trabajadores (id -> nombre) para etiquetas
        self._trab_cache: Dict[int, str] = {}

        # Rango y filtros
        self.base_day: date = date.today()   # semana actual
        self.days_span: int = 7
        self.filter_estado: Optional[str] = None

        # Refs
        self._edit_controls: Dict[str, Dict[str, ft.Control]] = {}
        self._day_tables: Dict[str, TableBuilder] = {}        # día ISO -> TableBuilder
        self._editing_rows: Dict[str, set[Any]] = {}

        # Día actualmente expandido (para que 'Nueva cita' use el contexto)
        self._opened_day_iso: Optional[str] = None

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
    # Toolbar (compacta, sin navegación de fechas)
    # ---------------------------------------------------------------
    def _build_toolbar(self):
        pal = self.colors

        # Dropdown Estado
        self.estado_dd = ft.Dropdown(
            label="Estado",
            width=160,
            options=[ft.dropdown.Option("", "Todos")] + [
                ft.dropdown.Option(s.value, s.value.title()) for s in E_AGENDA_ESTADO
            ],
            on_change=lambda e: self._apply_estado_filter(),
            dense=True,
        )
        self.estado_dd.text_style = ft.TextStyle(
            color=pal.get("FG_COLOR", ft.colors.ON_SURFACE), size=12
        )

        # Botón limpiar
        self.clear_btn = ft.IconButton(
            ft.icons.CLEAR_ALL,
            tooltip="Limpiar filtros",
            on_click=lambda e: self._clear_filters(),
            icon_size=16,
            style=ft.ButtonStyle(padding=0),
        )

        # "Nueva cita"
        self.new_btn = ft.FilledButton(
            "Nueva cita",
            icon=ft.icons.ADD,
            on_click=lambda e: self._insert_new_from_modal_global(),
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(6, 6),
                bgcolor=pal.get("ACCENT"),
                color=pal.get("ON_PRIMARY", ft.colors.WHITE),
            ),
        )

        # Layout responsivo
        self.toolbar = ft.ResponsiveRow(
            controls=[
                ft.Container(content=self.estado_dd, col={"xs": 6, "md": 3, "lg": 2}),
                ft.Container(content=self.clear_btn, alignment=ft.alignment.center_left,
                             col={"xs": 2, "md": 1, "lg": 1}),
                ft.Container(col={"xs": 0, "md": 6, "lg": 7}, expand=True),
                ft.Container(content=self.new_btn, alignment=ft.alignment.center_right,
                             col={"xs": 4, "md": 2, "lg": 2}),
            ],
            columns=12,
            spacing=8,
            run_spacing=8,
        )

    def _apply_estado_filter(self):
        v = (self.estado_dd.value or "").strip()
        self.filter_estado = v or None
        self._refrescar_dataset()

    def _clear_filters(self):
        self.estado_dd.value = ""
        self.filter_estado = None
        self._refrescar_dataset()

    # ---------------------------------------------------------------
    # Body
    # ---------------------------------------------------------------
    def _build_body(self):
        pal = self.colors

        self.table_container = ft.Container(
            expand=True,
            alignment=ft.alignment.top_center,
            bgcolor=pal.get("BG_COLOR"),
            content=ft.Column(
                controls=[],
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

        # columnas del grupo (días)
        self.GDIA = "dia"       # date ISO
        self.GRES = "resumen"   # resumen del día
        self.GCNT = "citas"     # conteo

        columns = [
            {"key": self.GDIA, "title": "D\u00eda", "width": 180, "align": "start", "formatter": self._fmt_day_title},
            {"key": self.GRES, "title": "Resumen", "width": 360, "align": "start", "formatter": self._fmt_day_resumen},
            {"key": self.GCNT, "title": "N\u00b0", "width": 42, "align": "center",
             "formatter": lambda v, r: ft.Text(str(v or 0), size=11)},
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
        col.controls.append(ft.Divider(color=pal.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)))
        col.controls.append(self.expansive.build())

        self.content = ft.Container(
            expand=True,
            bgcolor=pal.get("BG_COLOR"),
            padding=6,
            content=self.table_container,
        )

        self._refrescar_dataset()

    # ---------------------------------------------------------------
    # Dataset — semana actual (SIEMPRE muestra los 7 días)
    # ---------------------------------------------------------------
    def _range_bounds_with_days(self) -> Tuple[datetime, datetime, List[date]]:
        base = self.base_day
        monday = base - timedelta(days=(base.weekday() % 7))  # 0 lunes .. 6 domingo
        days = [monday + timedelta(days=i) for i in range(self.days_span)]
        start_dt = datetime.combine(days[0], time.min)
        end_dt = datetime.combine(days[-1], time.max)
        return start_dt, end_dt, days

    def _fetch_group_rows(self) -> List[Dict[str, Any]]:
        start_dt, end_dt, all_days = self._range_bounds_with_days()

        # Intento con filtro; si queda vacío, fallback sin filtro para no dejar la vista en blanco por un mal estado
        try:
            rows = self.model.listar_por_rango(inicio=start_dt, fin=end_dt, estado=self.filter_estado) or []
        except Exception:
            rows = []
        if not rows and self.filter_estado is not None:
            try:
                rows = self.model.listar_por_rango(inicio=start_dt, fin=end_dt, estado=None) or []
            except Exception:
                rows = []

        # Agrupar por día
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
            key = ini.date().isoformat()
            by_day.setdefault(key, []).append(r)

        # Construir grupos para TODA la semana (aunque no haya citas)
        groups: List[Dict[str, Any]] = []
        for d in all_days:
            key = d.isoformat()
            citas = sorted(by_day.get(key, []), key=lambda x: (x.get(E_AGENDA.INICIO.value) or ""))
            pills: List[str] = []
            for ev in citas[:3]:
                h = _hfmt(ev.get(E_AGENDA.INICIO.value))
                cli = ev.get(E_AGENDA.CLIENTE_NOM.value) or ""
                pills.append(f"{h} {cli}".strip())
            groups.append({
                self.GDIA: key,
                self.GRES: (f" {DOT} ").join(pills) if pills else EM_DASH,
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
        row_controls = [
            ft.Text(
                _datefmt(d),
                size=12,
                weight="bold",
                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            ),
            ft.Container(expand=True),
        ]

        num_registros = int(row.get(self.GCNT, 0) or 0)
        if num_registros <= 0:
            row_controls.append(
                ft.IconButton(
                    ft.icons.ADD,
                    tooltip="Nueva cita en este d\u00eda",
                    on_click=lambda e, d=d: self._insert_new_for_day(d),
                    icon_size=16,
                    style=ft.ButtonStyle(padding=0),
                )
            )

        return ft.Row(row_controls, alignment=ft.MainAxisAlignment.START)

    def _fmt_day_resumen(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        return ft.Text(_txt(value), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

    # ---------------------------------------------------------------
    # Detail builder (tabla hija por día) — SIN NOTAS
    # ---------------------------------------------------------------
    def _detail_builder_for_day(self, group_row: Dict[str, Any]) -> ft.Control:
        DIA = group_row[self.GDIA]  # ISO
        self._day_tables.pop(DIA, None)
        self._opened_day_iso = DIA

        ID      = E_AGENDA.ID.value
        H_INI   = "hora_inicio"
        H_FIN   = "hora_fin"
        CLIENTE = E_AGENDA.CLIENTE_NOM.value
        TEL     = E_AGENDA.CLIENTE_TEL.value
        SERV_ID = "servicio_id"      # UI: FK servicio
        SERV_TX = "servicio_txt"     # UI: nombre servicio
        TRAB    = E_AGENDA.TRABAJADOR_ID.value
        EST     = E_AGENDA.ESTADO.value

        columns = [
            {"key": H_INI,   "title": "Inicio",    "width": 58,  "align": "center",
             "formatter": lambda v, r, dia=DIA: self._fmt_hora_cell(v, r, dia, key=H_INI)},
            {"key": H_FIN,   "title": "Fin",       "width": 58,  "align": "center",
             "formatter": lambda v, r, dia=DIA: self._fmt_hora_cell(v, r, dia, key=H_FIN)},
            {"key": CLIENTE, "title": "Cliente",   "width": 170, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_text_cell(v, r, dia, key=CLIENTE, hint='Nombre cliente')},
            {"key": TEL,     "title": "Tel\u00e9fono", "width": 108, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_tel_cell(v, r, dia, key=TEL)},
            {"key": SERV_ID, "title": "Servicio",  "width": 170, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_servicio_cell(r.get(SERV_ID), r, dia, key=SERV_ID)},
            {"key": TRAB,    "title": "Trab.",     "width": 140, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_trab_cell(v, r, dia, key=TRAB)},
            {"key": EST,     "title": "Estado",    "width": 108, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_estado_cell(v, r, dia, key=EST)},
        ]

        tb = TableBuilder(
            group=f"agenda_citas_{DIA}",
            columns=columns,
            id_key=ID,
            sort_manager=SortManager(),
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
        ) or []

        # Normalizar filas de BD a celdas UI
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
            r[H_INI] = _hfmt(ini)
            r[H_FIN] = _hfmt(fin)
            r[SERV_TX] = r.get(E_AGENDA.TITULO.value, "")  # nombre textual guardado
            # Preseleccionar FK de servicio si viene de BD
            r[SERV_ID] = r.get("servicio_id")
            # Etiqueta del trabajador
            try:
                tid_val = r.get(E_AGENDA.TRABAJADOR_ID.value)
                tid_int = int(tid_val) if tid_val is not None else None
            except Exception:
                tid_int = None
            r["trabajador_nombre"] = self._get_trab_name(tid_int) if tid_int is not None else ""

        editing_set = self._editing_rows.get(DIA, set())
        if editing_set:
            for r in rows:
                rid = r.get(E_AGENDA.ID.value)
                if rid is None:
                    continue
                try:
                    rid_val = int(rid)
                except Exception:
                    rid_val = rid
                if rid_val in editing_set:
                    r["_editing"] = True

        self._day_tables[DIA] = tb
        wrapper = ft.Container(padding=4, content=tb.build())
        tb.set_rows(rows)
        return wrapper

    # ---------------------------------------------------------------
    # Integración con el modal (nuevo/compacto) y contexto de día
    # ---------------------------------------------------------------
    def _insert_new_from_modal_global(self):
        """Botón 'Nueva cita' de la toolbar. Si hay día abierto, solo pedir HORA."""
        if not self.can_add:
            self._snack_error("No tienes permisos para crear citas.")
            return

        default_day: Optional[date] = None
        if self._opened_day_iso:
            try:
                default_day = date.fromisoformat(self._opened_day_iso)
            except Exception:
                default_day = None

        # Sin día abierto → pedir fecha+hora (limitado a la semana visible)
        def on_selected(values: Sequence[datetime] | Sequence[str]):
            for dt in self._coerce_dt_list(values):
                self._create_prefilled_row_for_datetime(dt)

        picker = DateTimeModalPicker(
            on_confirm=on_selected,
            auto_range=False,
            require_time=True,
            use_24h=False,
            return_format="datetime",
            width=360,
            cell_size=22,
            title="Nueva cita",
            subtitle="Selecciona la fecha y la hora de inicio.",
        )

        picker.open(self.page)
        start_dt, end_dt, days = self._range_bounds_with_days()
        enabled = [d.isoformat() for d in days]
        picker.set_enabled_dates(enabled)

        if default_day and default_day.isoformat() in enabled:
            try:
                picker._calendar._toggle(default_day)  # preseleccionar pero permitir cambiar
            except Exception:
                pass

    def _insert_new_for_day(self, d: date):
        """Botón '+' en la fila del día → pide solo hora."""
        if not self.can_add:
            self._snack_error("No tienes permisos para crear citas.")
            return

        def on_selected(values: Sequence[datetime] | Sequence[str], _d=d):
            for dt in self._coerce_dt_list(values):
                if dt.date() == _d:
                    self._create_prefilled_row_for_datetime(dt)
                    break

        picker = DateTimeModalPicker(
            on_confirm=on_selected,
            auto_range=False,
            require_time=True,
            use_24h=False,
            return_format="datetime",
            width=360,
            cell_size=22,
            title=f"Nueva cita ({d.strftime('%d/%m/%Y')})",
            subtitle="Selecciona la hora para este d\u00eda.",
        )

        picker.open(self.page)
        picker.set_enabled_dates([d.isoformat()])

    def _coerce_dt_list(self, values: Sequence[datetime] | Sequence[str]) -> List[datetime]:
        """Normaliza a lista de datetime (descarta None/formatos inválidos)."""
        out: List[datetime] = []
        for v in values:
            if isinstance(v, datetime):
                out.append(v)
            elif isinstance(v, str):
                v = v.strip()
                if not v:
                    continue
                dt = None
                try:
                    dt = datetime.fromisoformat(v)
                except Exception:
                    try:
                        dt = datetime.strptime(v, "%Y-%m-%d %H:%M")
                    except Exception:
                        dt = None
                if dt is not None:
                    out.append(dt)
        return out

    def _ensure_group_exists_and_expand(self, d: date):
        dia_iso = d.isoformat()
        if self.expansive.find_row(dia_iso) is not None:
            self.expansive.expand_row(dia_iso)
            self._opened_day_iso = dia_iso
            return

        new_group = {
            self.GDIA: dia_iso,
            self.GRES: EM_DASH,
            self.GCNT: 0,
            "_date_obj": d,
        }
        self.expansive.insert_row(new_group, position="end")
        self.expansive.expand_row(dia_iso)
        self._opened_day_iso = dia_iso
        self._safe_update()

    def _create_prefilled_row_for_datetime(self, dt_inicio: datetime):
        """
        Crea nueva fila con hora de inicio = hora propuesta (editable).
        'Fin' queda como estimado (inicio + DEFAULT_DURATION_MIN) y es read-only.
        """
        d = dt_inicio.date()
        self._ensure_group_exists_and_expand(d)
        dia_iso = d.isoformat()
        tb = self._day_tables.get(dia_iso)
        if not tb:
            self.expansive.expand_row(dia_iso)
            tb = self._day_tables.get(dia_iso)
            if not tb:
                return

        fin_dt = dt_inicio + timedelta(minutes=DEFAULT_DURATION_MIN)

        row = {
            E_AGENDA.ID.value: None,
            "hora_inicio": dt_inicio.strftime("%H:%M"),     # propuesta editable
            "hora_fin": fin_dt.strftime("%H:%M"),           # estimado read-only
            E_AGENDA.CLIENTE_NOM.value: "",
            E_AGENDA.CLIENTE_TEL.value: "",
            "servicio_id": None,
            "servicio_txt": "",
            E_AGENDA.TRABAJADOR_ID.value: None,
            E_AGENDA.ESTADO.value: E_AGENDA_ESTADO.PROGRAMADA.value,
            "_is_new": True,
            "_editing": True,
        }
        tb.add_row(row, auto_scroll=True)
        self._safe_update()

    # ---------------------------------------------------------------
    # Celdas (grilla hija)
    # ---------------------------------------------------------------
    def _ensure_edit_map(self, dia_iso: str, row_id: Any):
        key = f"{dia_iso}:{row_id if row_id is not None else -1}"
        if key not in self._edit_controls:
            self._edit_controls[key] = {}
        return key

    def _fmt_hora_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(_hfmt(value), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        is_fin = (key == "hora_fin")
        tf = ft.TextField(
            value=_hfmt(value),
            hint_text="HH:MM",
            keyboard_type=ft.KeyboardType.DATETIME,
            text_size=11,
            content_padding=ft.padding.symmetric(horizontal=6, vertical=4),
            read_only=is_fin,
            width=56,
        )
        self._apply_textfield_palette(tf)

        def validar(_):
            if is_fin:
                return
            ok = _valid_hhmm(tf.value or "")
            tf.border_color = None if ok else ft.colors.RED
            self._safe_update()

        tf.on_change = validar
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = tf
        return tf

    def _fmt_text_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str, hint: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(_txt(value), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf = ft.TextField(
            value=_txt(value),
            hint_text=hint,
            text_size=11,
            content_padding=ft.padding.symmetric(horizontal=6, vertical=4),
            width=170 if key == E_AGENDA.CLIENTE_NOM.value else 150,
        )
        self._apply_textfield_palette(tf)
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = tf
        return tf

    def _fmt_tel_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(_txt(value), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf = ft.TextField(
            value=_txt(value),
            hint_text="Tel\u00e9fono",
            text_size=11,
            keyboard_type=ft.KeyboardType.PHONE,
            content_padding=ft.padding.symmetric(horizontal=6, vertical=4),
            width=108,
        )
        self._apply_textfield_palette(tf)
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = tf
        return tf

    # --------- Trabajadores: cache/lookup y celda ----------
    def _load_trab_options(self) -> List[ft.dropdown.Option]:
        """Carga trabajadores desde el modelo, refresca cache y devuelve opciones para Dropdown."""
        opciones: List[ft.dropdown.Option] = []
        cache: Dict[int, str] = {}
        try:
            trs = self.trab_model.listar(estado=None) or []
        except Exception:
            trs = []
        for r in trs:
            tid = (r.get("id") or r.get("ID") or r.get("trabajador_id") or r.get("id_trabajador"))
            nom = r.get("nombre") or r.get("NOMBRE") or r.get("name") or (f"Trabajador {tid}" if tid is not None else "")
            if tid is None:
                continue
            try:
                tid_int = int(tid)
            except Exception:
                continue
            cache[tid_int] = nom
            opciones.append(ft.dropdown.Option(str(tid_int), nom))
        self._trab_cache = cache
        return opciones

    def _ensure_trab_cache(self):
        if not self._trab_cache:
            self._load_trab_options()

    def _get_trab_name(self, tid: Optional[int]) -> str:
        if tid is None:
            return ""
        self._ensure_trab_cache()
        try:
            return self._trab_cache.get(int(tid), str(tid))
        except Exception:
            return str(tid)

    def _fmt_trab_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            label = row.get("trabajador_nombre")
            if not label:
                try:
                    label = self._get_trab_name(int(value)) if value is not None else ""
                except Exception:
                    label = str(value or "")
            return ft.Text(label, size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        # En edición: dropdown con cache actualizada
        opts = self._load_trab_options()
        dd = ft.Dropdown(value=str(value) if value is not None else None, options=opts, width=140, dense=True)
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=11)

        def _on_change(_):
            try:
                sel = next((o for o in dd.options if o.key == dd.value), None)
                row["trabajador_nombre"] = sel.text if sel else ""
            except Exception:
                row["trabajador_nombre"] = ""
        dd.on_change = _on_change

        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = dd
        return dd

    def _fmt_servicio_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        if not en_edicion:
            label = row.get("servicio_txt") or row.get(E_AGENDA.TITULO.value) or ""
            return ft.Text(label, size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        # Servicios del catálogo (sin filtrar por trabajador)
        opciones: List[ft.dropdown.Option] = []
        try:
            servicios = self.serv_model.listar(activo=True) or []
        except Exception:
            servicios = []
        for s in servicios:
            sid = s.get("id") or s.get("ID") or s.get("id_servicio")
            nom = s.get("nombre") or s.get("NOMBRE")
            if sid is not None and nom:
                opciones.append(ft.dropdown.Option(str(sid), nom))

        dd = ft.Dropdown(value=str(value) if value is not None else None, options=opciones, width=170, dense=True)
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=11)
        self._edit_controls[k][key] = dd

        # Mantener también el nombre textual seleccionado (para titulo en modelo)
        def _on_serv_change(e):
            try:
                sel = next((o for o in dd.options if o.key == dd.value), None)
                row["servicio_txt"] = sel.text if sel else ""
            except Exception:
                row["servicio_txt"] = ""
        dd.on_change = _on_serv_change

        return dd

    # ----- estado final & sellado de fin -----
    def _estado_final(self, v: Optional[str]) -> bool:
        v = (v or "").lower()
        return v in {
            E_AGENDA_ESTADO.COMPLETADA.value.lower(),
            E_AGENDA_ESTADO.CANCELADA.value.lower(),
        }

    def _fmt_estado_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(str(value or ""), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        dd = ft.Dropdown(
            value=value or E_AGENDA_ESTADO.PROGRAMADA.value,
            options=[ft.dropdown.Option(s.value, s.value.title()) for s in E_AGENDA_ESTADO],
            width=108, dense=True
        )
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=11)
        k = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
        self._edit_controls[k][key] = dd

        def _on_estado_change(e):
            k2 = self._ensure_edit_map(dia_iso, row.get(E_AGENDA.ID.value))
            fin_tf: ft.TextField = self._edit_controls.get(k2, {}).get("hora_fin")  # type: ignore
            if not fin_tf:
                return
            if self._estado_final(dd.value):
                now_txt = datetime.now().strftime("%H:%M")
                fin_tf.value = now_txt
                fin_tf.read_only = True
            else:
                fin_tf.read_only = True
            self._safe_update()

        dd.on_change = _on_estado_change
        return dd

    # ---------- Chequeo de solapes ----------
    @staticmethod
    def _overlap(a_ini: datetime, a_fin: datetime, b_ini: datetime, b_fin: datetime) -> bool:
        """Hay solape si el inicio de uno es antes del fin del otro y viceversa."""
        return (a_ini < b_fin) and (b_ini < a_fin)

    def _find_conflict_for_trabajador(
        self,
        trabajador_id: int,
        inicio_dt: datetime,
        fin_dt: datetime,
        *,
        exclude_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Devuelve la CITA (dict) que entra en conflicto para el trabajador dado,
        considerando SOLO citas en estado PROGRAMADA. Si no hay conflicto, None.
        """
        try:
            rows = self.model.listar_por_dia(dia=inicio_dt.date(), estado=None) or []
        except Exception:
            rows = []

        for r in rows:
            # excluir la misma cita en edición
            rid = r.get(E_AGENDA.ID.value)
            try:
                rid_int = int(rid) if rid is not None else None
            except Exception:
                rid_int = None
            if exclude_id is not None and rid_int == exclude_id:
                continue

            # trabajador debe coincidir
            tid = r.get(E_AGENDA.TRABAJADOR_ID.value)
            try:
                tid_int = int(tid) if tid is not None else None
            except Exception:
                tid_int = None
            if tid_int != trabajador_id:
                continue

            # solo bloquea si está PROGRAMADA
            estado = (r.get(E_AGENDA.ESTADO.value) or "").strip().lower()
            if estado != E_AGENDA_ESTADO.PROGRAMADA.value.lower():
                continue

            # parseo horarios
            r_ini = r.get(E_AGENDA.INICIO.value)
            r_fin = r.get(E_AGENDA.FIN.value)
            try:
                if isinstance(r_ini, str):
                    r_ini = datetime.fromisoformat(r_ini)
                if isinstance(r_fin, str):
                    r_fin = datetime.fromisoformat(r_fin)
            except Exception:
                continue
            if not isinstance(r_ini, datetime) or not isinstance(r_fin, datetime):
                continue

            if self._overlap(inicio_dt, fin_dt, r_ini, r_fin):
                return r

        return None

    def _create_corte_from_cita(
        self,
        row: Dict[str, Any],
        cita_id: int,
        fecha_fin: datetime,
        usuario_id: Optional[int],
    ) -> Dict[str, Any]:
        """Genera (si procede) un corte AGENDADO a partir de la cita completada."""
        if not self.cortes_model:
            return {"status": "skipped", "message": "Modelo de cortes no disponible."}

        try:
            cita_db = self.model.get_by_id(int(cita_id)) or {}
        except Exception:
            cita_db = {}

        merged: Dict[str, Any] = dict(cita_db or {})
        merged.setdefault(E_AGENDA.ID.value, cita_id)
        merged.setdefault(E_AGENDA.TRABAJADOR_ID.value, row.get(E_AGENDA.TRABAJADOR_ID.value))
        merged.setdefault("servicio_id", row.get("servicio_id"))
        merged.setdefault(E_AGENDA.CLIENTE_NOM.value, row.get(E_AGENDA.CLIENTE_NOM.value))
        if "total" not in merged:
            merged["total"] = row.get("total")
        if "precio_unit" not in merged:
            merged["precio_unit"] = row.get("precio_unit")
        merged.setdefault(E_AGENDA.TITULO.value, row.get(E_AGENDA.TITULO.value) or row.get("servicio_txt"))
        merged[E_AGENDA.FIN.value] = fecha_fin

        try:
            return self.cortes_model.crear_corte_desde_cita(
                merged,
                fecha_corte=fecha_fin,
                created_by=usuario_id,
            )
        except Exception as ex:
            return {"status": "error", "message": str(ex)}

    @staticmethod
    def _format_corte_result(result: Optional[Dict[str, Any]]) -> Optional[str]:
        if not result:
            return None
        status = result.get("status")
        if status == "success":
            return "Cita completada y corte registrado."
        if status == "exists":
            return "Cita completada (el corte ya existía)."
        if status in ("error", "skipped"):
            msg = result.get("message")
            return f"Cita completada (sin corte automático: {msg})." if msg else None
        return None

    # ---------------------------------------------------------------
    # Actions / CRUD (iconos compactos)
    # ---------------------------------------------------------------
    def _actions_builder(self, dia_iso: str, row: Dict[str, Any], is_new: bool) -> ft.Control:
        def _ico(icon, tip, on_click):
            return ft.IconButton(icon=icon, tooltip=tip, on_click=on_click,
                                 icon_size=14, style=ft.ButtonStyle(padding=0))

        rid = row.get(E_AGENDA.ID.value)
        if is_new or bool(row.get("_is_new")) or (rid in (None, "", 0)):
            return ft.Row(
                [
                    _ico(ft.icons.CHECK, "Aceptar",
                         lambda e, r=row: self._on_accept_row(dia_iso, r)),
                    _ico(ft.icons.CLOSE, "Cancelar",
                         lambda e, r=row: self._on_cancel_row(dia_iso, r)),
                ],
                spacing=4, alignment=ft.MainAxisAlignment.START
            )
        if row.get("_editing", False):
            return ft.Row(
                [
                    _ico(ft.icons.CHECK, "Guardar",
                         lambda e, r=row: self._on_accept_row(dia_iso, r)),
                    _ico(ft.icons.CLOSE, "Cancelar",
                         lambda e, r=row: self._on_cancel_row(dia_iso, r)),
                ],
                spacing=4, alignment=ft.MainAxisAlignment.START
            )
        acciones: List[ft.Control] = []
        estado_actual = (row.get(E_AGENDA.ESTADO.value) or "").strip().lower()
        if estado_actual == E_AGENDA_ESTADO.PROGRAMADA.value.lower():
            acciones.append(
                _ico(
                    ft.icons.CHECK_CIRCLE,
                    "Marcar como completada",
                    lambda e, r=row: self._quick_update_estado(dia_iso, r, E_AGENDA_ESTADO.COMPLETADA.value),
                )
            )
            acciones.append(
                _ico(
                    ft.icons.CLOSE,
                    "Cancelar cita",
                    lambda e, r=row: self._quick_update_estado(dia_iso, r, E_AGENDA_ESTADO.CANCELADA.value),
                )
            )

        acciones.extend(
            [
                _ico(ft.icons.EDIT, "Editar", lambda e, r=row: self._on_edit_row(dia_iso, r)),
                _ico(ft.icons.DELETE, "Borrar", lambda e, r=row: self._on_delete_row(dia_iso, r)),
            ]
        )
        return ft.Row(acciones, spacing=4, alignment=ft.MainAxisAlignment.START)

    def _on_edit_row(self, dia_iso: str, row: Dict[str, Any]):
        if not self.can_edit:
            return
        row["_editing"] = True
        rid = row.get(E_AGENDA.ID.value)
        if rid is not None:
            try:
                rid_int = int(rid)
            except Exception:
                rid_int = rid
            self._editing_rows.setdefault(dia_iso, set()).add(rid_int)
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
        rid = row.get(E_AGENDA.ID.value)
        if rid is not None:
            try:
                rid_int = int(rid)
            except Exception:
                rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
        self._refresh_day_table(dia_iso)

    def _on_accept_row(self, dia_iso: str, row: Dict[str, Any]):
        if not (self.can_add or self.can_edit):
            self._snack_error("No tienes permisos.")
            return

        key = f"{dia_iso}:{row.get(E_AGENDA.ID.value) if row.get(E_AGENDA.ID.value) is not None else -1}"
        ctrls = self._edit_controls.get(key, {})

        def _val(tf: Optional[ft.TextField]) -> str:
            return (tf.value or "").strip() if tf else ""

        h_ini = _val(ctrls.get("hora_inicio"))
        h_fin_visible = _val(ctrls.get("hora_fin"))  # visible (informativo) o sello
        cliente = _val(ctrls.get(E_AGENDA.CLIENTE_NOM.value))
        tel     = _val(ctrls.get(E_AGENDA.CLIENTE_TEL.value))
        # SIN NOTAS: no leemos ni guardamos notas

        estado_dd: ft.Dropdown = ctrls.get(E_AGENDA.ESTADO.value)  # type: ignore
        trab_dd: ft.Dropdown   = ctrls.get(E_AGENDA.TRABAJADOR_ID.value)  # type: ignore
        serv_dd: ft.Dropdown   = ctrls.get("servicio_id")  # type: ignore

        estado = estado_dd.value if estado_dd else E_AGENDA_ESTADO.PROGRAMADA.value
        trabajador_id = int(trab_dd.value) if trab_dd and (trab_dd.value or "").isdigit() else None
        servicio_id = int(serv_dd.value) if serv_dd and (serv_dd.value or "").isdigit() else None
        # Nombre textual del servicio (para 'titulo' en modelo)
        servicio_txt = ""
        if serv_dd:
            try:
                sel = next((o for o in serv_dd.options if o.key == serv_dd.value), None)
                servicio_txt = sel.text if sel else ""
            except Exception:
                servicio_txt = ""

        # Sanitizar teléfono (opcional)
        tel_digits = _only_digits(tel)
        if tel and len(tel_digits) < 7:
            self._snack_error("Teléfono inválido (mín. 7 dígitos)")
            return

        errores = []
        if not _valid_hhmm(h_ini):
            errores.append("Hora de inicio inválida (usa HH:MM)")
        if len(cliente) < 2:
            errores.append("Cliente inválido")
        if trabajador_id is None:
            errores.append("Selecciona un trabajador")
        if servicio_id is None:
            errores.append("Selecciona un servicio")

        if errores:
            self._snack_error(" / ".join(errores))
            return

        d = date.fromisoformat(dia_iso)
        inicio_dt = datetime.combine(d, _parse_hhmm(h_ini))

        # Determinar FIN:
        if self._estado_final(estado):
            fin_dt = datetime.now().replace(second=0, microsecond=0)
            if _valid_hhmm(h_fin_visible):
                try:
                    fin_dt = datetime.combine(d, _parse_hhmm(h_fin_visible))
                except Exception:
                    pass
            if fin_dt <= inicio_dt:
                self._snack_error("Fin debe ser > Inicio (sello de finalización)")
                return
        else:
            if _valid_hhmm(h_fin_visible):
                fin_dt = datetime.combine(d, _parse_hhmm(h_fin_visible))
            else:
                fin_dt = inicio_dt + timedelta(minutes=DEFAULT_DURATION_MIN)

        # ---- BLOQUEO POR SOLAPE DE TRABAJADOR (solo contra PROGRAMADAS) ----
        if trabajador_id is not None:
            exclude = None
            try:
                if row.get(E_AGENDA.ID.value) not in (None, "", 0):
                    exclude = int(row.get(E_AGENDA.ID.value))
            except Exception:
                exclude = None

            conflicto = self._find_conflict_for_trabajador(
                trabajador_id=trabajador_id,
                inicio_dt=inicio_dt,
                fin_dt=fin_dt,
                exclude_id=exclude,
            )
            if conflicto:
                tname = self._get_trab_name(trabajador_id)
                try:
                    c_ini = conflicto.get(E_AGENDA.INICIO.value)
                    c_fin = conflicto.get(E_AGENDA.FIN.value)
                    if isinstance(c_ini, str): c_ini = datetime.fromisoformat(c_ini)
                    if isinstance(c_fin, str): c_fin = datetime.fromisoformat(c_fin)
                    rango_txt = f"{c_ini.strftime('%H:%M')}–{c_fin.strftime('%H:%M')}" if isinstance(c_ini, datetime) and isinstance(c_fin, datetime) else "en ese horario"
                except Exception:
                    rango_txt = "en ese horario"
                self._snack_error(f"{tname or 'El trabajador'} ya tiene una cita PROGRAMADA {rango_txt}. Cambia la hora o el trabajador.")
                return

        uid = None
        try:
            sess = self.page.client_storage.get("app.user")
            uid = (sess or {}).get("id_usuario")
        except Exception:
            uid = None

        if row.get(E_AGENDA.ID.value) in (None, "", 0):
            res = self.model.crear_cita(
                titulo=servicio_txt or None,
                inicio=inicio_dt,
                fin=fin_dt,
                todo_dia=False,
                color=None,
                notas=None,  # SIN NOTAS
                trabajador_id=trabajador_id,
                servicio_id=servicio_id,  # FK servicio
                cliente_nombre=cliente,
                cliente_tel=tel_digits or None,
                estado=estado,
                created_by=uid
            )
        else:
            rid = int(row.get(E_AGENDA.ID.value))
            res = self.model.actualizar_cita(
                cita_id=rid,
                titulo=servicio_txt or None,
                inicio=inicio_dt,
                fin=fin_dt,
                todo_dia=False,
                color=None,
                notas=None,  # SIN NOTAS
                trabajador_id=trabajador_id,
                servicio_id=servicio_id,  # FK servicio
                cliente_nombre=cliente,
                cliente_tel=tel_digits or None,
                estado=estado,
                updated_by=uid
            )

        if res.get("status") == "success":
            self._snack_ok("Cambios guardados.")
        else:
            self._snack_error(res.get('message', 'No se pudo guardar'))

        self._edit_controls.pop(key, None)
        rid = row.get(E_AGENDA.ID.value)
        if rid is not None:
            try:
                rid_int = int(rid)
            except Exception:
                rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
        self._refresh_day_table(dia_iso)
        self._refrescar_dataset()

    def _on_delete_row(self, dia_iso: str, row: Dict[str, Any]):
        if not self.can_delete:
            self._snack_error("No tienes permisos para eliminar.")
            return
        rid = row.get(E_AGENDA.ID.value)
        if not rid:
            return
        res = self.model.eliminar_cita(int(rid))
        if res.get("status") == "success":
            self._snack_ok("Cita eliminada.")
            try:
                rid_int = int(rid)
            except Exception:
                rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
            self._refresh_day_table(dia_iso)
            self._refrescar_dataset()
        else:
            self._snack_error(res.get('message', 'No se pudo eliminar'))

    def _quick_update_estado(self, dia_iso: str, row: Dict[str, Any], nuevo_estado: str):
        if not self.can_edit:
            self._snack_error("Sin permisos para actualizar.")
            return
        rid = row.get(E_AGENDA.ID.value)
        if rid in (None, "", 0):
            self._snack_error("Registra la cita antes de actualizar el estado.")
            return
        try:
            rid_int = int(rid)
        except Exception:
            rid_int = rid

        inicio = row.get(E_AGENDA.INICIO.value)
        if isinstance(inicio, str):
            try:
                inicio_dt = datetime.fromisoformat(inicio)
            except Exception:
                inicio_dt = datetime.combine(date.fromisoformat(dia_iso), _parse_hhmm(row.get("hora_inicio", "00:00")))
        elif isinstance(inicio, datetime):
            inicio_dt = inicio
        else:
            inicio_dt = datetime.combine(date.fromisoformat(dia_iso), _parse_hhmm(row.get("hora_inicio", "00:00")))

        fin = row.get(E_AGENDA.FIN.value)
        if isinstance(fin, str):
            try:
                fin_dt = datetime.fromisoformat(fin)
            except Exception:
                fin_dt = inicio_dt + timedelta(minutes=DEFAULT_DURATION_MIN)
        elif isinstance(fin, datetime):
            fin_dt = fin
        else:
            fin_dt = inicio_dt + timedelta(minutes=DEFAULT_DURATION_MIN)

        if nuevo_estado == E_AGENDA_ESTADO.COMPLETADA.value:
            fin_actual = datetime.now().replace(second=0, microsecond=0)
            if fin_actual <= inicio_dt:
                fin_actual = inicio_dt + timedelta(minutes=DEFAULT_DURATION_MIN)
            fin_dt = fin_actual

        titulo = row.get(E_AGENDA.TITULO.value) or row.get("servicio_txt") or None
        trabajador_id = row.get(E_AGENDA.TRABAJADOR_ID.value)
        if trabajador_id is not None:
            try:
                trabajador_id = int(trabajador_id)
            except Exception:
                pass
        cliente_nombre = row.get(E_AGENDA.CLIENTE_NOM.value)
        cliente_tel = _only_digits(row.get(E_AGENDA.CLIENTE_TEL.value) or "") or None
        servicio_id = row.get("servicio_id")
        if servicio_id is not None:
            try:
                servicio_id = int(servicio_id)
            except Exception:
                pass
        cantidad = row.get("cantidad")
        precio_unit = row.get("precio_unit")
        total = row.get("total")

        try:
            cantidad = int(cantidad) if cantidad is not None else None
        except Exception:
            cantidad = None
        try:
            precio_unit = float(precio_unit) if precio_unit is not None else None
        except Exception:
            precio_unit = None
        try:
            total = float(total) if total is not None else None
        except Exception:
            total = None

        todo_dia = bool(row.get(E_AGENDA.TODO_DIA.value, False))
        color = row.get(E_AGENDA.COLOR.value)

        uid = None
        try:
            sess = self.page.client_storage.get("app.user") if self.page else None
            uid = (sess or {}).get("id_usuario")
        except Exception:
            uid = None

        res = self.model.actualizar_cita(
            cita_id=rid_int,
            titulo=titulo,
            inicio=inicio_dt,
            fin=fin_dt,
            todo_dia=todo_dia,
            color=color,
            notas=None,  # SIN NOTAS
            trabajador_id=trabajador_id,
            cliente_nombre=cliente_nombre,
            cliente_tel=cliente_tel,
            estado=nuevo_estado,
            servicio_id=servicio_id,
            cantidad=cantidad,
            precio_unit=precio_unit,
            total=total,
            updated_by=uid,
        )

        corte_result = None
        if res.get("status") == "success":
            if nuevo_estado == E_AGENDA_ESTADO.COMPLETADA.value:
                # Efecto secundario opcional: no rompe UI si falla
                try:
                    corte_result = self._create_corte_from_cita(row, rid_int, fin_dt, uid)
                    msg = self._format_corte_result(corte_result) or "Cita marcada como completada."
                except Exception:
                    msg = "Cita marcada como completada."
            else:
                msg = "Cita cancelada."
            self._snack_ok(msg)
        else:
            self._snack_error(res.get('message', 'No se pudo actualizar el estado'))
            return

        self._refresh_day_table(dia_iso)
        self._refrescar_dataset()

    def _refresh_day_table(self, dia_iso: str):
        tb = self._day_tables.get(dia_iso)
        if not tb:
            return
        d = date.fromisoformat(dia_iso)
        rows = self.model.listar_por_dia(
            dia=d,
            estado=self.filter_estado,
        ) or []
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
            r["servicio_txt"] = r.get(E_AGENDA.TITULO.value, "")
            r["servicio_id"] = r.get("servicio_id")
            # Etiqueta del trabajador
            try:
                tid_val = r.get(E_AGENDA.TRABAJADOR_ID.value)
                tid_int = int(tid_val) if tid_val is not None else None
            except Exception:
                tid_int = None
            r["trabajador_nombre"] = self._get_trab_name(tid_int) if tid_int is not None else ""

        editing_set = self._editing_rows.get(dia_iso, set())
        if editing_set:
            for r in rows:
                rid = r.get(E_AGENDA.ID.value)
                if rid is None:
                    continue
                try:
                    rid_val = int(rid)
                except Exception:
                    rid_val = rid
                if rid_val in editing_set:
                    r["_editing"] = True
        tb.set_rows(rows)
        self._safe_update()

    # ---------------------------------------------------------------
    # Theme/Layout/Update
    # ---------------------------------------------------------------
    def did_mount(self):
        self._mounted = True
        self.page = self.app_state.get_page()
        # ✅ colores del área agenda
        self.colors = self.app_state.get_colors("agenda")
        self._recolor_ui()
        self._safe_update()

    def will_unmount(self):
        self._mounted = False
        if self._theme_listener:
            try:
                self.app_state.off_theme_change(self._theme_listener)
            except Exception:
                pass
            self._theme_listener = None
        if self._layout_listener:
            try:
                self.layout_ctrl.remove_listener(self._layout_listener)
            except Exception:
                pass
            self._layout_listener = None

    def _on_theme_changed(self):
        # ✅ recolor con paleta 'agenda'
        self.colors = self.app_state.get_colors("agenda")
        self._recolor_ui()
        self._refrescar_dataset()

    def _on_layout_changed(self, expanded: bool):
        self._safe_update()

    def _apply_textfield_palette(self, tf: ft.TextField):
        tf.bgcolor = self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
        tf.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.label_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf.hint_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=11)
        tf.cursor_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.border_color = self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)
        tf.focused_border_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _recolor_ui(self):
        if isinstance(self.content, ft.Container):
            self.content.bgcolor = self.colors.get("BG_COLOR")
        self.table_container.bgcolor = self.colors.get("BG_COLOR")
        self.estado_dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=12)
        self._safe_update()

    def _safe_update(self):
        p = getattr(self, "page", None)
        if p:
            try:
                p.update()
            except AssertionError:
                pass

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
