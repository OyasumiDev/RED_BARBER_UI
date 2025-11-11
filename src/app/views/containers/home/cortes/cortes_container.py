# app/views/containers/home/cortes/cortes_container.py
from __future__ import annotations
import flet as ft
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Core / Layout / Estado
from app.config.application.app_state import AppState
from app.views.containers.nvar.layout_controller import LayoutController

# Builders
from app.ui.builders.table_builder_expansive import TableBuilderExpansive
from app.ui.builders.table_builder import TableBuilder
from app.ui.sorting.sort_manager import SortManager

# Modal de fecha/hora (para el "+" por día)
from app.views.modals.modal_datetime_picker import DateTimeModalPicker

# Modelos
from app.models.servicios_model import ServiciosModel
from app.models.trabajadores_model import TrabajadoresModel
from app.models.agenda_model import AgendaModel
from app.models.promos_model import PromosModel
from app.models.cortes_model import CortesModel  # crear_corte, eliminar_corte, listar_por_dia(d:date), listar_por_rango(inicio, fin)

# Enums
from app.core.enums.e_usuarios import E_USU_ROL
from app.core.enums.e_agenda import E_AGENDA, E_AGENDA_ESTADO
from app.core.enums.e_cortes import E_CORTE

# Enum de trabajadores (si no existe, fallback seguro)
try:
    from app.core.enums.e_trabajadores import E_TRAB_ESTADO  # .ACTIVO.value
except Exception:
    class _E_TRAB_ESTADO:
        class _V:
            def __init__(self, v): self.value = v
        ACTIVO = _V("activo")
    E_TRAB_ESTADO = _E_TRAB_ESTADO  # type: ignore

# Modal de promociones (si existe)
try:
    from app.views.modals.modal_promos_manager import PromosManagerDialog
except Exception:
    PromosManagerDialog = None  # type: ignore

# -------------------------- Helpers --------------------------
LIBRE_KEY = "__LIBRE__"

def _txt(v: Any) -> str:
    return "" if v is None else str(v)

def _hhmm(v: Any) -> str:
    try:
        if isinstance(v, str): return v
        if isinstance(v, time): return v.strftime("%H:%M")
        if isinstance(v, datetime): return v.strftime("%H:%M")
        return str(v)
    except Exception:
        return ""

def _valid_hhmm(hhmm: str) -> bool:
    try:
        hh, mm = [int(x) for x in (hhmm or "").strip().split(":")]
        return 0 <= hh < 24 and 0 <= mm < 60
    except Exception:
        return False

def _parse_hhmm(hhmm: str) -> time:
    hh, mm = [int(x) for x in (hhmm or "").strip().split(":")]
    return time(hour=hh, minute=mm)

def _dec(v: Any, fallback: str = "0.00") -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(fallback)

# ============================================================================

