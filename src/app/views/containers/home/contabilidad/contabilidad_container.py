from __future__ import annotations
import flet as ft
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.config.application.app_state import AppState
from app.views.containers.nvar.layout_controller import LayoutController

from app.models.trabajadores_model import TrabajadoresModel
from app.models.contabilidad_model import NominaModel, GananciasModel

# ------------------------ Utils ------------------------
def _dec(v: Any, fb: str = "0.00") -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(fb)

def _money(v: Any) -> str:
    return f"{_dec(v):,.2f}"

def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())

# =========================================================
class ContabilidadContainer(ft.Container):
    """
    Resumen de ganancias por trabajador con acciones de Pago parcial / Pagar todo.

    REGLAS EN UI:
    - Colores: AppState.get_colors("contabilidad")
    - NO se recalcula gan_empleado / gan_empresa en el container.
      Se muestran los valores ya preparados por GananciasModel:
        * Prioriza snapshots por corte (COM_MONTO / SUC_MONTO).
        * Si faltan, el propio modelo calcula: emp = total * pct/100 ; empresa = total - emp.
    """

    def __init__(self):
        super().__init__(expand=True, padding=10)

        # Estado global / layout
        self.app = AppState()
        self.layout = LayoutController()
        try:
            self.page = self.app.get_page()
        except Exception:
            self.page = getattr(self.app, "page", None)

        # Paleta desde AppState (no ThemeController)
        self.colors = self.app.get_colors("contabilidad")
        print(f"[CONTAB] Paleta 'contabilidad' cargada: keys={len(self.colors)}")

        # Permisos
        self.is_root = self._is_root()

        # Modelos
        self.trab_model = TrabajadoresModel()
        self.nomina = NominaModel()
        self.gan = GananciasModel(self.nomina)

        # Filtros
        today = date.today()
        self.start_date: date = _monday(today)
        self.end_date: date = today
        self.filter_trab: Optional[int] = None

        # Datos
        self.summary_rows: List[Dict[str, Any]] = []
        self.summary_totals: Dict[str, Any] = {}

        # UI refs
        self._list_host: Optional[ft.Container] = None
        self._totals_host: Optional[ft.Container] = None
        self._tf_start: Optional[ft.TextField] = None
        self._tf_end: Optional[ft.TextField] = None
        self._dd_trab: Optional[ft.Dropdown] = None

        # Build
        print("[CONTAB] Inicializando ContabilidadContainer...")
        self._build_ui()
        self._load_and_render()

    # ------------------------- permisos
    def _is_root(self) -> bool:
        try:
            sess = self.app.get_client_value("app.user", None)
        except Exception:
            sess = None
        rol = (sess or {}).get("rol", "")
        username = (sess or {}).get("username", "")
        rol = (rol or "").strip().lower()
        username = (username or "").strip().lower()
        val = (rol == "root" or username == "root")
        print(f"[CONTAB] Permisos → is_root={val}")
        return val

    # ------------------------- UI
    def _build_ui(self):
        pal = self.colors

        self._tf_start = ft.TextField(
            label="Desde",
            value=self.start_date.isoformat(),
            width=150, dense=True, text_size=12,
            content_padding=ft.padding.symmetric(8, 6),
        )
        self._tf_end = ft.TextField(
            label="Hasta",
            value=self.end_date.isoformat(),
            width=150, dense=True, text_size=12,
            content_padding=ft.padding.symmetric(8, 6),
        )
        self._apply_tf_palette(self._tf_start)
        self._apply_tf_palette(self._tf_end)

        # Dropdown trabajadores activos
        opts = [ft.dropdown.Option("", "Todos")]
        try:
            # Acepta distintos esquemas (estado=1/True/"activo")
            trs = (self.trab_model.listar(estado=1)
                   or self.trab_model.listar(estado=True)
                   or self.trab_model.listar(estado="activo")
                   or [])
        except Exception:
            trs = []
        for t in trs:
            tid = t.get("id") or t.get("trabajador_id") or t.get("ID")
            nom = t.get("nombre") or t.get("NOMBRE") or t.get("name") or f"Trabajador {tid}"
            if tid is not None:
                opts.append(ft.dropdown.Option(str(tid), nom))

        self._dd_trab = ft.Dropdown(
            label="Trabajador",
            options=opts, width=220, dense=True,
            on_change=lambda e: self._apply_filters(),
        )
        self._dd_trab.text_style = ft.TextStyle(color=pal.get("FG_COLOR"), size=12)

        btn_aplicar = ft.FilledButton(
            "Aplicar", icon=ft.icons.SEARCH,
            on_click=lambda e: self._apply_filters(),
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(6, 6),
                bgcolor=pal.get("ACCENT"),
                color=pal.get("ON_PRIMARY", ft.colors.WHITE),
            ),
        )

        toolbar = ft.ResponsiveRow(
            columns=12, spacing=10, run_spacing=10,
            controls=[
                ft.Container(self._tf_start, col={"xs":6, "md":3, "lg":2}),
                ft.Container(self._tf_end,   col={"xs":6, "md":3, "lg":2}),
                ft.Container(self._dd_trab,  col={"xs":12, "md":4, "lg":3}),
                ft.Container(btn_aplicar,    col={"xs":6, "md":2, "lg":2}),
            ]
        )

        self._totals_host = ft.Container(
            content=self._totals_panel(),
            padding=10,
            bgcolor=pal.get("CARD_BG"),
            border=ft.border.all(1, pal.get("BORDER_COLOR")),
            border_radius=8
        )

        self._list_column = ft.Column([], expand=True, spacing=8)
        self._list_host = ft.Container(content=self._list_column, expand=True)

        self.content = ft.Column(
            [
                ft.Text("Contabilidad", size=18, weight="bold", color=pal.get("FG_COLOR")),
                ft.Divider(color=pal.get("DIVIDER_COLOR")),
                toolbar,
                ft.Container(height=8),
                self._totals_host,
                ft.Container(height=8),
                self._list_host,
            ],
            expand=True,
            spacing=8,
        )
        self.bgcolor = pal.get("BG_COLOR")

    def _apply_tf_palette(self, tf: ft.TextField):
        pal = self.colors
        tf.bgcolor = pal.get("FIELD_BG", pal.get("CARD_BG"))
        tf.color = pal.get("FG_COLOR")
        tf.label_style = ft.TextStyle(color=pal.get("FG_COLOR"))
        tf.hint_style = ft.TextStyle(color=pal.get("MUTED"), size=11)
        tf.cursor_color = pal.get("FG_COLOR")
        tf.border_color = pal.get("DIVIDER_COLOR")
        tf.focused_border_color = pal.get("FG_COLOR")

    # ------------------------- Datos
    def _apply_filters(self):
        try:
            s = date.fromisoformat(self._tf_start.value or self.start_date.isoformat())
        except Exception:
            s = self.start_date
        try:
            e = date.fromisoformat(self._tf_end.value or self.end_date.isoformat())
        except Exception:
            e = self.end_date
        if e < s:
            s, e = e, s
        self.start_date, self.end_date = s, e

        v = (self._dd_trab.value or "").strip()
        self.filter_trab = int(v) if v.isdigit() else None

        self._load_and_render()

    def _load_and_render(self):
        ini = datetime.combine(self.start_date, datetime.min.time())
        fin = datetime.combine(self.end_date, datetime.max.time())
        print(f"[CONTAB] Cargando resumen_por_rango(inicio={ini}, fin={fin}, trabajador_id={self.filter_trab})")
        try:
            res = self.gan.resumen_por_rango(inicio=ini, fin=fin, trabajador_id=self.filter_trab)
            self.summary_rows = res.get("rows", [])
            self.summary_totals = res.get("totals", {})
            print(f"[CONTAB] Resumen listo (sin recomputar): rows={len(self.summary_rows)} totals={self.summary_totals}")
        except Exception as ex:
            self.summary_rows, self.summary_totals = [], {}
            self._snack_error(f"Error cargando resumen: {ex}")
            print(f"[CONTAB][ERR] resumen_por_rango → {ex}")

        # Pintar UI
        self._totals_host.content = self._totals_panel()
        self._list_column.controls.clear()
        self._list_column.controls.extend(self._build_cards(self.summary_rows))
        self._safe_update()
        print("[CONTAB] Render completado (valores del modelo).")

    # ------------------------- Render helpers
    def _totals_panel(self) -> ft.Control:
        pal = self.colors
        t = self.summary_totals or {}

        def _kpi(title: str, value: str) -> ft.Control:
            return ft.Container(
                col={"xs": 6, "md": 4, "lg": 2},
                content=ft.Column(
                    [
                        ft.Text(title, size=11, color=pal.get("MUTED")),
                        ft.Text(value, size=16, weight="bold", color=pal.get("FG_COLOR")),
                    ],
                    spacing=2,
                ),
                bgcolor=pal.get("CARD_BG"),
                padding=10,
                border_radius=8,
                border=ft.border.all(1, pal.get("BORDER_COLOR")),
            )

        grid = ft.ResponsiveRow(
            columns=12, spacing=8, run_spacing=8,
            controls=[
                _kpi("Cortes", f"{int(t.get('cortes', 0))}"),
                _kpi("Total $", _money(t.get("total", 0))),
                _kpi("Gan. empleados $", _money(t.get("gan_empleado", 0))),
                _kpi("Gan. empresa $", _money(t.get("gan_empresa", 0))),
                _kpi("Pagado $", _money(t.get("pagado", 0))),
                _kpi("Pendiente $", _money(t.get("pendiente", 0))),
            ],
        )
        return grid

    def _build_cards(self, rows: List[Dict[str, Any]]) -> List[ft.Control]:
        pal = self.colors
        items: List[ft.Control] = []
        for r in rows or []:
            tid = int(r.get("trabajador_id") or 0)
            nombre = r.get("trabajador") or f"Trabajador {tid or ''}"
            cortes = int(r.get("cortes") or 0)
            total = _money(r.get("total"))
            gan_emp = _money(r.get("gan_empleado"))
            gan_neg = _money(r.get("gan_empresa"))
            pagado = _money(r.get("pagado"))
            pendiente = _money(r.get("pendiente"))

            btn_det = ft.TextButton(
                "Detalle", on_click=lambda e, _tid=tid: self._open_detail_dialog_by_id(_tid),
            )
            btn_pagar = ft.FilledTonalButton(
                "Pagar", icon=ft.icons.PAYMENTS,
                on_click=lambda e, _tid=tid: self._open_pay_dialog_by_id(_tid),
                disabled=(r.get("pendiente", 0) <= 0) or not self.is_root,
            )
            btn_pagar_todo = ft.FilledButton(
                "Pagar todo", icon=ft.icons.ATTACH_MONEY,
                on_click=lambda e, _tid=tid: self._confirm_pay_all_dialog_by_id(_tid),
                disabled=(r.get("pendiente", 0) <= 0) or not self.is_root,
            )

            header = ft.Row(
                [
                    ft.Text(nombre, size=14, weight="bold", color=pal.get("FG_COLOR")),
                    ft.Container(expand=True),
                    ft.Row([btn_det, btn_pagar, btn_pagar_todo], spacing=6),
                ],
                alignment=ft.MainAxisAlignment.START,
            )
            grid = ft.ResponsiveRow(
                columns=12, spacing=6, run_spacing=6,
                controls=[
                    ft.Container(ft.Text(f"Cortes: {cortes}", size=12, color=pal.get("FG_COLOR")), col={"xs":6, "md":3, "lg":2}),
                    ft.Container(ft.Text(f"Total: $ {total}", size=12, color=pal.get("FG_COLOR")), col={"xs":6, "md":3, "lg":2}),
                    ft.Container(ft.Text(f"Emp: $ {gan_emp}", size=12, color=pal.get("FG_COLOR")), col={"xs":6, "md":3, "lg":2}),
                    ft.Container(ft.Text(f"Negocio: $ {gan_neg}", size=12, color=pal.get("FG_COLOR")), col={"xs":6, "md":3, "lg":2}),
                    ft.Container(ft.Text(f"Pagado: $ {pagado}", size=12, color=pal.get("FG_COLOR")), col={"xs":6, "md":3, "lg":2}),
                    ft.Container(ft.Text(f"Pendiente: $ {pendiente}", size=12, color=pal.get("FG_COLOR")), col={"xs":6, "md":3, "lg":2}),
                ],
            )
            card = ft.Container(
                content=ft.Column([header, grid], spacing=6),
                bgcolor=pal.get("CARD_BG"),
                padding=10,
                border_radius=10,
                border=ft.border.all(1, pal.get("BORDER_COLOR")),
            )
            items.append(card)

        if not items:
            items.append(ft.Text("Sin resultados para el rango/criterios.", color=pal.get("MUTED")))

        return items

    # ------------------------- Lookups by id
    def _find_row(self, trabajador_id: int) -> Dict[str, Any] | None:
        tid = int(trabajador_id or 0)
        for r in self.summary_rows or []:
            try:
                if int(r.get("trabajador_id") or 0) == tid:
                    return r
            except Exception:
                continue
        return None

    # ------------------------- Modals
    def _open_pay_dialog_by_id(self, trabajador_id: int):
        pal = self.colors
        r = self._find_row(trabajador_id)
        if not r:
            self._snack_error("No se encontró el trabajador.")
            return
        nombre = r.get("trabajador") or f"Trabajador {trabajador_id}"
        pendiente_val = _dec(r.get("pendiente") or 0)
        generado_emp = _dec(r.get("gan_empleado") or 0)

        tf_monto = ft.TextField(
            label="Monto a pagar",
            value=f"{pendiente_val:.2f}",
            keyboard_type=ft.KeyboardType.NUMBER,
            dense=True, width=220, text_size=12,
            text_align=ft.TextAlign.RIGHT,
        )
        self._apply_tf_palette(tf_monto)
        tf_nota = ft.TextField(label="Nota (opcional)", value=f"Pago a {nombre}", dense=True, width=320, text_size=12)
        self._apply_tf_palette(tf_nota)

        info = ft.Column(
            [
                ft.Text(f"Generado (empleado): $ {generado_emp:.2f}", size=11, color=pal.get("MUTED")),
                ft.Text(f"Máximo a pagar (pendiente): $ {pendiente_val:.2f}", size=11, color=pal.get("MUTED")),
            ],
            spacing=2,
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Pagar a {nombre}", weight="bold", color=pal.get("FG_COLOR")),
            content=ft.Column([info, tf_monto, tf_nota], spacing=8, tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_dialog(e)),
                ft.FilledButton(
                    "Confirmar pago", icon=ft.icons.CHECK,
                    on_click=lambda e, _tid=trabajador_id: self._confirm_pay_from_controls(_tid, tf_monto.value, tf_nota.value),
                    style=ft.ButtonStyle(bgcolor=pal.get("ACCENT"), color=pal.get("ON_PRIMARY", ft.colors.WHITE)),
                ),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self._safe_update()

    def _confirm_pay_from_controls(self, trabajador_id: int, monto_text: str, nota: str):
        r = self._find_row(trabajador_id)
        if not r:
            self._snack_error("No se encontró el trabajador.")
            return
        pendiente = _dec(r.get("pendiente") or 0)
        try:
            monto = _dec(monto_text or "0")
        except Exception:
            self._snack_error("Monto inválido."); return
        if monto <= 0:
            self._snack_error("El monto debe ser mayor a 0."); return
        if monto > pendiente:
            self._snack_error(f"El monto no puede exceder el pendiente ($ {_money(pendiente)})."); return

        ini = datetime.combine(self.start_date, datetime.min.time())
        fin = datetime.combine(self.end_date, datetime.max.time())
        try:
            sess = self.page.client_storage.get("app.user") if self.page else None
            uid = (sess or {}).get("id_usuario")
        except Exception:
            uid = None

        res = self.nomina.registrar_pago(
            trabajador_id=int(trabajador_id),
            monto=float(monto),
            fecha=datetime.now(),
            nota=(nota or None),
            inicio_periodo=ini,
            fin_periodo=fin,
            created_by=uid,
        )
        if res.get("status") == "success":
            self._snack_ok("Pago registrado.")
            self._dismiss_dialog()
            self._load_and_render()
        else:
            self._snack_error(f"Error al pagar: {res.get('message')}")

    def _confirm_pay_all_dialog_by_id(self, trabajador_id: int):
        pal = self.colors
        r = self._find_row(trabajador_id)
        if not r:
            self._snack_error("No se encontró el trabajador."); return
        pendiente = _dec(r.get("pendiente") or 0)
        if pendiente <= 0:
            self._snack_error("No hay pendiente por pagar."); return
        nombre = r.get("trabajador") or f"Trabajador {trabajador_id}"

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar pago total", weight="bold", color=pal.get("FG_COLOR")),
            content=ft.Text(f"Se pagará TODO el pendiente a {nombre}: $ {pendiente:.2f}", color=pal.get("FG_COLOR")),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_dialog(e)),
                ft.FilledButton(
                    "Pagar todo", icon=ft.icons.ATTACH_MONEY,
                    on_click=lambda e, _tid=trabajador_id: self._confirm_pay_all_by_id(_tid),
                    style=ft.ButtonStyle(bgcolor=pal.get("ACCENT"), color=pal.get("ON_PRIMARY", ft.colors.WHITE)),
                ),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self._safe_update()

    def _confirm_pay_all_by_id(self, trabajador_id: int):
        r = self._find_row(trabajador_id)
        if not r:
            self._snack_error("No se encontró el trabajador."); return
        pendiente = _dec(r.get("pendiente") or 0)
        if pendiente <= 0:
            self._snack_error("No hay pendiente por pagar."); return

        ini = datetime.combine(self.start_date, datetime.min.time())
        fin = datetime.combine(self.end_date, datetime.max.time())
        try:
            sess = self.page.client_storage.get("app.user") if self.page else None
            uid = (sess or {}).get("id_usuario")
        except Exception:
            uid = None

        res = self.nomina.registrar_pago(
            trabajador_id=int(trabajador_id),
            monto=float(pendiente),
            fecha=datetime.now(),
            nota=f"Pago total de pendiente ({self.start_date} a {self.end_date})",
            inicio_periodo=ini,
            fin_periodo=fin,
            created_by=uid,
        )
        if res.get("status") == "success":
            self._snack_ok("Pago total registrado.")
            self._dismiss_dialog()
            self._load_and_render()
        else:
            self._snack_error(f"Error al pagar: {res.get('message')}")

    def _open_detail_dialog_by_id(self, trabajador_id: int):
        pal = self.colors
        ini = datetime.combine(self.start_date, datetime.min.time())
        fin = datetime.combine(self.end_date, datetime.max.time())
        try:
            detalle = self.gan.detalle_trabajador(inicio=ini, fin=fin, trabajador_id=trabajador_id) or []
        except Exception as ex:
            detalle = []
            self._snack_error(f"Error cargando detalle: {ex}")
            print(f"[CONTAB][ERR] detalle_trabajador → {ex}")

        items: List[ft.Control] = []
        if not detalle:
            items.append(ft.Text("Sin cortes en el rango.", color=pal.get("MUTED")))
        else:
            for d in detalle:
                fh = d.get("fecha_hora")
                fh_txt = str(fh)[:16] if fh else ""
                total = _dec(d.get("total"))
                emp = _dec(d.get("gan_empleado"))
                suc = _dec(d.get("gan_empresa"))
                pct = _dec(d.get("pct") if d.get("pct") is not None else "0.00")
                items.append(
                    ft.Row(
                        [
                            ft.Text(fh_txt, size=11, color=pal.get("FG_COLOR")),
                            ft.Container(expand=True),
                            ft.Text(_money(total), size=11, color=pal.get("FG_COLOR")),
                            ft.Text(f" pct: {pct:.2f}%", size=11, color=pal.get("MUTED")),
                            ft.Text(" emp: " + _money(emp), size=11, color=pal.get("FG_COLOR")),
                            ft.Text(" neg: " + _money(suc), size=11, color=pal.get("FG_COLOR")),
                        ],
                        alignment=ft.MainAxisAlignment.START, spacing=10,
                    )
                )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Detalle de cortes", weight="bold", color=pal.get("FG_COLOR")),
            content=ft.Container(
                content=ft.Column(items, spacing=6, scroll=ft.ScrollMode.AUTO, height=360),
                width=560,
            ),
            actions=[ft.TextButton("Cerrar", on_click=lambda e: self._close_dialog(e))],
        )
        self.page.dialog = dlg
        dlg.open = True
        self._safe_update()

    # ------------------------- ciclo de vida / utils
    def did_mount(self):
        # Relee la paleta desde AppState cada vez que se monta
        self.colors = self.app.get_colors("contabilidad")
        self.bgcolor = self.colors.get("BG_COLOR")
        print("[CONTAB] did_mount → paleta reaplicada")
        self._safe_update()

    def _close_dialog(self, e):
        if self.page and self.page.dialog:
            self.page.dialog.open = False
            self._safe_update()

    def _dismiss_dialog(self):
        if self.page and self.page.dialog:
            self.page.dialog.open = False
            self.page.dialog = None

    def _safe_update(self):
        try:
            if self.page:
                self.page.update()
            else:
                self.update()
        except Exception:
            pass

    def _snack_ok(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(msg, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            bgcolor=self.colors.get("CARD_BG"),
        )
        self.page.snack_bar.open = True

    def _snack_error(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(msg, color=ft.colors.WHITE),
            bgcolor=ft.colors.RED_700,
        )
        self.page.snack_bar.open = True
