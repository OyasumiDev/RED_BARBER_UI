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

# Modal de fecha/hora (lo conservamos para el "+" por día)
from app.views.modals.modal_datetime_picker import DateTimeModalPicker

# Modelos
from app.models.servicios_model import ServiciosModel
from app.models.trabajadores_model import TrabajadoresModel
from app.models.agenda_model import AgendaModel
from app.models.promos_model import PromosModel

try:
    from app.models.cortes_model import CortesModel
except Exception:
    CortesModel = None  # type: ignore

# Enums
from app.core.enums.e_usuarios import E_USU_ROL
from app.core.enums.e_agenda import E_AGENDA_ESTADO

# Modal de promociones (si existe)
try:
    from app.views.modals.promos_modal import PromosModal
except Exception:
    PromosModal = None  # type: ignore


# -------------------------- Helpers --------------------------
DEFAULT_DURATION_MIN = 60
LIBRE_KEY = "__LIBRE__"


def _txt(v: Any) -> str:
    return "" if v is None else str(v)


def _hhmm(v: Any) -> str:
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


def _valid_hhmm(hhmm: str) -> bool:
    try:
        hh, mm = [int(x) for x in (hhmm or "").strip().split(":")]
        return 0 <= hh < 24 and 0 <= mm < 60
    except Exception:
        return False


def _parse_hhmm(hhmm: str) -> time:
    hh, mm = [int(x) for x in (hhmm or "").strip().split(":")]
    return time(hour=hh, minute=mm)


def _only_digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _dec(v: Any, fallback: str = "0.00") -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(fallback)


