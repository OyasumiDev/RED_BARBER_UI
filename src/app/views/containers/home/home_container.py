from __future__ import annotations
import json
import asyncio
import logging
from datetime import datetime, timedelta, date as _date
from typing import Any, Optional
import flet as ft

from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController

# Modelos / Enums
from app.models.agenda_model import AgendaModel
from app.core.enums.e_agenda import E_AGENDA, E_AGENDA_ESTADO
from app.models.inventario_model import InventarioModel

DEFAULT_DURATION_MIN = 60

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# =============================================================================
# 🧩 BLOQUE ÚNICO DE TAMAÑOS / COMPORTAMIENTO
# =============================================================================
UI = {
    # Ancho máximo "legible" del contenido central
    "INNER_MAX_WIDTH": 1100,

    # Padding general del contenedor raíz (px)
    "ROOT_PADDING": 16,

    # Espaciados de secciones y grillas (px)
    "SECTION_SPACING": 14,
    "GRID_SPACING": 10,        # separación horizontal entre tarjetas
    "GRID_RUN_SPACING": 14,    # separación vertical entre filas (subí un poco para que respiren)

    "CARD_PADDING": 12,
    "CARD_RADIUS": 12,

    # Breakpoints base (para 1, 2, 3 o 4 columnas)
    "BREAKPOINTS": [700, 980, 1300],

    # Forzar tope de columnas por área (1 en pantallas chicas, máximo el valor indicado)
    "MAX_COLS": {
        "postits": 2,  # ← Cada 2 stickers por fila
        "stock":   2,  # ← Cada 2 stickers por fila
    },

    # Ocultar por completo el dashboard de prueba (stickers grises)
    "SHOW_DASHBOARD": False,

    # Tipografías
    "TITLE_SIZE": 22,
    "SECTION_TITLE_SIZE": 16,
    "POSTIT": {
        "HORA": 14,
        "TITULO": 13,
        "CLIENTE": 12,
        "NOTAS": 11,
        "BADGE": 11,
        "LINE_SPACING": 6,
    },
    "STOCK": {
        "NOMBRE": 13,
        "NUM": 12,
    },
}

# Helper: nº de columnas según ancho + breakpoints
_def_bp = UI["BREAKPOINTS"]


def _cols_for_width(w: int) -> int:
    if w < _def_bp[0]:
        return 1
    if w < _def_bp[1]:
        return 2
    if w < _def_bp[2]:
        return 3
    return 4