class CortesContainer(ft.Container):
    """
    Módulo de Cortes — versión robusta:
    - Trabajador: lista SOLO activos (con fallback si el enum no existe) y permite seleccionar.
    - Cita#: muestra PROGRAMADAS + COMPLETADAS; al elegir, autocompleta cliente/trab/servicio/base.
    - Promo/Total: recálculo en tiempo real ante cambios (sin columnas de ganancia).
    - Hora: no editable; al guardar usa datetime.now() como hora real del corte.
    - Listado: llamadas a modelos con firmas correctas y filtros locales seguros.
    - Toolbar: botón “Promos” compacto para caber al extremo derecho.
    """

    # keys hijas
    HORA = "hora"
    CLIENTE = "cliente"
    SERV_ID = "servicio_id"
    SERV_TX = "servicio_txt"
    BASE = "monto_base"
    IS_LIBRE = "is_libre"
    PROMO_APLICAR = "promo_aplicar"
    DESCUENTO = "descuento"
    TOTAL = "total"
    TRAB_ID = "trabajador_id"
    CITA_ID = "cita_id"

    # keys grupo
    GDIA = "dia"
    GCNT = "cortes"

    def __init__(self):
        super().__init__(expand=True)

        # Core
        self.app_state = AppState()
        self.page = self.app_state.page
        self.colors = self.app_state.get_colors("servicios")
        self.layout_ctrl = LayoutController()

        # Permisos
        self.is_root = False
        self._sync_permissions()

        # Modelos
        self.serv_model = ServiciosModel()
        self.trab_model = TrabajadoresModel()
        self.agenda_model = AgendaModel()
        self.promos_model = PromosModel()
        self.cortes_model = CortesModel()

        # Estado general
        self._mounted = False
        self._theme_listener = None
        self._layout_listener = None

        # Rango visible (semana actual)
        self.base_day: date = date.today()
        self.days_span: int = 7

        # Filtros
        self.filter_trab: Optional[int] = None
        self.filter_serv: Optional[int] = None
        self.filter_cliente: str = ""

        # Refs UI
        self._day_tables: Dict[str, TableBuilder] = {}
        self._editing_rows: Dict[str, set[Any]] = {}
        self._edit_controls: Dict[str, Dict[str, ft.Control]] = {}
        self._trab_cache: Dict[str, str] = {}

        # Día abierto (para “Nuevo corte”)
        self._opened_day_iso: Optional[str] = None

        # Build
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

    # ----------------------------- permisos / sesión
    def _sync_permissions(self):
        try:
            sess = self.page.client_storage.get("app.user") if self.page else None
        except Exception:
            sess = None
        rol = (sess.get("rol") or "").strip().lower() if isinstance(sess, dict) else ""
        username = (sess.get("username") or "").strip().lower() if isinstance(sess, dict) else ""
        self.is_root = (rol == E_USU_ROL.ROOT.value) or (username == "root")

    # ------------------------------------------------------------------ Toolbar
    def _build_toolbar(self):
        # 👉 Nuevo corte
        self.btn_nuevo = ft.FilledButton(
            "Nuevo corte",
            icon=ft.icons.ADD,
            on_click=lambda e: self._quick_new_for_today_or_opened_day(),
            style=ft.ButtonStyle(padding=ft.padding.symmetric(6, 6)),
        )

        # Filtros
        self.dd_trab = ft.Dropdown(
            label="Trabajador", width=156, dense=True,
            options=[ft.dropdown.Option("", "Todos")],
            on_change=lambda e: self._apply_filters(),
        )
        self.dd_trab.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)
        try:
            for t in self._listar_trabajadores_activos():
                tid = self._extract_trab_id(t)
                nom = t.get("nombre") or t.get("NOMBRE") or t.get("name") or f"Trabajador {tid}"
                if tid:
                    self.dd_trab.options.append(ft.dropdown.Option(tid, nom))
        except Exception:
            pass

        self.dd_serv = ft.Dropdown(
            label="Servicio", width=156, dense=True,
            options=[ft.dropdown.Option("", "Todos")],
            on_change=lambda e: self._apply_filters(),
        )
        self.dd_serv.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)
        try:
            for s in self.serv_model.listar(activo=True) or []:
                sid = s.get("id") or s.get("id_servicio") or s.get("ID")
                nom = s.get("nombre") or s.get("NOMBRE") or ""
                if sid and nom:
                    self.dd_serv.options.append(ft.dropdown.Option(str(sid), nom))
        except Exception:
            pass

        self.tf_cliente = ft.TextField(
            label="Buscar cliente", hint_text="Nombre…", width=220, height=36, text_size=12,
            on_change=lambda e: self._apply_filters(),
        )
        self._apply_textfield_palette(self.tf_cliente)

        self.btn_clear = ft.IconButton(
            icon=ft.icons.CLEAR_ALL, tooltip="Limpiar filtros",
            on_click=lambda e: self._clear_filters(), icon_size=16, style=ft.ButtonStyle(padding=0),
        )

        # Manejar promociones (compacto)
        self.btn_promos = ft.FilledTonalButton(
            "Promos",
            icon=ft.icons.LOCAL_OFFER,
            on_click=lambda e: self._open_promos_modal(),
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(4, 4),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            visible=self.is_root,
        )

        # Toolbar
        self.toolbar = ft.ResponsiveRow(
            controls=[
                ft.Container(content=self.btn_nuevo, alignment=ft.alignment.center_left, col={"xs": 12, "md": 2, "lg": 2}),
                ft.Container(content=self.dd_trab, col={"xs": 6, "md": 2, "lg": 2}),
                ft.Container(content=self.dd_serv, col={"xs": 6, "md": 2, "lg": 2}),
                ft.Container(content=self.tf_cliente, col={"xs": 8, "md": 3, "lg": 3}),
                ft.Container(content=self.btn_clear, alignment=ft.alignment.center_left, col={"xs": 4, "md": 1, "lg": 1}),
                ft.Container(content=self.btn_promos, alignment=ft.alignment.center_right, col={"xs": 12, "md": 2, "lg": 2}),
            ],
            columns=12, spacing=8, run_spacing=8,
        )

    def _apply_filters(self):
        v_trab = (self.dd_trab.value or "").strip()
        v_serv = (self.dd_serv.value or "").strip()
        self.filter_trab = int(v_trab) if v_trab.isdigit() else None
        self.filter_serv = int(v_serv) if v_serv.isdigit() else None
        self.filter_cliente = (self.tf_cliente.value or "").strip()
        self._refrescar_dataset()

    def _clear_filters(self):
        self.dd_trab.value = ""
        self.dd_serv.value = ""
        self.tf_cliente.value = ""
        self.filter_trab = None
        self.filter_serv = None
        self.filter_cliente = ""
        self._refrescar_dataset()

    # -------------------------------------------------------------------- Body
    def _build_body(self):
        self.table_container = ft.Container(
            expand=True,
            alignment=ft.alignment.top_center,
            bgcolor=self.colors.get("BG_COLOR"),
            content=ft.Column(
                controls=[], alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True, scroll=ft.ScrollMode.AUTO,
            ),
        )

        columns = [
            {"key": self.GDIA, "title": "Día", "width": 132, "align": "start", "formatter": self._fmt_day_title},
            {"key": self.GCNT, "title": "N°", "width": 32, "align": "center",
             "formatter": lambda v, r: ft.Text(str(v or 0), size=11)},
        ]
        self.expansive = TableBuilderExpansive(
            group="cortes_dias", columns=columns, row_id_key=self.GDIA,
            detail_builder=self._detail_builder_for_day,
        )

        col = self.table_container.content
        col.controls.clear()
        col.controls.append(self.toolbar)
        col.controls.append(ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)))
        col.controls.append(self.expansive.build())

        self.content = ft.Container(expand=True, bgcolor=self.colors.get("BG_COLOR"), padding=6, content=self.table_container)
        self._refrescar_dataset()

    # ----------------------------------------------------------- Dataset/grupo
    def _range_bounds(self) -> Tuple[datetime, datetime]:
        base = self.base_day
        monday = base - timedelta(days=(base.weekday() % 7))
        ds = [monday + timedelta(days=i) for i in range(self.days_span)]
        return datetime.combine(ds[0], time.min), datetime.combine(ds[-1], time.max)

    def _fetch_group_rows(self) -> List[Dict[str, Any]]:
        start_dt, end_dt = self._range_bounds()

        # Firma real del modelo: solo (inicio, fin); filtramos luego en memoria
        try:
            rows = self.cortes_model.listar_por_rango(start_dt, end_dt) or []
        except Exception:
            rows = []

        # Filtrado local (trabajador/servicio/cliente)
        if self.filter_trab:
            rows = [r for r in rows if str(r.get("trabajador_id") or "") == str(self.filter_trab)]
        if self.filter_serv:
            rows = [r for r in rows if str(r.get("servicio_id") or "") == str(self.filter_serv)]
        if self.filter_cliente:
            q = self.filter_cliente.lower()
            rows = [r for r in rows if q in (str(r.get("cliente") or r.get("descripcion") or "").lower())]

        by_day: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            fh = r.get("fecha_hora") or r.get("fecha") or r.get("created_at")
            if isinstance(fh, str):
                try:
                    try: dt = datetime.fromisoformat(fh)
                    except ValueError: dt = datetime.strptime(fh, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
            elif isinstance(fh, datetime):
                dt = fh
            else:
                continue
            key = dt.date().isoformat()
            by_day.setdefault(key, []).append(r)

        groups: List[Dict[str, Any]] = []
        for key, items in sorted(by_day.items()):
            d = date.fromisoformat(key)
            groups.append({self.GDIA: key, self.GCNT: len(items), "_date_obj": d})
        return groups

    def _refrescar_dataset(self):
        data = self._fetch_group_rows()
        self.expansive.set_rows(data)
        self._safe_update()

    # ----------------------------------------------------------- Formatters
    def _fmt_day_title(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        try:
            d = row.get("_date_obj") or date.fromisoformat(value)
        except Exception:
            d = self.base_day
        row_controls = [
            ft.Text(d.strftime("%a %d/%m/%Y"), size=12, weight="bold", color=self.colors.get("FG_COLOR")),
            ft.Container(expand=True),
            ft.IconButton(
                ft.icons.ADD, tooltip="Nuevo corte en este día",
                on_click=lambda e, d=d: self._insert_new_for_day(d),
                icon_size=16, style=ft.ButtonStyle(padding=0)),
        ]
        return ft.Row(row_controls, alignment=ft.MainAxisAlignment.START)

    # ----------------------------------------------------------- Detalle por día
    def _detail_builder_for_day(self, group_row: Dict[str, Any]) -> ft.Control:
        DIA = group_row[self.GDIA]
        self._day_tables.pop(DIA, None)
        self._opened_day_iso = DIA

        ID = "id"
        columns = [
            {"key": self.HORA, "title": "Hora", "width": 52, "align": "center",
             "formatter": lambda v, r, dia=DIA: self._fmt_hora_cell(v, r, dia)},
            {"key": self.CLIENTE, "title": "Cliente", "width": 120, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_text_cell(v, r, dia, key=self.CLIENTE, hint="Nombre")},
            {"key": self.SERV_ID, "title": "Servicio", "width": 120, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_servicio_cell(r.get(self.SERV_ID), r, dia)},
            {"key": self.BASE, "title": "Base $", "width": 64, "align": "end",
             "formatter": lambda v, r, dia=DIA: self._fmt_base_cell(v, r, dia)},
            {"key": self.PROMO_APLICAR, "title": "Promo", "width": 132, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_promo_cell(v, r, dia)},
            {"key": self.TOTAL, "title": "Total $", "width": 66, "align": "end",
             "formatter": lambda v, r, dia=DIA: self._fmt_total_cell(v, r, dia)},
            {"key": self.TRAB_ID, "title": "Trab.", "width": 116, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_trab_cell(v, r, dia)},
            {"key": self.CITA_ID, "title": "Cita#", "width": 110, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_cita_cell(v, r, dia)},
        ]

        tb = TableBuilder(
            group=f"cortes_{DIA}",
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

        # Cargar filas del día y normalizar (firma SIN kwargs)
        d_obj = group_row.get("_date_obj") or date.fromisoformat(DIA)
        try:
            rows = self.cortes_model.listar_por_dia(d_obj) or []
        except Exception:
            rows = []
        rows = self._normalize_rows_for_ui(DIA, rows)

        # Mantener edición activa
        editing_set = self._editing_rows.get(DIA, set())
        if editing_set:
            for r in rows:
                rid = r.get("id")
                if rid is None: continue
                try: rid_val = int(rid)
                except Exception: rid_val = rid
                if rid_val in editing_set:
                    r["_editing"] = True

        self._day_tables[DIA] = tb
        wrapper = ft.Container(padding=4, content=tb.build())
        tb.set_rows(rows)
        return wrapper

    # ------------------------ Normalización
    def _normalize_rows_for_ui(self, dia_iso: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for r in rows or []:
            fh = r.get("fecha_hora")
            if isinstance(fh, str):
                try:
                    try: dt = datetime.fromisoformat(fh)
                    except ValueError: dt = datetime.strptime(fh, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    dt = None
            elif isinstance(fh, datetime):
                dt = fh
            else:
                dt = None

            r[self.HORA] = _hhmm(dt or r.get(self.HORA))
            r[self.CLIENTE] = r.get("cliente") or r.get("descripcion")
            r[self.SERV_ID] = r.get("servicio_id")
            r[self.SERV_TX] = r.get("servicio_txt")
            r[self.IS_LIBRE] = 1 if (r.get("is_libre") or r.get(self.SERV_ID) in (None, "", 0)) else 0
            r[self.BASE] = r.get("monto_base") or r.get("precio_base") or r.get(E_CORTE.PRECIO_BASE.value) or 0
            r[self.PROMO_APLICAR] = 1 if r.get("promo_aplicar", 1) else 0
            desc_val = r.get("descuento") or r.get(E_CORTE.DESCUENTO.value) or 0
            total_val = r.get("total") or r.get(E_CORTE.TOTAL.value) or 0
            r[self.DESCUENTO] = _dec(desc_val)
            r[self.TOTAL] = _dec(total_val)
            r[self.TRAB_ID] = r.get("trabajador_id")
            r[self.CITA_ID] = r.get("cita_id") or r.get("agenda_id")
            out.append(r)
        return out

    # ----------------------------------------------------------- Crear nuevas filas
    def _quick_new_for_today_or_opened_day(self):
        d = date.fromisoformat(self._opened_day_iso) if self._opened_day_iso else date.today()
        now = datetime.now().replace(second=0, microsecond=0)
        dt = datetime.combine(d, now.time()) if d != now.date() else now
        self._create_prefilled_row(dt)

    def _insert_new_for_day(self, d: date):
        def on_selected(values: Sequence[datetime] | Sequence[str], _d=d):
            for dt in self._coerce_dt_list(values):
                if dt.date() == _d:
                    self._create_prefilled_row(dt)
                    break

        picker = DateTimeModalPicker(
            on_confirm=on_selected, auto_range=False, require_time=True,
            use_24h=False, return_format="datetime",
            width=320, cell_size=22,
            title=f"Nuevo corte ({d.strftime('%d/%m/%Y')})", subtitle="Selecciona la hora (informativa).",
        )
        picker.open(self.page)
        picker.set_enabled_dates([d.isoformat()])

    def _coerce_dt_list(self, values: Sequence[datetime] | Sequence[str]) -> List[datetime]:
        out: List[datetime] = []
        for v in values:
            if isinstance(v, datetime):
                out.append(v)
            elif isinstance(v, str) and v.strip():
                try:
                    out.append(datetime.fromisoformat(v))
                except Exception:
                    try:
                        out.append(datetime.strptime(v, "%Y-%m-%d %H:%M"))
                    except Exception:
                        pass
        return out

    def _ensure_group_exists_and_expand(self, d: date):
        dia_iso = d.isoformat()
        if self.expansive.find_row(dia_iso) is not None:
            self.expansive.expand_row(dia_iso); self._opened_day_iso = dia_iso; return
        new_group = {self.GDIA: dia_iso, self.GCNT: 0, "_date_obj": d}
        self.expansive.insert_row(new_group, position="end")
        self.expansive.expand_row(dia_iso)
        self._opened_day_iso = dia_iso
        self._safe_update()

    def _get_or_build_day_table(self, dia_iso: str) -> Optional[TableBuilder]:
        tb = self._day_tables.get(dia_iso)
        if tb: return tb
        self.expansive.expand_row(dia_iso)
        tb = self._day_tables.get(dia_iso)
        if tb: return tb
        group_row = self.expansive.find_row(dia_iso)
        if group_row:
            self._detail_builder_for_day(group_row)
            tb = self._day_tables.get(dia_iso)
        return tb

    def _create_prefilled_row(self, dt: datetime):
        d = dt.date()
        self._ensure_group_exists_and_expand(d)
        dia_iso = d.isoformat()

        tb = self._get_or_build_day_table(dia_iso)
        if not tb: return

        row = {
            "id": None,
            self.HORA: dt.strftime("%H:%M"),  # visible, no editable
            self.CLIENTE: "",
            self.SERV_ID: LIBRE_KEY,
            self.SERV_TX: "",
            self.IS_LIBRE: 1,
            self.BASE: "0.00",
            self.PROMO_APLICAR: 1,
            self.DESCUENTO: "0.00",
            self.TOTAL: "0.00",
            self.TRAB_ID: None,
            self.CITA_ID: None,
            "_is_new": True,
            "_editing": True,
        }
        tb.add_row(row, auto_scroll=True)
        self._safe_update()

    # ----------------------------------------------------------- Helpers edición y datos
    def _ensure_edit_map(self, dia_iso: str, row_id: Any):
        key = f"{dia_iso}:{row_id if row_id is not None else -1}"
        if key not in self._edit_controls:
            self._edit_controls[key] = {}
        return key

    def _is_row_editing(self, row: Dict[str, Any]) -> bool:
        return bool(row.get("_is_new")) or bool(row.get("_editing"))

    def _resolve_row_datetime(self, dia_iso: str, row: Dict[str, Any]) -> datetime:
        try:
            d = date.fromisoformat(dia_iso)
        except Exception:
            d = date.today()
        hhmm = str(row.get(self.HORA) or "").strip()
        if not _valid_hhmm(hhmm):
            hhmm = datetime.now().strftime("%H:%M")
        try:
            t = _parse_hhmm(hhmm)
        except Exception:
            t = datetime.now().time().replace(second=0, microsecond=0)
        return datetime.combine(d, t)

    def _mark_row_editing(self, dia_iso: str, row: Dict[str, Any]):
        row["_editing"] = True
        rid = row.get("id")
        if rid is not None:
            try: rid_int = int(rid)
            except Exception: rid_int = rid
            self._editing_rows.setdefault(dia_iso, set()).add(rid_int)

    def _extract_trab_id(self, data: Dict[str, Any]) -> Optional[str]:
        for key in ("id", "ID", "trabajador_id", "id_trabajador", "ID_TRABAJADOR"):
            val = data.get(key)
            if val not in (None, "", 0):
                return str(val)
        return None

    def _resolve_trab_name(self, trabajador_id: Any) -> str:
        if trabajador_id in (None, "", 0):
            return ""
        key = str(trabajador_id)
        if key in self._trab_cache:
            return self._trab_cache[key]
        try:
            for t in self._listar_trabajadores_activos():
                tid = self._extract_trab_id(t)
                if not tid:
                    continue
                nom = t.get("nombre") or t.get("NOMBRE") or t.get("name") or f"Trabajador {tid}"
                self._trab_cache[tid] = nom
        except Exception:
            pass
        return self._trab_cache.get(key, f"ID {key}")

    def _resolve_promo_row(self, dia_iso: str, row: Dict[str, Any], servicio_id: Optional[Any]) -> Optional[Dict[str, Any]]:
        if servicio_id in (None, "", LIBRE_KEY, 0):
            return None
        dt = self._resolve_row_datetime(dia_iso, row)
        try:
            return self.promos_model.find_applicable(servicio_id=int(servicio_id), dt=dt) or None
        except Exception:
            return None

    def _set_display_label(self, dia_iso: str, row: Dict[str, Any], key: str, text: str):
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        ctrl = self._edit_controls.get(k, {}).get(key)
        if isinstance(ctrl, ft.Text):
            ctrl.value = text
        elif isinstance(ctrl, ft.TextField):
            ctrl.value = text

    def _update_total_display(self, dia_iso: str, row: Dict[str, Any], total: Decimal):
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        for key in (f"{self.TOTAL}__lbl", self.TOTAL):
            ctrl = self._edit_controls.get(k, {}).get(key)
            if isinstance(ctrl, ft.Text):
                ctrl.value = f"{total:.2f}"
            elif isinstance(ctrl, ft.TextField):
                ctrl.value = f"{total:.2f}"

    def _format_promo_info_text(self, has_promo: bool, applied: bool) -> str:
        if applied and has_promo:
            return "Promoción aplicada"
        return "Sin promoción"

    # ---- Listar trabajadores ACTVOS robusto a distintos esquemas
    def _listar_trabajadores_activos(self) -> List[Dict[str, Any]]:
        try:
            res = self.trab_model.listar(estado=E_TRAB_ESTADO.ACTIVO.value) or []
            if res: return res
        except Exception:
            pass
        try:
            res = self.trab_model.listar(activo=True) or []
            if res: return res
        except Exception:
            pass
        try:
            data = self.trab_model.listar(estado=None) or []
            out = []
            for t in data:
                est = str(t.get("estado", "")).strip().lower()
                act = t.get("activo", None)
                if est in ("activo", "act", "1", "true", "t", "sí", "si") or act in (True, 1, "1"):
                    out.append(t)
            return out or data
        except Exception:
            return []

    def _get_servicio_by_id(self, sid: int) -> Optional[Dict[str, Any]]:
        try:
            if hasattr(self.serv_model, "get_by_id"):
                r = self.serv_model.get_by_id(int(sid))
                if r: return r
        except Exception:
            pass
        try:
            for s in self.serv_model.listar(activo=True) or []:
                sid0 = s.get("id") or s.get("ID") or s.get("id_servicio")
                if sid0 is not None and int(sid0) == int(sid):
                    return s
        except Exception:
            pass
        return None

    def _agenda_get_by_id(self, cita_id: int, d: Optional[date]) -> Dict[str, Any]:
        try:
            if hasattr(self.agenda_model, "get_by_id"):
                r = self.agenda_model.get_by_id(int(cita_id)) or {}
                if r: return r
        except Exception:
            pass
        if d:
            try:
                for st in (E_AGENDA_ESTADO.PROGRAMADA.value, E_AGENDA_ESTADO.COMPLETADA.value):
                    for c in self.agenda_model.listar_por_dia(dia=d, estado=st) or []:
                        cid = c.get(E_AGENDA.ID.value) or c.get("id")
                        if cid is not None and int(cid) == int(cita_id):
                            return c
            except Exception:
                pass
        return {}

    def _format_cita_label(self, dia_iso: str, cita_value: Any) -> str:
        val = str(cita_value or "").strip()
        if not val:
            return "-"
        try:
            d = date.fromisoformat(dia_iso)
        except Exception:
            d = None
        cita = self._agenda_get_by_id(int(val), d) if val.isdigit() else {}
        if not cita:
            return val
        ini = cita.get(E_AGENDA.INICIO.value) or cita.get("inicio")
        if isinstance(ini, str):
            try:
                ini = datetime.fromisoformat(ini)
            except Exception:
                ini = None
        hh = ini.strftime("%H:%M") if isinstance(ini, datetime) else ""
        cliente = cita.get(E_AGENDA.CLIENTE_NOM.value) or cita.get("cliente") or ""
        estado = (cita.get(E_AGENDA.ESTADO.value) or "").strip().title()
        parts = [p for p in [hh, cliente, estado] if p]
        return " ".join(parts) if parts else val

    def _get_assigned_citas(self, dia_iso: str, current_value: str) -> set[str]:
        assigned: set[str] = set()
        tb = self._day_tables.get(dia_iso)
        if tb:
            try:
                for r in tb.get_rows():
                    cid = str(r.get(self.CITA_ID) or "").strip()
                    if cid:
                        assigned.add(cid)
            except Exception:
                pass
        if current_value:
            assigned.discard(current_value)
        return assigned

    # ---- Al seleccionar una cita, autocompletar y recalcular
    def _on_select_cita(self, dia_iso: str, row: Dict[str, Any], cita_value: Any):
        val = str(cita_value or "").strip()
        row[self.CITA_ID] = val
        if not val.isdigit():
            self._safe_update(); return

        d = date.fromisoformat(dia_iso)
        cita = self._agenda_get_by_id(int(val), d)

        k = self._ensure_edit_map(dia_iso, row.get("id"))
        # Cliente
        tf_cli: ft.TextField = self._edit_controls[k].get(self.CLIENTE)  # type: ignore
        if tf_cli:
            tf_cli.value = cita.get("cliente_nombre") or cita.get("cliente") or tf_cli.value

        # Trabajador
        dd_trab: ft.Dropdown = self._edit_controls[k].get(self.TRAB_ID)  # type: ignore
        if dd_trab and cita.get("trabajador_id"):
            dd_trab.value = str(cita["trabajador_id"])
            row[self.TRAB_ID] = cita["trabajador_id"]

        # Servicio + base
        dd_serv: ft.Dropdown = self._edit_controls[k].get(self.SERV_ID)  # type: ignore
        base_tf: ft.TextField = self._edit_controls[k].get(self.BASE)    # type: ignore
        if dd_serv and cita.get("servicio_id"):
            sid = int(cita["servicio_id"])
            dd_serv.value = str(sid)
            srow = self._get_servicio_by_id(sid)
            if srow and base_tf:
                pv = srow.get("precio_base") or srow.get("precio") or 0
                base_tf.value = f"{_dec(pv):.2f}"

        self._recalc_row(dia_iso, row)
        self._safe_update()

    # ----------------------------------------------------------- Celdas (hora no editable)
    def _fmt_hora_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        label = _hhmm(value) or _hhmm(datetime.now())
        return ft.Text(label, size=11, color=self.colors.get("FG_COLOR"))

    def _fmt_text_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str, hint: str) -> ft.Control:
        en_edicion = self._is_row_editing(row)
        if not en_edicion:
            return ft.Text(_txt(value), size=11, color=self.colors.get("FG_COLOR"))
        tf = ft.TextField(value=_txt(value), hint_text=hint, width=120 if key == self.CLIENTE else 100,
                          text_size=11, content_padding=ft.padding.symmetric(6, 4))
        self._apply_textfield_palette(tf)
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][key] = tf
        return tf

    def _fmt_trab_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        if not self._is_row_editing(row):
            label = self._resolve_trab_name(value) or "-"
            return ft.Text(label, size=11, color=self.colors.get("FG_COLOR"))

        opts = []
        try:
            trs = self._listar_trabajadores_activos()
        except Exception:
            trs = []
        for r in trs:
            tid = self._extract_trab_id(r)
            nom = r.get("nombre") or r.get("NOMBRE") or r.get("name") or f"Trabajador {tid}"
            if tid:
                opts.append(ft.dropdown.Option(tid, nom))

        dd = ft.Dropdown(value=str(value) if value is not None else None, options=opts, width=116, dense=True)
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=11)

        def _on_change(_):
            k = self._ensure_edit_map(dia_iso, row.get("id"))
            self._edit_controls[k][self.TRAB_ID] = dd
            self._mark_row_editing(dia_iso, row)
            self._recalc_row(dia_iso, row)

        dd.on_change = _on_change
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][self.TRAB_ID] = dd
        return dd

    def _fmt_servicio_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        if not self._is_row_editing(row):
            label = row.get(self.SERV_TX)
            if not label:
                if (row.get(self.IS_LIBRE) or value == LIBRE_KEY or value in (None, "", 0)):
                    label = "Libre (monto)"
                elif value:
                    srv = None
                    try:
                        srv = self._get_servicio_by_id(int(value))
                    except Exception:
                        srv = None
                    label = srv.get("nombre") if srv else f"Servicio #{value}"
            return ft.Text(_txt(label), size=11, color=self.colors.get("FG_COLOR"))

        opciones: List[ft.dropdown.Option] = [ft.dropdown.Option(LIBRE_KEY, "Libre (monto)")]
        servicios = []
        try:
            servicios = self.serv_model.listar(activo=True) or []
        except Exception:
            pass
        for s in servicios:
            sid = s.get("id") or s.get("ID") or s.get("id_servicio")
            nom = s.get("nombre") or s.get("NOMBRE")
            if sid is not None and nom:
                opciones.append(ft.dropdown.Option(str(sid), nom))

        initial = LIBRE_KEY if (row.get(self.IS_LIBRE) or value in (None, "", 0)) else (str(value))
        dd = ft.Dropdown(value=initial, options=opciones, width=120, dense=True)
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=11)

        def _on_change(_):
            is_libre = (dd.value == LIBRE_KEY)
            row[self.IS_LIBRE] = 1 if is_libre else 0
            if is_libre:
                row[self.SERV_ID] = None
            else:
                try:
                    row[self.SERV_ID] = int(dd.value)
                except Exception:
                    row[self.SERV_ID] = dd.value
            if not is_libre:
                try:
                    sid = int(dd.value)
                except Exception:
                    sid = None
                base = Decimal("0.00")
                if sid is not None:
                    srow = self._get_servicio_by_id(sid)
                    if srow:
                        pv = srow.get("precio_base") or srow.get("precio") or 0
                        base = _dec(pv)
                key = self._ensure_edit_map(dia_iso, row.get("id"))
                base_tf: ft.TextField = self._edit_controls[key].get(self.BASE)  # type: ignore
                if base_tf:
                    base_tf.value = f"{base:.2f}"
            k = self._ensure_edit_map(dia_iso, row.get("id"))
            self._edit_controls[k][self.SERV_ID] = dd
            self._mark_row_editing(dia_iso, row)
            self._recalc_row(dia_iso, row)

        dd.on_change = _on_change
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][self.SERV_ID] = dd
        return dd

    def _fmt_base_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        if not self._is_row_editing(row):
            return ft.Text(f"{_dec(value):.2f}", size=11, color=self.colors.get("FG_COLOR"), text_align=ft.TextAlign.RIGHT)
        base_val = _txt(value) or "0.00"
        tf = ft.TextField(value=base_val, width=64, text_size=11, keyboard_type=ft.KeyboardType.NUMBER,
                          content_padding=ft.padding.symmetric(6, 4), text_align=ft.TextAlign.RIGHT)
        self._apply_textfield_palette(tf)
        def _on_change(_):
            self._mark_row_editing(dia_iso, row)
            self._recalc_row(dia_iso, row)
        tf.on_change = _on_change
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][self.BASE] = tf
        return tf

    def _fmt_promo_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        servicio_id = row.get(self.SERV_ID)
        promo_row = self._resolve_promo_row(dia_iso, row, servicio_id)
        if not self._is_row_editing(row):
            applied = bool(row.get(self.PROMO_APLICAR) and promo_row)
            label = "Promoción aplicada" if applied else "Sin promoción"
            color = ft.colors.GREEN_400 if applied else self.colors.get("FG_COLOR")
            return ft.Text(label, size=11, color=color)

        sw = ft.Switch(value=bool(value) and bool(promo_row), scale=0.9, disabled=not promo_row)

        def _on_change(_):
            row[self.PROMO_APLICAR] = 1 if (sw.value and not sw.disabled) else 0
            k = self._ensure_edit_map(dia_iso, row.get("id"))
            self._edit_controls[k][self.PROMO_APLICAR] = sw
            self._mark_row_editing(dia_iso, row)
            self._recalc_row(dia_iso, row)

        sw.on_change = _on_change
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][self.PROMO_APLICAR] = sw
        info_text = self._format_promo_info_text(bool(promo_row), sw.value and not sw.disabled)
        info_lbl = ft.Text(info_text, size=10, color=self.colors.get("FG_COLOR"))
        self._edit_controls[k][f"{self.DESCUENTO}__lbl"] = info_lbl
        return ft.Column([sw, info_lbl], spacing=2, tight=True)

    def _fmt_total_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        val_txt = f"{_dec(value):.2f}"
        if not self._is_row_editing(row):
            txt = ft.Text(val_txt, size=11, color=self.colors.get("FG_COLOR"), text_align=ft.TextAlign.RIGHT)
            self._edit_controls[k][f"{self.TOTAL}__lbl"] = txt
            return txt

        tf = ft.TextField(value=val_txt, width=75, text_size=11, text_align=ft.TextAlign.RIGHT,
                          keyboard_type=ft.KeyboardType.NUMBER, content_padding=ft.padding.symmetric(6, 4))
        self._apply_textfield_palette(tf)

        def _on_change(_):
            try:
                row[self.TOTAL] = f"{_dec(tf.value or 0):.2f}"
            except Exception:
                row[self.TOTAL] = tf.value or "0.00"
            self._edit_controls[k][self.TOTAL] = tf
            self._mark_row_editing(dia_iso, row)

        tf.on_change = _on_change
        self._edit_controls[k][self.TOTAL] = tf
        self._edit_controls[k][f"{self.TOTAL}__lbl"] = tf
        return tf

    def _fmt_cita_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        """Dropdown con citas PROGRAMADAS y COMPLETADAS del día."""
        current_val = str(value or "")
        if not self._is_row_editing(row):
            label = self._format_cita_label(dia_iso, value)
            return ft.Text(label, size=11, color=self.colors.get("FG_COLOR"))

        d = date.fromisoformat(dia_iso)
        assigned = self._get_assigned_citas(dia_iso, current_val.strip())

        opciones = [ft.dropdown.Option("", "—")]
        try:
            citas_prog = self.agenda_model.listar_por_dia(dia=d, estado=E_AGENDA_ESTADO.PROGRAMADA.value) or []
        except Exception:
            citas_prog = []
        try:
            citas_done = self.agenda_model.listar_por_dia(dia=d, estado=E_AGENDA_ESTADO.COMPLETADA.value) or []
        except Exception:
            citas_done = []

        def _add_opts(citas, pref):
            for c in citas:
                cid = c.get(E_AGENDA.ID.value) or c.get("id")
                cid_str = str(cid) if cid is not None else ""
                if cid_str and cid_str in assigned:
                    continue
                ini = c.get(E_AGENDA.INICIO.value) or c.get("inicio")
                nom = c.get(E_AGENDA.CLIENTE_NOM.value) or c.get("cliente") or ""
                if isinstance(ini, str):
                    try: ini = datetime.fromisoformat(ini)
                    except Exception: ini = None
                hh = ini.strftime("%H:%M") if isinstance(ini, datetime) else ""
                opciones.append(ft.dropdown.Option(str(cid), f"{pref} {hh} {nom}".strip()))

        _add_opts(citas_prog, "🟡")
        _add_opts(citas_done, "🟢")

        dd = ft.Dropdown(value=current_val, options=opciones, width=110, dense=True)
        dd.on_change = lambda e: self._on_select_cita(dia_iso, row, dd.value)
        return dd

    # ----------------------------------------------------------- Actions / CRUD
    def _actions_builder(self, dia_iso: str, row: Dict[str, Any], is_new: bool) -> ft.Control:
        def _ico(icon, tip, on_click):
            return ft.IconButton(icon=icon, tooltip=tip, on_click=on_click, icon_size=14, style=ft.ButtonStyle(padding=0))

        rid = row.get("id")
        if is_new or bool(row.get("_is_new")) or (rid in (None, "", 0)):
            return ft.Row(
                [_ico(ft.icons.CHECK, "Aceptar", lambda e, r=row: self._on_accept_row(dia_iso, r)),
                 _ico(ft.icons.CLOSE, "Cancelar", lambda e, r=row: self._on_cancel_row(dia_iso, r))],
                spacing=4, alignment=ft.MainAxisAlignment.START
            )
        if row.get("_editing", False):
            return ft.Row(
                [_ico(ft.icons.CHECK, "Guardar", lambda e, r=row: self._on_accept_row(dia_iso, r)),
                 _ico(ft.icons.CLOSE, "Cancelar", lambda e, r=row: self._on_cancel_row(dia_iso, r))],
                spacing=4, alignment=ft.MainAxisAlignment.START
            )
        acciones = [
            _ico(ft.icons.EDIT, "Editar", lambda e, r=row: self._on_edit_row(dia_iso, r)),
        ]
        if self.is_root:
            acciones.append(_ico(ft.icons.DELETE, "Borrar", lambda e, r=row: self._on_delete_row(dia_iso, r)))
        return ft.Row(acciones, spacing=4, alignment=ft.MainAxisAlignment.START)

    def _on_edit_row(self, dia_iso: str, row: Dict[str, Any]):
        self._mark_row_editing(dia_iso, row)
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
        rid = row.get("id")
        if rid is not None:
            try: rid_int = int(rid)
            except Exception: rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
        self._refresh_day_table(dia_iso)

    def _on_delete_row(self, dia_iso: str, row: Dict[str, Any]):
        if not self.is_root:
            self._snack_error("❌ Solo ROOT puede borrar."); return
        rid = row.get("id")
        if not rid: return
        res = self.cortes_model.eliminar_corte(int(rid))
        if res.get("status") == "success":
            self._snack_ok("🗑️ Corte eliminado.")
            try: rid_int = int(rid)
            except Exception: rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
            self._refresh_day_table(dia_iso)
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ {res.get('message', 'No se pudo eliminar')}")

    def _on_accept_row(self, dia_iso: str, row: Dict[str, Any]):
        key = f"{dia_iso}:{row.get('id') if row.get('id') is not None else -1}"
        ctrls = self._edit_controls.get(key, {})

        def _val(tf: Optional[ft.TextField]) -> str:
            return (tf.value or "").strip() if tf else ""

        cliente = _val(ctrls.get(self.CLIENTE))
        trab_dd: ft.Dropdown = ctrls.get(self.TRAB_ID)  # type: ignore
        serv_dd: ft.Dropdown = ctrls.get(self.SERV_ID)  # type: ignore
        base_tf: ft.TextField = ctrls.get(self.BASE)    # type: ignore
        sw_aplicar: ft.Switch = ctrls.get(self.PROMO_APLICAR)  # type: ignore
        cita_val = row.get(self.CITA_ID)

        if not cliente or len(cliente) < 2:
            self._snack_error("❌ Cliente inválido."); return

        trabajador_id = int(trab_dd.value) if trab_dd and (trab_dd.value or "").isdigit() else None
        if trabajador_id is None:
            self._snack_error("❌ Selecciona un trabajador."); return

        is_libre = (serv_dd.value == LIBRE_KEY) if serv_dd else bool(row.get(self.IS_LIBRE))
        servicio_id = None if is_libre else (int(serv_dd.value) if serv_dd and (serv_dd.value or "").isdigit() else None)
        if not is_libre and not servicio_id:
            self._snack_error("❌ Selecciona un servicio o usa 'Libre (monto)'."); return

        base = _dec(base_tf.value if base_tf else row.get(self.BASE) or 0)
        if base <= 0:
            self._snack_error("❌ Monto base debe ser > 0."); return

        aplicar_promo = bool(sw_aplicar.value) if isinstance(sw_aplicar, ft.Switch) else bool(row.get(self.PROMO_APLICAR, 1))

        # Hora real del corte (según el grupo/columna)
        fh = self._resolve_row_datetime(dia_iso, row)

        # Promo con la hora real
        promo_row = self._resolve_promo_row(dia_iso, row, servicio_id)

        descuento = Decimal("0.00")
        total = base
        if promo_row and aplicar_promo:
            promo_total, promo_desc = self.promos_model.aplicar_descuento(precio_base=base, promo_row=promo_row)
            total = _dec(promo_total)
            descuento = _dec(promo_desc)
        else:
            total = _dec(total)

        # persistir
        uid = None
        try:
            sess = self.page.client_storage.get("app.user")
            uid = (sess or {}).get("id_usuario")
        except Exception:
            uid = None

        cita_str = str(cita_val or "").strip()

        payload = dict(
            fecha_hora=fh,
            tipo="AGENDADO" if cita_str else "LIBRE",
            trabajador_id=trabajador_id,
            servicio_id=servicio_id,
            agenda_id=int(cita_str) if cita_str.isdigit() else None,
            aplicar_promo=1 if aplicar_promo else 0,
            precio_base_manual=float(base),
            descripcion=cliente,
            created_by=uid,
        )

        try:
            if row.get("id"):
                self.cortes_model.eliminar_corte(int(row["id"]))
            res = self.cortes_model.crear_corte(**payload)
        except Exception as ex:
            self._snack_error(f"❌ Error guardando: {ex}"); return

        if res.get("status") == "success":
            # Por si el modelo no lo hace internamente
            if payload.get("agenda_id"):
                try:
                    self.agenda_model.actualizar_cita(
                        cita_id=payload["agenda_id"],
                        estado=E_AGENDA_ESTADO.COMPLETADA.value,
                        fin=fh,
                        updated_by=uid
                    )
                except Exception:
                    pass
            self._snack_ok("✅ Corte guardado.")
        else:
            self._snack_error(f"❌ {res.get('message', 'No se pudo guardar')}"); return

        # limpiar estado edición y refrescar
        self._edit_controls.pop(key, None)
        rid = row.get("id")
        if rid is not None:
            try: rid_int = int(rid)
            except Exception: rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
        self._refresh_day_table(dia_iso)
        self._refrescar_dataset()

    # ----------------------------------------------------------- Recalculo / promo
    def _recalc_row(self, dia_iso: str, row: Dict[str, Any]):
        key = f"{dia_iso}:{row.get('id') if row.get('id') is not None else -1}"
        ctrls = self._edit_controls.get(key, {})
        base_tf: ft.TextField = ctrls.get(self.BASE)  # type: ignore
        serv_dd: ft.Dropdown = ctrls.get(self.SERV_ID)  # type: ignore
        sw_aplicar: ft.Switch = ctrls.get(self.PROMO_APLICAR)  # type: ignore
        base = _dec(base_tf.value if base_tf else row.get(self.BASE) or 0)
        servicio_id = None if (serv_dd and serv_dd.value == LIBRE_KEY) else (int(serv_dd.value) if serv_dd and (serv_dd.value or "").isdigit() else None)
        aplicar = bool(sw_aplicar.value) if isinstance(sw_aplicar, ft.Switch) else bool(row.get(self.PROMO_APLICAR, 1))

        dt = self._resolve_row_datetime(dia_iso, row)
        total = base
        descuento = Decimal("0.00")
        promo = None
        if servicio_id:
            promo = self._resolve_promo_row(dia_iso, row, servicio_id)
            if promo and aplicar:
                promo_total, promo_desc = self.promos_model.aplicar_descuento(precio_base=base, promo_row=promo)
                total = _dec(promo_total)
                descuento = _dec(promo_desc)
                total = _dec(total)
            else:
                total = _dec(total)
        else:
            total = _dec(total)

        row[self.DESCUENTO] = f"{descuento:.2f}"
        row[self.TOTAL] = f"{total:.2f}"
        self._update_total_display(dia_iso, row, total)

        aplicado_flag = aplicar and bool(promo)
        if isinstance(sw_aplicar, ft.Switch):
            has_promo = promo is not None
            sw_aplicar.disabled = not has_promo
            if not has_promo and sw_aplicar.value:
                sw_aplicar.value = False
                row[self.PROMO_APLICAR] = 0
            aplicado_flag = bool(promo) and bool(sw_aplicar.value and not sw_aplicar.disabled)
        self._set_display_label(
            dia_iso, row, f"{self.DESCUENTO}__lbl",
            self._format_promo_info_text(promo is not None, aplicado_flag)
        )
        self._update_total_display(dia_iso, row, total)
        self._safe_update()

    # ----------------------------------------------------------- Refresh hijos
    def _refresh_day_table(self, dia_iso: str):
        tb = self._day_tables.get(dia_iso)
        if not tb: return
        d = date.fromisoformat(dia_iso)
        try:
            rows = self.cortes_model.listar_por_dia(d) or []
        except Exception:
            rows = []
        rows = self._normalize_rows_for_ui(dia_iso, rows)

        editing_set = self._editing_rows.get(dia_iso, set())
        if editing_set:
            for r in rows:
                rid = r.get("id")
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

    # ----------------------------------------------------------- Tema / Layout
    def did_mount(self):
        self._mounted = True
        self._sync_permissions()
        self.btn_promos.visible = self.is_root
        self.colors = self.app_state.get_colors("servicios")
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
        self.colors = self.app_state.get_colors("servicios")
        self._recolor_ui()
        self._refrescar_dataset()

    def _on_layout_changed(self, expanded: bool):
        self._safe_update()

    def _apply_textfield_palette(self, tf: ft.TextField):
        tf.bgcolor = self.colors.get("FIELD_BG", self.colors.get("CARD_BG", ft.colors.SURFACE_VARIANT))
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
        self.dd_trab.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)
        self.dd_serv.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR"), size=12)
        self._safe_update()

    def _safe_update(self):
        p = getattr(self, "page", None)
        if p:
            try: p.update()
            except AssertionError: pass

    # ----------------------------------------------------------- Promos modal
    def _open_promos_modal(self):
        self._sync_permissions()
        if not self.is_root:
            self._snack_error("❌ Solo ROOT puede manejar promociones."); return
        if PromosManagerDialog:
            try:
                dialog = PromosManagerDialog(on_after_close=lambda: self._refrescar_dataset())
                dialog.open(self.page)
            except Exception:
                self._snack_error("⚠️ No se pudo abrir el modal de promociones.")
        else:
            self._snack_error("⚠️ Modal de promociones no disponible.")

    # ----------------------------------------------------------- Notificaciones
    def _snack_ok(self, msg: str):
        if not self.page: return
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            bgcolor=self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)),
        )
        self.page.snack_bar.open = True
        self._safe_update()

    def _snack_error(self, msg: str):
        if not self.page: return
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=ft.colors.WHITE),
            bgcolor=ft.colors.RED_600,
        )
        self.page.snack_bar.open = True
        self._safe_update()