# ============================================================================
#  Cortes (pagos) – contenedor expansible por día
# ============================================================================
class CortesContainer(ft.Container):
    """
    - Toolbar: filtros + [Nuevo corte]*principal + [Manejar promociones]*solo ROOT (visible solo root)
    - Tabla por días (expansible), resumen de cada día y totales.
    - Filas hijas editables inline con cálculo de promos y comisión del trabajador.
    - Si se indica una “Cita#”, al guardar marca esa cita como COMPLETADA.
    """

    # keys hijas
    HORA = "hora"
    CLIENTE = "cliente"
    TEL = "tel"
    SERV_ID = "servicio_id"
    SERV_TX = "servicio_txt"
    BASE = "monto_base"
    IS_LIBRE = "is_libre"
    LIBRE_MONTO = "monto_libre"
    PROMO_ID = "promo_id"
    PROMO_TX = "promo_txt"
    PROMO_APLICAR = "promo_aplicar"
    DESCUENTO = "descuento"
    TOTAL = "total"
    TRAB_ID = "trabajador_id"
    COM_PCT = "comision_pct"
    GAN_TRAB = "gan_trab"
    NEGOCIO = "negocio"
    CITA_ID = "cita_id"

    # keys grupo
    GDIA = "dia"       # date ISO
    GRES = "resumen"
    GCNT = "cortes"

    def __init__(self):
        super().__init__(expand=True)

        # Core
        self.app_state = AppState()
        self.page = self.app_state.page
        self.colors = self.app_state.get_colors()
        self.layout_ctrl = LayoutController()

        # Permisos (se sincronizan de nuevo en did_mount)
        self.is_root = False
        self._sync_permissions()

        # Modelos
        self.serv_model = ServiciosModel()
        self.trab_model = TrabajadoresModel()
        self.agenda_model = AgendaModel()
        self.promos_model = PromosModel()
        self.cortes_model = CortesModel() if CortesModel else None

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
        # Trabajadores (filtro)
        self.dd_trab = ft.Dropdown(
            label="Trabajador",
            width=180,
            dense=True,
            options=[ft.dropdown.Option("", "Todos")],
            on_change=lambda e: self._apply_filters(),
        )
        self.dd_trab.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=12)

        try:
            trs = self.trab_model.listar(estado=None) or []
        except Exception:
            trs = []
        for t in trs:
            tid = t.get("id") or t.get("trabajador_id") or t.get("ID")
            nom = t.get("nombre") or t.get("NOMBRE") or t.get("name") or f"Trabajador {tid}"
            if tid is not None:
                self.dd_trab.options.append(ft.dropdown.Option(str(tid), nom))

        # Servicios (filtro)
        self.dd_serv = ft.Dropdown(
            label="Servicio",
            width=180,
            dense=True,
            options=[ft.dropdown.Option("", "Todos")],
            on_change=lambda e: self._apply_filters(),
        )
        self.dd_serv.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=12)

        try:
            servicios = self.serv_model.listar(activo=True) or []
        except Exception:
            servicios = []
        for s in servicios:
            sid = s.get("id") or s.get("id_servicio") or s.get("ID")
            nom = s.get("nombre") or s.get("NOMBRE") or ""
            if sid and nom:
                self.dd_serv.options.append(ft.dropdown.Option(str(sid), nom))

        # Cliente (filtro texto)
        self.tf_cliente = ft.TextField(
            label="Buscar cliente",
            hint_text="Nombre cliente…",
            width=220,
            height=36,
            text_size=12,
            on_change=lambda e: self._apply_filters(),
        )
        self._apply_textfield_palette(self.tf_cliente)

        # Botón limpiar
        self.btn_clear = ft.IconButton(
            icon=ft.icons.CLEAR_ALL,
            tooltip="Limpiar filtros",
            on_click=lambda e: self._clear_filters(),
            icon_size=16,
            style=ft.ButtonStyle(padding=0),
        )

        # 👉 Nuevo corte (principal): crea para HOY o para el día expandido, sin modal de fecha
        self.btn_nuevo = ft.FilledButton(
            "Nuevo corte",
            icon=ft.icons.ADD,
            on_click=lambda e: self._quick_new_for_today_or_opened_day(),
            style=ft.ButtonStyle(padding=ft.padding.symmetric(6, 6)),
        )

        # Manejar promociones (solo visible para ROOT)
        self.btn_promos = ft.FilledTonalButton(
            "Manejar promociones",
            icon=ft.icons.LOCAL_OFFER,
            on_click=lambda e: self._open_promos_modal(),
            style=ft.ButtonStyle(padding=ft.padding.symmetric(6, 6)),
            visible=self.is_root,
        )

        # Toolbar responsive
        self.toolbar = ft.ResponsiveRow(
            controls=[
                ft.Container(content=self.dd_trab, col={"xs": 6, "md": 3, "lg": 2}),
                ft.Container(content=self.dd_serv, col={"xs": 6, "md": 3, "lg": 2}),
                ft.Container(content=self.tf_cliente, col={"xs": 12, "md": 4, "lg": 3}),
                ft.Container(content=self.btn_clear, alignment=ft.alignment.center_left, col={"xs": 2, "md": 1, "lg": 1}),
                ft.Container(expand=True, col={"xs": 0, "md": 1, "lg": 2}),  # spacer
                ft.Container(content=self.btn_nuevo, alignment=ft.alignment.center_right, col={"xs": 5, "md": 2, "lg": 2}),
                ft.Container(content=self.btn_promos, alignment=ft.alignment.center_right, col={"xs": 7, "md": 3, "lg": 2}),
            ],
            columns=12,
            spacing=8,
            run_spacing=8,
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
                controls=[],
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

        columns = [
            {"key": self.GDIA, "title": "Día", "width": 180, "align": "start", "formatter": self._fmt_day_title},
            {"key": self.GRES, "title": "Resumen", "width": 360, "align": "start", "formatter": self._fmt_day_resumen},
            {"key": self.GCNT, "title": "N°", "width": 42, "align": "center",
             "formatter": lambda v, r: ft.Text(str(v or 0), size=11)},
        ]
        self.expansive = TableBuilderExpansive(
            group="cortes_dias",
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
            padding=6,
            content=self.table_container,
        )

        self._refrescar_dataset()

    # ----------------------------------------------------------- Dataset/grupo
    def _range_bounds(self) -> Tuple[datetime, datetime]:
        base = self.base_day
        monday = base - timedelta(days=(base.weekday() % 7))
        ds = [monday + timedelta(days=i) for i in range(self.days_span)]
        return datetime.combine(ds[0], time.min), datetime.combine(ds[-1], time.max)

    def _fetch_group_rows(self) -> List[Dict[str, Any]]:
        start_dt, end_dt = self._range_bounds()

        rows: List[Dict[str, Any]] = []
        if self.cortes_model:
            try:
                rows = self.cortes_model.listar_por_rango(
                    inicio=start_dt,
                    fin=end_dt,
                    trabajador_id=self.filter_trab,
                    servicio_id=self.filter_serv,
                    search=self.filter_cliente or None,
                ) or []
            except Exception:
                rows = []

        by_day: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            fh = r.get("fecha_hora") or r.get("fecha") or r.get("created_at")
            if isinstance(fh, str):
                try:
                    try:
                        dt = datetime.fromisoformat(fh)
                    except ValueError:
                        dt = datetime.strptime(fh, "%Y-%m-%d %H:%M:%S")
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
            pills = []
            for ev in sorted(items, key=lambda x: str(x.get("fecha_hora") or ""))[:3]:
                h = _hhmm(ev.get("fecha_hora"))
                cli = ev.get("cliente") or ""
                total = _dec(ev.get("total"))
                pills.append(f"{h} {cli} (${total})".strip())
            groups.append({
                self.GDIA: key,
                self.GRES: " · ".join(pills) if pills else "—",
                self.GCNT: len(items),
                "_date_obj": d,
            })
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
            ft.Text(d.strftime("%a %d/%m/%Y"), size=12, weight="bold", color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            ft.Container(expand=True),
            ft.IconButton(
                ft.icons.ADD,
                tooltip="Nuevo corte en este día",
                on_click=lambda e, d=d: self._insert_new_for_day(d),
                icon_size=16,
                style=ft.ButtonStyle(padding=0),
            ),
        ]
        return ft.Row(row_controls, alignment=ft.MainAxisAlignment.START)

    def _fmt_day_resumen(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        return ft.Text(_txt(value), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

    # ----------------------------------------------------------- Detalle por día
    def _detail_builder_for_day(self, group_row: Dict[str, Any]) -> ft.Control:
        DIA = group_row[self.GDIA]
        self._day_tables.pop(DIA, None)
        self._opened_day_iso = DIA

        ID = "id"
        columns = [
            {"key": self.HORA, "title": "Hora", "width": 58, "align": "center",
             "formatter": lambda v, r, dia=DIA: self._fmt_hora_cell(v, r, dia)},
            {"key": self.CLIENTE, "title": "Cliente", "width": 150, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_text_cell(v, r, dia, key=self.CLIENTE, hint="Nombre cliente")},
            {"key": self.TEL, "title": "Tel.", "width": 108, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_tel_cell(v, r, dia)},
            {"key": self.SERV_ID, "title": "Servicio", "width": 170, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_servicio_cell(r.get(self.SERV_ID), r, dia)},
            {"key": self.BASE, "title": "Base $", "width": 86, "align": "end",
             "formatter": lambda v, r, dia=DIA: self._fmt_base_cell(v, r, dia)},
            {"key": self.PROMO_ID, "title": "Promo", "width": 140, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_promo_cell(v, r, dia)},
            {"key": self.TOTAL, "title": "Total $", "width": 90, "align": "end",
             "formatter": lambda v, r, dia=DIA: self._fmt_total_cell(v, r, dia)},
            {"key": self.TRAB_ID, "title": "Trab.", "width": 140, "align": "start",
             "formatter": lambda v, r, dia=DIA: self._fmt_trab_cell(v, r, dia)},
            {"key": self.GAN_TRAB, "title": "Gan. Trab.", "width": 92, "align": "end",
             "formatter": lambda v, r, dia=DIA: self._fmt_gan_trab_cell(v, r, dia)},
            {"key": self.NEGOCIO, "title": "Negocio", "width": 92, "align": "end",
             "formatter": lambda v, r, dia=DIA: self._fmt_negocio_cell(v, r, dia)},
            {"key": self.CITA_ID, "title": "Cita#", "width": 68, "align": "center",
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

        # Cargar filas del día y normalizar
        d_obj = group_row.get("_date_obj") or date.fromisoformat(DIA)
        rows: List[Dict[str, Any]] = []
        if self.cortes_model:
            try:
                rows = self.cortes_model.listar_por_dia(dia=d_obj) or []
            except Exception:
                rows = []
        rows = self._normalize_rows_for_ui(DIA, rows)

        # mantener edición activa
        editing_set = self._editing_rows.get(DIA, set())
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

        self._day_tables[DIA] = tb
        wrapper = ft.Container(padding=4, content=tb.build())
        tb.set_rows(rows)
        return wrapper

    # ------------------------ Normalización común (builder/refresh)
    def _normalize_rows_for_ui(self, dia_iso: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for r in rows or []:
            # fecha/hora
            fh = r.get("fecha_hora")
            if isinstance(fh, str):
                try:
                    try:
                        dt = datetime.fromisoformat(fh)
                    except ValueError:
                        dt = datetime.strptime(fh, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    dt = None
            elif isinstance(fh, datetime):
                dt = fh
            else:
                dt = None

            r[self.HORA] = _hhmm(dt or r.get(self.HORA))
            r[self.CLIENTE] = r.get("cliente")
            r[self.TEL] = r.get("tel")
            r[self.SERV_ID] = r.get("servicio_id")
            r[self.SERV_TX] = r.get("servicio_txt")
            r[self.IS_LIBRE] = 1 if (r.get("is_libre") or r.get(self.SERV_ID) in (None, "", 0)) else 0
            r[self.BASE] = r.get("monto_base") or r.get("precio_base") or r.get(self.LIBRE_MONTO) or 0
            r[self.LIBRE_MONTO] = r.get("monto_libre") or (r[self.BASE] if r[self.IS_LIBRE] else None)
            r[self.PROMO_ID] = r.get("promo_id")
            r[self.PROMO_TX] = r.get("promo_txt") or ("—" if not r.get("promo_id") else r.get("promo_txt"))
            r[self.PROMO_APLICAR] = 1 if r.get("promo_aplicar", 1) else 0
            r[self.DESCUENTO] = r.get("descuento") or 0
            r[self.TOTAL] = r.get("total") or Decimal("0.00")
            r[self.TRAB_ID] = r.get("trabajador_id")
            r[self.COM_PCT] = r.get("comision_pct") or None

            base = _dec(r[self.BASE])
            total = _dec(r[self.TOTAL])
            pct = self._resolve_trab_comision_pct(r[self.TRAB_ID], r[self.COM_PCT])
            r[self.GAN_TRAB] = (total * Decimal(pct) / Decimal("100")).quantize(Decimal("0.01"))
            r[self.NEGOCIO] = (total - _dec(r[self.GAN_TRAB])).quantize(Decimal("0.01"))
            r[self.CITA_ID] = r.get("cita_id")
            out.append(r)
        return out

    # ----------------------------------------------------------- Crear nuevas filas
    def _quick_new_for_today_or_opened_day(self):
        """Nuevo corte: crea una fila para HOY o para el día actualmente expandido (sin datepicker)."""
        # determina día destino
        if self._opened_day_iso:
            try:
                d = date.fromisoformat(self._opened_day_iso)
            except Exception:
                d = date.today()
        else:
            d = date.today()

        now = datetime.now().replace(second=0, microsecond=0)
        dt = datetime.combine(d, now.time()) if d != now.date() else now
        self._create_prefilled_row(dt)

    def _insert_new_for_day(self, d: date):
        """Botón '+' en la fila del día (usa un selector de hora para ese día)."""
        def on_selected(values: Sequence[datetime] | Sequence[str], _d=d):
            for dt in self._coerce_dt_list(values):
                if dt.date() == _d:
                    self._create_prefilled_row(dt)
                    break

        picker = DateTimeModalPicker(
            on_confirm=on_selected,
            auto_range=False,
            require_time=True,
            use_24h=False,
            return_format="datetime",
            width=320,
            cell_size=22,
            title=f"Nuevo corte ({d.strftime('%d/%m/%Y')})",
            subtitle="Selecciona la hora.",
        )
        picker.open(self.page)
        picker.set_enabled_dates([d.isoformat()])

    def _coerce_dt_list(self, values: Sequence[datetime] | Sequence[str]) -> List[datetime]:
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
        new_group = {self.GDIA: dia_iso, self.GRES: "—", self.GCNT: 0, "_date_obj": d}
        self.expansive.insert_row(new_group, position="end")
        self.expansive.expand_row(dia_iso)
        self._opened_day_iso = dia_iso
        self._safe_update()

    def _create_prefilled_row(self, dt: datetime):
        d = dt.date()
        self._ensure_group_exists_and_expand(d)
        dia_iso = d.isoformat()
        tb = self._day_tables.get(dia_iso)
        if not tb:
            self.expansive.expand_row(dia_iso)
            tb = self._day_tables.get(dia_iso)
            if not tb:
                return

        row = {
            "id": None,
            self.HORA: dt.strftime("%H:%M"),
            self.CLIENTE: "",
            self.TEL: "",
            self.SERV_ID: None,
            self.SERV_TX: "",
            self.IS_LIBRE: 0,
            self.LIBRE_MONTO: None,
            self.BASE: "0.00",
            self.PROMO_ID: None,
            self.PROMO_TX: "",
            self.PROMO_APLICAR: 1,
            self.DESCUENTO: "0.00",
            self.TOTAL: "0.00",
            self.TRAB_ID: None,
            self.COM_PCT: None,
            self.GAN_TRAB: "0.00",
            self.NEGOCIO: "0.00",
            self.CITA_ID: None,
            "_is_new": True,
            "_editing": True,
        }
        tb.add_row(row, auto_scroll=True)
        self._safe_update()

    # ----------------------------------------------------------- Celdas edición
    def _ensure_edit_map(self, dia_iso: str, row_id: Any):
        key = f"{dia_iso}:{row_id if row_id is not None else -1}"
        if key not in self._edit_controls:
            self._edit_controls[key] = {}
        return key

    def _fmt_hora_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(_hhmm(value), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf = ft.TextField(value=_hhmm(value), hint_text="HH:MM", width=56, text_size=11,
                          keyboard_type=ft.KeyboardType.DATETIME, content_padding=ft.padding.symmetric(6, 4))
        self._apply_textfield_palette(tf)
        def validar(_):
            ok = _valid_hhmm(tf.value or "")
            tf.border_color = None if ok else ft.colors.RED
            self._safe_update()
        tf.on_change = validar
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][self.HORA] = tf
        return tf

    def _fmt_text_cell(self, value: Any, row: Dict[str, Any], dia_iso: str, *, key: str, hint: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            return ft.Text(_txt(value), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf = ft.TextField(value=_txt(value), hint_text=hint, width=150 if key == self.CLIENTE else 108,
                          text_size=11, content_padding=ft.padding.symmetric(6, 4))
        self._apply_textfield_palette(tf)
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][key] = tf
        return tf

    def _fmt_tel_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        return self._fmt_text_cell(value, row, dia_iso, key=self.TEL, hint="Teléfono")

    def _fmt_cita_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        if not en_edicion:
            return ft.Text(str(value or ""), size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf = ft.TextField(value=str(value or ""), hint_text="ID", width=68, text_size=11,
                          content_padding=ft.padding.symmetric(6, 4), keyboard_type=ft.KeyboardType.NUMBER)
        self._apply_textfield_palette(tf)
        self._edit_controls[k][self.CITA_ID] = tf
        return tf

    def _fmt_trab_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        if not en_edicion:
            label = row.get("trabajador_nombre") or str(value or "")
            return ft.Text(label, size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        # cargar trabajadores
        opts = []
        try:
            trs = self.trab_model.listar(estado=None) or []
        except Exception:
            trs = []
        for r in trs:
            tid = r.get("id") or r.get("trabajador_id") or r.get("ID")
            nom = r.get("nombre") or r.get("NOMBRE") or r.get("name") or f"Trabajador {tid}"
            if tid is not None:
                opts.append(ft.dropdown.Option(str(tid), nom))

        dd = ft.Dropdown(value=str(value) if value is not None else None, options=opts, width=140, dense=True)
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=11)

        def _on_change(_):
            pct = self._resolve_trab_comision_pct(int(dd.value) if (dd.value or "").isdigit() else None, None)
            k = self._ensure_edit_map(dia_iso, row.get("id"))
            self._edit_controls[k][self.COM_PCT] = pct  # guardo valor directo
            self._recalc_row(dia_iso, row)

        dd.on_change = _on_change
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][self.TRAB_ID] = dd
        return dd

    def _fmt_servicio_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        if not en_edicion:
            label = row.get(self.SERV_TX) or ("Libre" if row.get(self.IS_LIBRE) else "")
            return ft.Text(label, size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        opciones: List[ft.dropdown.Option] = [ft.dropdown.Option(LIBRE_KEY, "Libre (monto)")]
        try:
            servicios = self.serv_model.listar(activo=True) or []
        except Exception:
            servicios = []
        for s in servicios:
            sid = s.get("id") or s.get("ID") or s.get("id_servicio")
            nom = s.get("nombre") or s.get("NOMBRE")
            if sid is not None and nom:
                opciones.append(ft.dropdown.Option(str(sid), nom))

        initial = LIBRE_KEY if (row.get(self.IS_LIBRE) or value in (None, "", 0)) else (str(value))
        dd = ft.Dropdown(value=initial, options=opciones, width=170, dense=True)
        dd.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=11)

        def _on_change(_):
            is_libre = (dd.value == LIBRE_KEY)
            row[self.IS_LIBRE] = 1 if is_libre else 0
            if is_libre:
                pass
            else:
                try:
                    sid = int(dd.value)
                except Exception:
                    sid = None
                precio = Decimal("0.00")
                if sid is not None:
                    try:
                        srow = next((x for x in servicios if (x.get("id") or x.get("ID") or x.get("id_servicio")) == sid), None)
                        pv = srow.get("precio_base") if srow else None
                        precio = _dec(pv or 0)
                    except Exception:
                        pass

                base_tf: ft.TextField = self._edit_controls[k].get(self.BASE)  # type: ignore
                if base_tf:
                    base_tf.value = f"{precio:.2f}"

                dt = self._row_datetime(dia_iso, row)
                if dt and sid:
                    promo = self._find_promo(sid, dt)
                    self._set_promo_ui(dia_iso, row, promo_row=promo, aplicar=True)

            self._recalc_row(dia_iso, row)

        dd.on_change = _on_change
        self._edit_controls[k][self.SERV_ID] = dd
        return dd

    def _fmt_base_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        base_val = _txt(value)
        if not en_edicion:
            return ft.Text(f"{_dec(base_val):.2f}", size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), text_align=ft.TextAlign.RIGHT)
        tf = ft.TextField(value=base_val or "0.00", width=86, text_size=11, keyboard_type=ft.KeyboardType.NUMBER,
                          content_padding=ft.padding.symmetric(6, 4), text_align=ft.TextAlign.RIGHT)
        self._apply_textfield_palette(tf)
        def _on_change(_):
            self._recalc_row(dia_iso, row)
        tf.on_change = _on_change
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        self._edit_controls[k][self.BASE] = tf
        return tf

    def _fmt_promo_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        k = self._ensure_edit_map(dia_iso, row.get("id"))
        en_edicion = bool(row.get("_is_new")) or row.get("_editing", False)
        promo_txt = row.get(self.PROMO_TX) or "—"
        aplicar = bool(row.get(self.PROMO_APLICAR, 1))

        chip = ft.Container(
            bgcolor=self.colors.get("TYPE_TAG_BG", ft.colors.with_opacity(0.08, ft.colors.PRIMARY)),
            padding=ft.padding.symmetric(8, 4),
            border_radius=12,
            content=ft.Text(promo_txt, size=11, color=self.colors.get("FG_COLOR")),
        )
        if not en_edicion:
            return chip

        sw = ft.Switch(value=aplicar, scale=0.9)
        def _on_toggle(_):
            row[self.PROMO_APLICAR] = 1 if sw.value else 0
            self._recalc_row(dia_iso, row)
        sw.on_change = _on_toggle

        self._edit_controls[k][self.PROMO_APLICAR] = sw
        return ft.Row([chip, sw], spacing=6, alignment=ft.MainAxisAlignment.START)

    def _fmt_total_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        total = _dec(row.get(self.TOTAL))
        return ft.Text(f"{total:.2f}", size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), text_align=ft.TextAlign.RIGHT)

    def _fmt_gan_trab_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        return ft.Text(f"{_dec(row.get(self.GAN_TRAB)):.2f}", size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), text_align=ft.TextAlign.RIGHT)

    def _fmt_negocio_cell(self, value: Any, row: Dict[str, Any], dia_iso: str) -> ft.Control:
        return ft.Text(f"{_dec(row.get(self.NEGOCIO)):.2f}", size=11, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), text_align=ft.TextAlign.RIGHT)

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
        row["_editing"] = True
        rid = row.get("id")
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
        rid = row.get("id")
        if rid is not None:
            try:
                rid_int = int(rid)
            except Exception:
                rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
        self._refresh_day_table(dia_iso)

    def _on_delete_row(self, dia_iso: str, row: Dict[str, Any]):
        if not self.is_root:
            self._snack_error("❌ Solo ROOT puede borrar.")
            return
        if not self.cortes_model:
            self._snack_error("❌ Modelo de cortes no disponible.")
            return
        rid = row.get("id")
        if not rid:
            return
        res = self.cortes_model.eliminar_corte(int(rid))
        if res.get("status") == "success":
            self._snack_ok("🗑️ Corte eliminado.")
            try:
                rid_int = int(rid)
            except Exception:
                rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
            self._refresh_day_table(dia_iso)
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ {res.get('message', 'No se pudo eliminar')}")

    def _on_accept_row(self, dia_iso: str, row: Dict[str, Any]):
        if not self.cortes_model:
            self._snack_error("❌ Modelo de cortes no disponible.")
            return

        key = f"{dia_iso}:{row.get('id') if row.get('id') is not None else -1}"
        ctrls = self._edit_controls.get(key, {})

        def _val(tf: Optional[ft.TextField]) -> str:
            return (tf.value or "").strip() if tf else ""

        hora_txt = _val(ctrls.get(self.HORA))
        cliente = _val(ctrls.get(self.CLIENTE))
        tel = _val(ctrls.get(self.TEL))
        cita_id_txt = _val(ctrls.get(self.CITA_ID))
        trab_dd: ft.Dropdown = ctrls.get(self.TRAB_ID)  # type: ignore
        serv_dd: ft.Dropdown = ctrls.get(self.SERV_ID)  # type: ignore
        base_tf: ft.TextField = ctrls.get(self.BASE)  # type: ignore
        sw_aplicar = ctrls.get(self.PROMO_APLICAR)

        if not _valid_hhmm(hora_txt):
            self._snack_error("❌ Hora inválida (HH:MM).")
            return
        if not cliente or len(cliente) < 2:
            self._snack_error("❌ Cliente inválido.")
            return

        trabajador_id = int(trab_dd.value) if trab_dd and (trab_dd.value or "").isdigit() else None
        if trabajador_id is None:
            self._snack_error("❌ Selecciona un trabajador.")
            return

        is_libre = (serv_dd.value == LIBRE_KEY) if serv_dd else bool(row.get(self.IS_LIBRE))
        servicio_id = None if is_libre else (int(serv_dd.value) if serv_dd and (serv_dd.value or "").isdigit() else None)
        if not is_libre and not servicio_id:
            self._snack_error("❌ Selecciona un servicio o usa 'Libre (monto)'.")
            return

        base = _dec(base_tf.value if base_tf else row.get(self.BASE) or 0)
        if base <= 0:
            self._snack_error("❌ Monto base debe ser > 0.")
            return

        aplicar_promo = bool(sw_aplicar.value) if isinstance(sw_aplicar, ft.Switch) else bool(row.get(self.PROMO_APLICAR, 1))

        d = date.fromisoformat(dia_iso)
        fh = datetime.combine(d, _parse_hhmm(hora_txt))

        # Promo
        promo_row = None
        if servicio_id:
            promo_row = self._find_promo(servicio_id, fh)

        descuento = Decimal("0.00")
        total = base
        promo_id = None
        promo_txt = None
        if promo_row and aplicar_promo:
            total, descuento = self.promos_model.aplicar_descuento(precio_base=base, promo_row=promo_row)
            promo_id = promo_row.get("id")
            promo_txt = promo_row.get("nombre")
        else:
            total = base
            descuento = Decimal("0.00")

        # comisión
        pct = self._resolve_trab_comision_pct(trabajador_id, self._edit_controls.get(key, {}).get(self.COM_PCT))
        gan_trab = (total * Decimal(pct) / Decimal("100")).quantize(Decimal("0.01"))
        negocio = (total - gan_trab).quantize(Decimal("0.01"))

        # sanitizar teléfono
        tel_digits = _only_digits(tel) or None

        # persistir
        uid = None
        try:
            sess = self.page.client_storage.get("app.user")
            uid = (sess or {}).get("id_usuario")
        except Exception:
            uid = None

        payload = {
            "fecha_hora": fh,
            "cliente": cliente,
            "tel": tel_digits,
            "trabajador_id": trabajador_id,
            "servicio_id": servicio_id,
            "servicio_txt": (None if servicio_id else "Libre"),
            "monto_base": float(base),
            "promo_id": promo_id,
            "promo_txt": promo_txt,
            "promo_aplicar": 1 if aplicar_promo else 0,
            "descuento": float(descuento),
            "total": float(total),
            "comision_pct": float(pct),
            "gan_trab": float(gan_trab),
            "negocio": float(negocio),
            "cita_id": int(cita_id_txt) if cita_id_txt.isdigit() else None,
            "created_by": uid,
        }

        if row.get("id") in (None, "", 0):
            res = self.cortes_model.crear_corte(**payload)  # type: ignore
        else:
            rid = int(row.get("id"))
            res = self.cortes_model.actualizar_corte(corte_id=rid, **payload)  # type: ignore

        if res.get("status") == "success":
            # si hay cita → completarla
            if payload.get("cita_id"):
                try:
                    self.agenda_model.actualizar_cita(
                        cita_id=payload["cita_id"],
                        estado=E_AGENDA_ESTADO.COMPLETADA.value,
                        fin=fh,
                        updated_by=uid
                    )
                except Exception:
                    pass
            self._snack_ok("✅ Corte guardado.")
        else:
            self._snack_error(f"❌ {res.get('message', 'No se pudo guardar')}")
            return

        # limpiar estado edición y refrescar
        self._edit_controls.pop(key, None)
        rid = row.get("id")
        if rid is not None:
            try:
                rid_int = int(rid)
            except Exception:
                rid_int = rid
            self._editing_rows.get(dia_iso, set()).discard(rid_int)
        self._refresh_day_table(dia_iso)
        self._refrescar_dataset()

    # ----------------------------------------------------------- Recalculo / promo / comisión
    def _row_datetime(self, dia_iso: str, row: Dict[str, Any]) -> Optional[datetime]:
        h = row.get(self.HORA) or "00:00"
        if not _valid_hhmm(h):
            return None
        d = date.fromisoformat(dia_iso)
        try:
            return datetime.combine(d, _parse_hhmm(h))
        except Exception:
            return None

    def _find_promo(self, servicio_id: int, dt: datetime) -> Optional[Dict[str, Any]]:
        try:
            return self.promos_model.find_applicable(servicio_id=servicio_id, dt=dt) or None
        except Exception:
            return None

    def _set_promo_ui(self, dia_iso: str, row: Dict[str, Any], *, promo_row: Optional[Dict[str, Any]], aplicar: bool):
        row[self.PROMO_ID] = promo_row.get("id") if promo_row else None
        row[self.PROMO_TX] = promo_row.get("nombre") if promo_row else "—"
        row[self.PROMO_APLICAR] = 1 if aplicar else 0

    def _resolve_trab_comision_pct(self, trabajador_id: Optional[int], pct_in_row: Any) -> float:
        try:
            if isinstance(pct_in_row, (int, float)):
                return float(pct_in_row)
            if isinstance(pct_in_row, Decimal):
                return float(pct_in_row)
        except Exception:
            pass

        if not trabajador_id:
            return 50.0

        try:
            t = self.trab_model.get_by_id(int(trabajador_id)) or {}
        except Exception:
            t = {}

        candidates = [
            "comision_porcentaje", "comision_pct", "comision", "decomicion_porcentaje", "decomision_porcentaje"
        ]
        val = None
        for c in candidates:
            if c in t and t[c] is not None:
                try:
                    val = float(t[c])
                    break
                except Exception:
                    continue

        tipo = (t.get("tipo") or t.get("rol") or t.get("categoria") or "").strip().lower()
        if val is None:
            if "dueno" in tipo or "dueño" in tipo:
                val = 100.0
            elif "recepcion" in tipo or "recepcionista" in tipo:
                val = 50.0
            else:
                val = 50.0
        return float(val)

    def _recalc_row(self, dia_iso: str, row: Dict[str, Any]):
        key = f"{dia_iso}:{row.get('id') if row.get('id') is not None else -1}"
        ctrls = self._edit_controls.get(key, {})
        base_tf: ft.TextField = ctrls.get(self.BASE)  # type: ignore
        serv_dd: ft.Dropdown = ctrls.get(self.SERV_ID)  # type: ignore
        sw_aplicar: ft.Switch = ctrls.get(self.PROMO_APLICAR)  # type: ignore
        trab_dd: ft.Dropdown = ctrls.get(self.TRAB_ID)  # type: ignore

        base = _dec(base_tf.value if base_tf else row.get(self.BASE) or 0)
        servicio_id = None if (serv_dd and serv_dd.value == LIBRE_KEY) else (int(serv_dd.value) if serv_dd and (serv_dd.value or "").isdigit() else None)
        aplicar = bool(sw_aplicar.value) if isinstance(sw_aplicar, ft.Switch) else bool(row.get(self.PROMO_APLICAR, 1))

        dt = self._row_datetime(dia_iso, row)
        total = base
        descuento = Decimal("0.00")

        if servicio_id and dt:
            promo = self._find_promo(servicio_id, dt)
            if promo and aplicar:
                total, descuento = self.promos_model.aplicar_descuento(precio_base=base, promo_row=promo)

            row[self.PROMO_ID] = promo.get("id") if promo else None
            row[self.PROMO_TX] = promo.get("nombre") if promo else "—"

        row[self.DESCUENTO] = f"{descuento:.2f}"
        row[self.TOTAL] = f"{total:.2f}"

        trabajador_id = int(trab_dd.value) if trab_dd and (trab_dd.value or "").isdigit() else None
        pct = self._resolve_trab_comision_pct(trabajador_id, ctrls.get(self.COM_PCT))
        gan_trab = (total * Decimal(pct) / Decimal("100")).quantize(Decimal("0.01"))
        row[self.GAN_TRAB] = f"{gan_trab:.2f}"
        row[self.NEGOCIO] = f"{(total - gan_trab):.2f}"

        self._safe_update()

    # ----------------------------------------------------------- Refresh hijos
    def _refresh_day_table(self, dia_iso: str):
        tb = self._day_tables.get(dia_iso)
        if not tb:
            return
        d = date.fromisoformat(dia_iso)
        rows: List[Dict[str, Any]] = []
        if self.cortes_model:
            try:
                rows = self.cortes_model.listar_por_dia(dia=d) or []
            except Exception:
                rows = []
        rows = self._normalize_rows_for_ui(dia_iso, rows)
        tb.set_rows(rows)
        self._safe_update()

    # ----------------------------------------------------------- Tema / Layout
    def did_mount(self):
        self._mounted = True
        self.page = self.app_state.get_page()
        self._sync_permissions()               # ⬅️ revalidar root al montar
        self.btn_promos.visible = self.is_root # ⬅️ ajustar visibilidad
        self.colors = self.app_state.get_colors()
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
        self.colors = self.app_state.get_colors()
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
        self.dd_trab.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=12)
        self.dd_serv.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE), size=12)
        self._safe_update()

    def _safe_update(self):
        p = getattr(self, "page", None)
        if p:
            try:
                p.update()
            except AssertionError:
                pass

    # ----------------------------------------------------------- Promos modal
    def _open_promos_modal(self):
        # última verificación de permisos por si se cambió la sesión
        self._sync_permissions()
        if not self.is_root:
            self._snack_error("❌ Solo ROOT puede manejar promociones.")
            return
        if PromosModal:
            try:
                PromosModal(on_after_close=lambda: self._refrescar_dataset()).open(self.page)
            except Exception:
                self._snack_error("⚠️ No se pudo abrir el modal de promociones (revisa firma de open()).")
        else:
            self._snack_error("⚠️ Modal de promociones no disponible (import fallido).")

    # ----------------------------------------------------------- Notificaciones
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