class HomeContainer(ft.Container):
    AREA = "home"

    def __init__(self):
        super().__init__(expand=True, padding=UI["ROOT_PADDING"])

        self.app_state = AppState()
        self.page = self.app_state.get_page()
        self.theme_ctrl = ThemeController()

        self._mounted = False
        self.colors = self._get_colors_area()
        self.user_data = self._load_user_safe()
        self.rol = self.user_data.get("rol", "guest")
        self.nombre = self.user_data.get("nombre_completo", self.user_data.get("username", "Usuario"))

        # Modo debug
        self.DEBUG = True

        # Layout dinámico (se recalcula en _recompute_layout)
        self._cols_postits = 2
        self._cols_stock = 2

        self._anim_tasks: dict[str, asyncio.Task] = {}

        # ---------- UI ----------
        self.title_text = ft.Text(
            f"Bienvenido, {self.nombre} ({self.rol})",
            size=UI["TITLE_SIZE"], weight="bold",
            color=self.colors.get("TITLE_FG", ft.colors.WHITE),
        )
        self.header_band = ft.Container(
            bgcolor=self.colors.get("TITLE_BG", ft.colors.RED_600),
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            border_radius=10,
            content=self.title_text,
        )
        self.section_line = ft.Divider(
            color=self.colors.get("SECTION_LINE", self.colors.get("DIVIDER_COLOR", ft.colors.RED_300)),
            height=14, thickness=1,
        )

        # Próximas citas
        self.postits_title = ft.Text(
            "Próximas citas (hoy)",
            size=UI["SECTION_TITLE_SIZE"], weight="bold",
            color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
        )
        self.btn_refresh_postits = ft.IconButton(
            icon=ft.icons.REFRESH, tooltip="Actualizar próximas citas",
            on_click=lambda e: self._reload_postits(),
        )
        self.postits_header = ft.Row(
            [self.postits_title, self.btn_refresh_postits],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self.postits_grid = ft.ResponsiveRow(
            controls=[],
            alignment=ft.MainAxisAlignment.START,
            columns=12,
            spacing=UI["GRID_SPACING"],
            run_spacing=UI["GRID_RUN_SPACING"],
        )
        self.agenda_postits_area = ft.Column([self.postits_header, self.postits_grid], spacing=8, visible=True)

        # Stock bajo
        self.stock_title = ft.Text(
            "Stock bajo", size=UI["SECTION_TITLE_SIZE"], weight="bold",
            color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
        )
        self.btn_refresh_stock = ft.IconButton(
            icon=ft.icons.REFRESH, tooltip="Actualizar stock bajo", on_click=lambda e: self._reload_low_stock(),
        )
        self.stock_header = ft.Row([self.stock_title, self.btn_refresh_stock],
                                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        self.stock_grid = ft.ResponsiveRow(
            controls=[],
            alignment=ft.MainAxisAlignment.START,
            columns=12,
            spacing=UI["GRID_SPACING"],
            run_spacing=UI["GRID_RUN_SPACING"],
        )
        self.stock_area = ft.Column([self.stock_header, self.stock_grid], spacing=8, visible=True)

        # Dashboard de prueba (REMOVIDO por defecto)
        self.dashboard_area: Optional[ft.Control] = None
        if UI["SHOW_DASHBOARD"]:
            self.dashboard_area = self._build_dashboard()

        # Columna principal
        self.main_column = ft.Column(
            [self.header_band, self.section_line, self.agenda_postits_area, self.stock_area]
            + ([self.dashboard_area] if self.dashboard_area else []),
            scroll=ft.ScrollMode.AUTO, expand=True, spacing=UI["SECTION_SPACING"],
        )

        # Centro y ancho legible
        center_container = ft.Container(content=self.main_column, width=UI["INNER_MAX_WIDTH"])
        self.inner = ft.Container(
            alignment=ft.alignment.top_center, expand=True,
            content=ft.Row([center_container], alignment=ft.MainAxisAlignment.CENTER),
        )
        self.content = self.inner

        # Eventos
        if self.page:
            self.page.on_resize = self._on_page_resize
        self.app_state.on_theme_change(self._on_theme_changed)

    # ---------- LOG helpers ----------
    def _log(self, msg: str, level: str = "info"):
        try:
            getattr(logger, level if level in ("debug", "info", "warning", "error") else "info")(msg)
        except Exception:
            print(f"[{level.upper()}] {msg}")

    def _dbg(self, msg: str):
        if self.DEBUG:
            self._log(msg, "debug")

    # ---------- ciclo de vida ----------
    def did_mount(self):
        self._mounted = True
        self.page = self.app_state.get_page()
        self._reload_user()
        self.colors = self._get_colors_area()
        self._apply_colors()
        self._recompute_layout()
        if UI["SHOW_DASHBOARD"]:
            self._rebuild_dashboard()  # solo si está habilitado
        self._reload_postits()
        self._reload_low_stock()
        self._safe_update()

    def will_unmount(self):
        for k, task in list(self._anim_tasks.items()):
            try:
                task.cancel()
            except Exception:
                pass
        self._anim_tasks.clear()
        self._mounted = False
        self.app_state.off_theme_change(self._on_theme_changed)

    # ---------- responsive ----------
    def _on_page_resize(self, e: ft.ControlEvent):
        self._recompute_layout()
        # re-aplicar columnas a tarjetas ya creadas
        self._apply_grid_cols(self.postits_grid, self._cols_postits)
        self._apply_grid_cols(self.stock_grid, self._cols_stock)
        self._safe_update()

    def _recompute_layout(self):
        """Calcula nº de columnas según ancho y aplica tope por área (2 por fila)."""
        w = getattr(self.page, "width", UI["INNER_MAX_WIDTH"] or 1200) or 1200
        base = _cols_for_width(w)
        self._cols_postits = min(base, UI["MAX_COLS"]["postits"])
        self._cols_stock = min(base, UI["MAX_COLS"]["stock"])
        self._dbg(f"[LAYOUT] width={w} → base={base} | postits_cols={self._cols_postits} stock_cols={self._cols_stock}")

    def _apply_grid_cols(self, grid: ft.ResponsiveRow, cols: int):
        unit = max(1, 12 // max(1, cols))
        for ctrl in grid.controls:
            try:
                ctrl.col = {"xs": 12, "sm": unit if cols > 1 else 12, "md": unit, "lg": unit, "xl": unit}
            except Exception:
                pass

    def _col_units(self, cols: int) -> dict:
        unit = max(1, 12 // max(1, cols))
        return {"xs": 12, "sm": unit if cols > 1 else 12, "md": unit, "lg": unit, "xl": unit}

    # ---------- tema / datos ----------
    def _on_theme_changed(self):
        self.colors = self._get_colors_area()
        self._apply_colors()
        self._safe_update()

    def _get_colors_area(self) -> dict:
        try:
            return self.theme_ctrl.get_colors(self.AREA) or {}
        except Exception:
            return {}

    def _reload_user(self):
        self.user_data = self._load_user_safe()
        self.rol = self.user_data.get("rol", "guest")
        self.nombre = self.user_data.get("nombre_completo", self.user_data.get("username", "Usuario"))

    def _apply_colors(self):
        self.bgcolor = self.colors.get("BG_COLOR", self.bgcolor)
        self.header_band.bgcolor = self.colors.get("TITLE_BG", ft.colors.RED_600)
        self.title_text.value = f"Bienvenido, {self.nombre} ({self.rol})"
        self.title_text.color = self.colors.get("TITLE_FG", ft.colors.WHITE)
        self.section_line.color = self.colors.get("SECTION_LINE", self.colors.get("DIVIDER_COLOR", ft.colors.RED_300))
        self.postits_title.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        self.stock_title.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        self._refresh_cards()

    def _refresh_cards(self):
        if self.dashboard_area and isinstance(self.dashboard_area, ft.Row):
            for c in self.dashboard_area.controls:
                if isinstance(c, ft.Container):
                    c.bgcolor = self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
                    border_col = self.colors.get("BORDER", None)
                    if border_col:
                        c.border = ft.border.all(1, border_col)
                    shadow_col = self.theme_ctrl.get_colors(self.AREA).get("SHADOW")
                    c.shadow = ft.BoxShadow(
                        blur_radius=10, spread_radius=0, offset=ft.Offset(0, 3),
                        color=shadow_col if shadow_col else ft.colors.with_opacity(0.12, ft.colors.BLACK),
                    )
                    if isinstance(c.content, ft.Column):
                        for t in c.content.controls:
                            if isinstance(t, ft.Text):
                                t.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _safe_update(self):
        if self.page:
            try:
                self.page.update()
            except AssertionError:
                pass

    def _load_user_safe(self) -> dict:
        p = getattr(self, "page", None)
        if not p:
            return {}
        try:
            raw = p.client_storage.get("app.user")
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str):
                raw = raw.strip()
                if raw.startswith("{}") or raw.startswith("[]"):
                    return {}
                if raw.startswith("{") or raw.startswith("["):
                    return json.loads(raw) or {}
            return {}
        except Exception:
            return {}

    # ---------- dashboards (deshabilitado por defecto) ----------
    def _build_dashboard(self) -> ft.Row:
        rol_method = {
            "barbero": self._barbero_dashboard,
            "dueno": self._dueno_dashboard,
            "recepcionista": self._recepcion_dashboard,
            "cajero": self._caja_dashboard,
            "inventarista": self._inventario_dashboard,
            "root": self._admin_dashboard,
        }.get(self.rol)
        return (rol_method() if rol_method else ft.Row([self._card("Rol no reconocido", "—")], expand=True))

    def _rebuild_dashboard(self):
        if not UI["SHOW_DASHBOARD"]:
            return
        self.dashboard_area = self._build_dashboard()
        # Reemplaza/inyecta al final si hiciera falta
        if self.dashboard_area not in self.main_column.controls:
            self.main_column.controls.append(self.dashboard_area)
        self._refresh_cards()
        self._safe_update()

    def _barbero_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Servicios asignados", "3"),
                       self._card("Comisión acumulada", "$450")], expand=True)

    def _dueno_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Ganancia total hoy", "$1200"),
                       self._card("Clientes atendidos", "18"),
                       self._card("Inventario crítico", "2 materiales")], expand=True)

    def _recepcion_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Citas del día", "12"),
                       self._card("Clientes en espera", "3")], expand=True)

    def _caja_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Cobros pendientes", "$300"),
                       self._card("Ventas del día", "$1500")], expand=True)

    def _inventario_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Materiales bajos", "5"),
                       self._card("Solicitudes abiertas", "2")], expand=True)

    def _admin_dashboard(self) -> ft.Row:
        return ft.Row([self._card("Usuarios activos", "6"),
                       self._card("Servicios totales hoy", "20"),
                       self._card("Ingresos generales", "$2000")], expand=True)

    def _card(self, title: str, value: str) -> ft.Container:
        return ft.Container(
            bgcolor=self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)),
            border_radius=UI["CARD_RADIUS"], padding=UI["CARD_PADDING"], expand=True,
            content=ft.Column(
                [ft.Text(title, size=16, weight="bold", color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
                 ft.Text(value, size=22, weight="bold", color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))],
                spacing=6, alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
        )

    # ---------- fecha helpers ----------
    def _to_dt(self, val) -> Optional[datetime]:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, _date):
            return datetime.combine(val, datetime.min.time())
        if isinstance(val, str):
            s = val.strip()
            if s.endswith("Z"):
                s = s[:-1]
            if "." in s:
                base, _, _tail = s.partition(".")
                s_try = [base]
            else:
                s_try = [s]
            patterns = [
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M",    "%Y-%m-%dT%H:%M",
                "%Y-%m-%d",
            ]
            for cand in s_try:
                for pat in patterns:
                    try:
                        return datetime.strptime(cand, pat)
                    except ValueError:
                        continue
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return None
        return None

    # ---------- próximas citas ----------
    def _reload_postits(self):
        # parar animaciones
        for k, task in list(self._anim_tasks.items()):
            try:
                task.cancel()
            except Exception:
                pass
        self._anim_tasks.clear()

        try:
            model = AgendaModel()
            now = datetime.now()
            start_day = datetime(now.year, now.month, now.day, 0, 0, 0)
            fin = start_day + timedelta(days=1)

            self._dbg(f"[POSTITS] now={now.isoformat()} start_day={start_day.isoformat()} fin={fin.isoformat()}")
            rows = model.listar_por_rango(inicio=start_day, fin=fin, estado=None, empresa_id=1) or []
            self._log(f"[POSTITS] filas recibidas hoy: {len(rows)}")

            norm: list[dict] = []
            seen_ids: set[Any] = set()
            estados_counter: dict[str, int] = {}
            parse_errors = 0

            for r in rows:
                rid = r.get(E_AGENDA.ID.value)
                estado_raw = (r.get(E_AGENDA.ESTADO.value) or "").strip().lower()
                estados_counter[estado_raw] = estados_counter.get(estado_raw, 0) + 1

                ini = self._to_dt(r.get(E_AGENDA.INICIO.value))
                fin_ = self._to_dt(r.get(E_AGENDA.FIN.value))
                if not ini:
                    parse_errors += 1
                    self._log(f"[POSTITS] ID={rid} estado={estado_raw} sin INICIO válido; se omite", "warning")
                    continue

                if rid is not None and rid in seen_ids:
                    self._log(f"[POSTITS] ID duplicado={rid}; se omite duplicado", "warning")
                    continue

                r["_inicio_dt"] = ini
                r["_fin_dt"] = fin_
                norm.append(r)
                if rid is not None:
                    seen_ids.add(rid)

            self._log(f"[POSTITS] normalizadas={len(norm)} parse_errors={parse_errors} estados={estados_counter}")

            proximas = [r for r in norm if r["_inicio_dt"].date() == now.date()]
            proximas.sort(key=lambda r: (r["_inicio_dt"], r.get(E_AGENDA.CLIENTE_NOM.value) or ""))

            self._log(f"[POSTITS] proximas_hoy={len(proximas)}")

            self.postits_grid.controls.clear()
            if not proximas:
                self.postits_grid.controls.append(
                    ft.Container(
                        content=ft.Text("No hay citas programadas para hoy.",
                                        color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
                        col={"xs": 12},
                    )
                )
            else:
                colmap = self._col_units(self._cols_postits)
                for r in proximas:
                    try:
                        c = self._build_postit(r, now)
                        c.col = colmap
                        c.margin = ft.margin.all(6)
                        self.postits_grid.controls.append(c)
                    except Exception as ex_item:
                        rid = r.get(E_AGENDA.ID.value)
                        est = r.get(E_AGENDA.ESTADO.value)
                        ini = r.get("_inicio_dt")
                        finx = r.get("_fin_dt")
                        self._log(f"[POSTITS] Error renderizando ID={rid} estado={est} inicio={ini} fin={finx}: {ex_item}", "error")
                        self.postits_grid.controls.append(
                            ft.Container(
                                bgcolor=ft.colors.RED_100, border_radius=UI["CARD_RADIUS"], padding=UI["CARD_PADDING"],
                                content=ft.Column(
                                    [
                                        ft.Text(f"Error en cita ID={rid} (estado={est})", color=ft.colors.RED_900),
                                        ft.Text(str(ex_item), color=ft.colors.RED_900, size=11, max_lines=3,
                                                overflow=ft.TextOverflow.ELLIPSIS),
                                    ],
                                    spacing=4,
                                ),
                                col=colmap,
                                margin=ft.margin.all(6),
                            )
                        )

            self._apply_grid_cols(self.postits_grid, self._cols_postits)
            self._safe_update()
        except Exception as ex:
            self._log(f"[POSTITS] EXCEPCIÓN GENERAL: {ex}", "error")
            self.postits_grid.controls.clear()
            self.postits_grid.controls.append(
                ft.Container(content=ft.Text(f"Error cargando citas: {ex}", color=ft.colors.RED_400),
                             col={"xs": 12})
            )
            self._safe_update()

    def _build_postit(self, r: dict, now: datetime) -> ft.Container:
        inicio: Optional[datetime] = r.get("_inicio_dt") or self._to_dt(r.get(E_AGENDA.INICIO.value))
        fin: Optional[datetime] = r.get("_fin_dt") or self._to_dt(r.get(E_AGENDA.FIN.value))

        titulo: str = r.get(E_AGENDA.TITULO.value) or "Servicio"
        cliente: str = r.get(E_AGENDA.CLIENTE_NOM.value) or "Cliente"
        tel: str = r.get(E_AGENDA.CLIENTE_TEL.value) or ""
        notas: str = r.get(E_AGENDA.NOTAS.value) or ""

        fin_safe = fin
        if inicio and (fin_safe is None or fin_safe <= inicio):
            fin_safe = inicio + timedelta(minutes=DEFAULT_DURATION_MIN)
            self._dbg(f"[POSTIT] Ajuste fin_safe (ID={r.get(E_AGENDA.ID.value)}): fin={fin} -> fin_safe={fin_safe}")

        if not inicio or not fin_safe:
            self._log(f"[POSTIT] Sin fechas válidas → render neutro (ID={r.get(E_AGENDA.ID.value)})", "warning")
            return ft.Container(
                bgcolor=self.colors.get("CARD_BG", ft.colors.SURFACE_VARIANT),
                border_radius=UI["CARD_RADIUS"], padding=UI["CARD_PADDING"], expand=True,
                content=ft.Column(
                    [
                        ft.Text(titulo, size=UI["POSTIT"]["TITULO"], weight="w600",
                                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                                max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(f"{cliente}" + (f" · {tel}" if tel else ""), size=UI["POSTIT"]["CLIENTE"],
                                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(notas or "", size=UI["POSTIT"]["NOTAS"], italic=True,
                                color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                                max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ],
                    spacing=UI["POSTIT"]["LINE_SPACING"], alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
            )

        badge_text, card_bg, fg_color, shake, blink = self._status_info(r, inicio, fin, fin_safe, now)
        self._dbg(f"[POSTIT] ID={r.get(E_AGENDA.ID.value)} badge='{badge_text}' fg={fg_color} bg={card_bg}")

        linea1 = ft.Text(f"{inicio.strftime('%H:%M')} - {fin_safe.strftime('%H:%M')}",
                         weight="bold", size=UI["POSTIT"]["HORA"], color=fg_color)
        linea2 = ft.Text(titulo, size=UI["POSTIT"]["TITULO"], weight="w600", color=fg_color,
                         max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
        linea3 = ft.Text(f"{cliente}" + (f" · {tel}" if tel else ""), size=UI["POSTIT"]["CLIENTE"], color=fg_color,
                         max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        linea4 = ft.Text(notas or "", size=UI["POSTIT"]["NOTAS"], italic=True, color=fg_color,
                         max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)

        badge = ft.Container(
            bgcolor=ft.colors.with_opacity(0.18, ft.colors.BLACK),
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=12,
            content=ft.Text(badge_text, size=UI["POSTIT"]["BADGE"], weight="bold", color=fg_color),
        )

        actions = self._postit_actions(r, inicio, fin_safe, now, fg_color)

        content_controls = [ft.Row([linea1, badge], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            linea2, linea3]
        if notas:
            content_controls.append(linea4)
        if actions is not None:
            content_controls.append(actions)

        rid_str = str(r.get(E_AGENDA.ID.value) or "x")
        key_suffix = (inicio or fin_safe).strftime("%Y%m%d%H%M%S")
        postit = ft.Container(
            key=f"postit-{rid_str}-{key_suffix}",
            bgcolor=card_bg, border_radius=UI["CARD_RADIUS"], padding=UI["CARD_PADDING"], expand=True,
            content=ft.Column(content_controls, spacing=UI["POSTIT"]["LINE_SPACING"],
                              alignment=ft.MainAxisAlignment.START,
                              horizontal_alignment=ft.CrossAxisAlignment.START),
            shadow=ft.BoxShadow(blur_radius=10, offset=ft.Offset(0, 4),
                                color=ft.colors.with_opacity(0.18, ft.colors.BLACK)),
            animate_opacity=300, animate_scale=300, animate_offset=300,
        )

        if shake:
            self._start_shake(postit, duration_sec=6)
        if blink:
            self._start_blink(postit)
        return postit

    # ---------- acciones rápidas ----------
    def _postit_actions(self, row: dict, inicio: datetime, fin: Optional[datetime],
                        now: datetime, fg_color: str) -> Optional[ft.Control]:
        show_complete, show_cancel = self._can_postit_actions(row, inicio, fin, now)
        if not (show_complete or show_cancel):
            return None

        def _ico(icon, tip, on_click):
            return ft.IconButton(icon=icon, tooltip=tip, on_click=on_click,
                                 icon_size=16, style=ft.ButtonStyle(padding=0),
                                 icon_color=fg_color)

        controls = []
        if show_complete:
            controls.append(_ico(
                ft.icons.CHECK_CIRCLE, "Marcar como completada",
                lambda e, r=row, i=inicio, f=fin, n=now: self._quick_update_estado_postit(
                    r, E_AGENDA_ESTADO.COMPLETADA.value, i, f, n)))
        if show_cancel:
            controls.append(_ico(
                ft.icons.CLOSE, "Cancelar cita",
                lambda e, r=row, i=inicio, f=fin, n=now: self._quick_update_estado_postit(
                    r, E_AGENDA_ESTADO.CANCELADA.value, i, f, n)))
        return ft.Row(controls, spacing=6, alignment=ft.MainAxisAlignment.START)

    def _can_postit_actions(self, row: dict, inicio: datetime, fin: Optional[datetime],
                            now: datetime) -> tuple[bool, bool]:
        estado_raw = (row.get(E_AGENDA.ESTADO.value) or "").strip().lower()
        if estado_raw in {E_AGENDA_ESTADO.COMPLETADA.value, E_AGENDA_ESTADO.CANCELADA.value,
                          "pagada", "pagado", "pagadas", "paid"}:
            return (False, False)
        if inicio > now:
            return (True, True)
        if fin and fin > now:
            return (True, True)
        return (False, False)

    def _quick_update_estado_postit(self, row: dict, nuevo_estado: str,
                                    inicio: datetime, fin: Optional[datetime], now: datetime):
        try:
            rid = row.get(E_AGENDA.ID.value)
            if not rid:
                self._notify_snack("❌ Registra la cita antes de actualizar el estado.", True)
                return
            try:
                rid_int = int(rid)
            except Exception:
                rid_int = rid

            inicio_dt = inicio or self._to_dt(row.get(E_AGENDA.INICIO.value))
            if not inicio_dt:
                self._notify_snack("❌ Inicio inválido.", True)
                return

            fin_dt = fin or self._to_dt(row.get(E_AGENDA.FIN.value)) or (inicio_dt + timedelta(minutes=DEFAULT_DURATION_MIN))
            if nuevo_estado == E_AGENDA_ESTADO.COMPLETADA.value:
                fin_actual = now.replace(second=0, microsecond=0)
                if fin_actual <= inicio_dt:
                    fin_actual = inicio_dt + timedelta(minutes=DEFAULT_DURATION_MIN)
                fin_dt = fin_actual

            titulo = row.get(E_AGENDA.TITULO.value) or row.get("servicio_txt") or None
            notas = row.get(E_AGENDA.NOTAS.value)

            trabajador_id = row.get(E_AGENDA.TRABAJADOR_ID.value)
            if trabajador_id is not None:
                try:
                    trabajador_id = int(trabajador_id)
                except Exception:
                    pass

            cliente_nombre = row.get(E_AGENDA.CLIENTE_NOM.value)
            cliente_tel = (row.get(E_AGENDA.CLIENTE_TEL.value) or "").strip()
            cliente_tel = "".join(ch for ch in cliente_tel if ch.isdigit()) or None

            servicio_id = row.get("servicio_id")
            if servicio_id is not None:
                try:
                    servicio_id = int(servicio_id)
                except Exception:
                    pass

            cantidad = row.get("cantidad"); precio_unit = row.get("precio_unit"); total = row.get("total")
            try:
                cantidad = int(cantidad) if cantidad is not None else None
            except:
                cantidad = None
            try:
                precio_unit = float(precio_unit) if precio_unit is not None else None
            except:
                precio_unit = None
            try:
                total = float(total) if total is not None else None
            except:
                total = None

            todo_dia = bool(row.get(E_AGENDA.TODO_DIA.value, False))
            color = row.get(E_AGENDA.COLOR.value)

            uid = None
            try:
                sess = self.page.client_storage.get("app.user") if self.page else None
                uid = (sess or {}).get("id_usuario")
            except Exception:
                uid = None

            model = AgendaModel()
            res = model.actualizar_cita(
                cita_id=rid_int, titulo=titulo, inicio=inicio_dt, fin=fin_dt,
                todo_dia=todo_dia, color=color, notas=notas,
                trabajador_id=trabajador_id, cliente_nombre=cliente_nombre, cliente_tel=cliente_tel,
                estado=nuevo_estado, servicio_id=servicio_id,
                cantidad=cantidad, precio_unit=precio_unit, total=total,
                updated_by=uid,
            )

            if res.get("status") == "success":
                msg = "✅ Cita marcada como completada." if nuevo_estado == E_AGENDA_ESTADO.COMPLETADA.value else "⚠️ Cita cancelada."
                self._notify_snack(msg, False)
                self._reload_postits()
            else:
                self._notify_snack(f"❌ {res.get('message', 'No se pudo actualizar el estado')}", True)

        except Exception as ex:
            self._log(f"[POSTITS] _quick_update_estado_postit EXC: {ex}", "error")
            self._notify_snack(f"❌ Error: {ex}", True)

    # ---------- snack ----------
    def _notify_snack(self, msg: str, error: bool = False):
        self._log(f"[SNACK] {msg}", "error" if error else "info")
        if not self.page:
            return
        if error:
            self.page.snack_bar = ft.SnackBar(ft.Text(msg, color=ft.colors.WHITE), bgcolor=ft.colors.RED_600)
        else:
            self.page.snack_bar = ft.SnackBar(
                ft.Text(msg, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
                bgcolor=self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)),
            )
        self.page.snack_bar.open = True
        self._safe_update()

    # ---------- estado/badge ----------
    def _format_future(self, mins: int) -> str:
        if mins < 60:
            return f"en {mins} min"
        h, m = mins // 60, mins % 60
        return f"en {h}h {m}m" if m else f"en {h}h"

    def _format_past(self, mins: int) -> str:
        if mins < 60:
            return f"{mins} min"
        h, m = mins // 60, mins % 60
        return f"{h}h {m}m" if m else f"{h}h"

    def _estado_equivalente_completada(self, estado_raw: str) -> bool:
        return (estado_raw or "").lower() in {E_AGENDA_ESTADO.COMPLETADA.value, "pagada", "pagado", "pagadas", "paid"}

    def _status_info(self, row: dict, inicio: datetime, fin_orig: Optional[datetime],
                     fin_safe: datetime, now: datetime) -> tuple[str, str, str, bool, bool]:
        estado_raw = (row.get(E_AGENDA.ESTADO.value) or "").strip().lower()
        mins_to_start = int((inicio - now).total_seconds() // 60)

        if estado_raw == E_AGENDA_ESTADO.CANCELADA.value:
            return ("Cancelada", ft.colors.GREY_500, ft.colors.WHITE, False, False)

        if self._estado_equivalente_completada(estado_raw):
            if now < inicio:
                return ("Completada (anticipada)", ft.colors.GREEN_400, ft.colors.WHITE, False, False)
            mins_past = int((now - (fin_orig or inicio)).total_seconds() // 60)
            return (f"Completada hace {self._format_past(max(1, mins_past))}",
                    ft.colors.GREEN_200, ft.colors.BLACK, False, False)

        if mins_to_start > 0:
            badge_text = self._format_future(mins_to_start)
            card_bg, fg_color = self._severity_colors(mins_to_start)
            shake = mins_to_start <= 20
            blink = mins_to_start <= 5
            return badge_text, card_bg, fg_color, shake, blink

        if fin_safe and fin_safe > now:
            return ("En curso", ft.colors.BLUE_400, ft.colors.WHITE, False, False)

        mins_past = int((now - (fin_orig or inicio)).total_seconds() // 60)
        return (f"Atrasada {self._format_past(max(1, mins_past))}",
                ft.colors.RED_200, ft.colors.BLACK, False, False)

    def _severity_colors(self, mins: int) -> tuple[str, str]:
        if mins <= 20:
            return (ft.colors.RED_400, ft.colors.WHITE)
        if mins <= 60:
            return (ft.colors.ORANGE_400, ft.colors.WHITE)
        if mins <= 120:
            return (ft.colors.GREEN_400, ft.colors.WHITE)
        return (self.colors.get("CARD_BG", ft.colors.SURFACE_VARIANT),
                self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

    # ---------- animaciones ----------
    def _start_blink(self, ctrl: ft.Container, key_suffix: str = "blink"):
        if not self._mounted or not self.page:
            return
        k = f"{ctrl.key or id(ctrl)}-{key_suffix}"
        if k in self._anim_tasks:
            return

        async def _blink_task():
            try:
                fade_low = 0.55
                while self._mounted:
                    ctrl.opacity = fade_low
                    self._safe_update()
                    await asyncio.sleep(0.6)
                    ctrl.opacity = 1.0
                    self._safe_update()
                    await asyncio.sleep(0.6)
            except asyncio.CancelledError:
                ctrl.opacity = 1.0
                self._safe_update()
                raise
            finally:
                # limpia el registro si fue cancelada o terminó
                self._anim_tasks.pop(k, None)

        # ⬇️ OJO: pasar la FUNCIÓN, sin paréntesis
        task = self.page.run_task(_blink_task)
        self._anim_tasks[k] = task

    def _start_shake(self, ctrl: ft.Container, duration_sec: int = 6, key_suffix: str = "shake"):
        if not self._mounted or not self.page:
            return
        k = f"{ctrl.key or id(ctrl)}-{key_suffix}"
        if k in self._anim_tasks:
            return

        async def _shake_task():
            try:
                end = datetime.now() + timedelta(seconds=duration_sec)
                step = 0
                while self._mounted and datetime.now() < end:
                    dx = (-1) ** step * 4
                    ctrl.offset = ft.transform.Offset(dx / 100.0, 0)
                    self._safe_update()
                    step += 1
                    await asyncio.sleep(0.08)
                ctrl.offset = ft.transform.Offset(0, 0)
                self._safe_update()
            except asyncio.CancelledError:
                ctrl.offset = ft.transform.Offset(0, 0)
                self._safe_update()
                raise
            finally:
                self._anim_tasks.pop(k, None)

        # ⬇️ Igual: pasar la FUNCIÓN, sin paréntesis
        task = self.page.run_task(_shake_task)
        self._anim_tasks[k] = task

    # ---------- stock ----------
    def _reload_low_stock(self):
        try:
            inv = InventarioModel(empresa_id=1)
            rows = inv.listar_bajo_stock() or []
            self._log(f"[STOCK] items={len(rows)}")
            self.stock_grid.controls.clear()

            if not rows:
                self.stock_grid.controls.append(
                    ft.Container(
                        content=ft.Text("Sin productos en stock bajo.",
                                        color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
                        col={"xs": 12},
                    )
                )
            else:
                colmap = self._col_units(self._cols_stock)
                for r in rows:
                    try:
                        nombre = str(r.get("nombre", "—"))
                        stock_actual = float(r.get("stock_actual", 0))
                        stock_minimo = float(r.get("stock_minimo", 0))
                        card = self._build_stock_card(nombre, stock_actual, stock_minimo)
                        card.col = colmap
                        card.margin = ft.margin.all(6)
                        self.stock_grid.controls.append(card)
                    except Exception as ex_item:
                        self._log(f"[STOCK] Error render card: {ex_item}", "error")
                        self.stock_grid.controls.append(
                            ft.Container(
                                bgcolor=ft.colors.RED_100, border_radius=UI["CARD_RADIUS"], padding=UI["CARD_PADDING"],
                                content=ft.Text(f"Error item: {ex_item}", color=ft.colors.RED_900),
                                col=colmap,
                                margin=ft.margin.all(6),
                            )
                        )

            self._apply_grid_cols(self.stock_grid, self._cols_stock)
            self._safe_update()
        except Exception as ex:
            self._log(f"[STOCK] EXCEPCIÓN GENERAL: {ex}", "error")
            self.stock_grid.controls.clear()
            self.stock_grid.controls.append(
                ft.Container(content=ft.Text(f"Error cargando stock bajo: {ex}", color=ft.colors.RED_400),
                             col={"xs": 12})
            )
            self._safe_update()

    def _build_stock_card(self, nombre: str, actual: float, minimo: float) -> ft.Container:
        bg = ft.colors.RED_100 if actual <= minimo else self.colors.get("CARD_BG", ft.colors.SURFACE_VARIANT)
        fg = ft.colors.RED_900 if actual <= minimo else self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        return ft.Container(
            key=f"stock-{nombre}",
            bgcolor=bg, border_radius=UI["CARD_RADIUS"], padding=UI["CARD_PADDING"], expand=True,
            content=ft.Column(
                [
                    ft.Text(nombre, size=UI["STOCK"]["NOMBRE"], weight="bold", color=fg, max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"Actual: {actual}", size=UI["STOCK"]["NUM"], color=fg),
                    ft.Text(f"Mínimo: {minimo}", size=UI["STOCK"]["NUM"], color=fg),
                ],
                spacing=4, alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
            shadow=ft.BoxShadow(blur_radius=8, offset=ft.Offset(0, 3),
                                color=ft.colors.with_opacity(0.15, ft.colors.BLACK)),
        )
