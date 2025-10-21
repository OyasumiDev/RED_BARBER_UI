# modal_datetime_picker.py
from __future__ import annotations
import calendar
from datetime import date, datetime, time
from typing import Callable, Iterable, Optional, Sequence

import flet as ft

# =========================================
# Utilidades
# =========================================
_CAL = calendar.Calendar()
_DAYS = ["LU", "MA", "MI", "JU", "VI", "SA", "DO"]
_MONTHS = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}



def _normalize_dates(items: Iterable[date | str]) -> set[date]:
    out: set[date] = set()
    if not items:
        return out
    for x in items:
        if isinstance(x, date):
            out.add(x)
        elif isinstance(x, str):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    out.add(datetime.strptime(x, fmt).date())
                    break
                except Exception:
                    continue
    return out


def _daterange(d1: date, d2: date):
    cur = d1
    while cur <= d2:
        yield cur
        cur = date.fromordinal(cur.toordinal() + 1)


def _to_time_24h(h12: int, m: int, s: int, ampm: str) -> time:
    ampm = (ampm or "AM").upper()
    h12 = max(1, min(12, h12))
    m = max(0, min(59, m))
    s = max(0, min(59, s))
    if ampm == "AM":
        hh = 0 if h12 == 12 else h12
    else:
        hh = 12 if h12 == 12 else h12 + 12
    return time(hour=hh, minute=m, second=s)


# =========================================
# Selector de tiempo (sin texto, solo dropdowns)
# =========================================
class TimeSelector(ft.Container):
    """
    Selector de tiempo no-escribible: Hora/Min/Seg + AM/PM (o 24h sin AM/PM).
    - API: get_time() -> datetime.time
    - Params:
        use_24h: usa 00–23 y oculta AM/PM
        default: hora por defecto
    """
    def __init__(self, *, use_24h: bool = False, default: Optional[time] = None):
        super().__init__(padding=12, border_radius=16, bgcolor=ft.colors.SURFACE_VARIANT)
        self.use_24h = bool(use_24h)

        tnow = default or datetime.now().time()
        if self.use_24h:
            self._h = tnow.hour  # 0..23
            self._ampm = None
        else:
            self._ampm = "AM" if tnow.hour < 12 else "PM"
            h12 = tnow.hour % 12
            self._h = 12 if h12 == 0 else h12  # 1..12

        self._m = tnow.minute
        self._s = tnow.second

        def _dd(opts, value, width=80, on_change=None):
            return ft.Dropdown(
                options=[ft.dropdown.Option(x) for x in opts],
                value=value,
                width=width,
                dense=True,
                border_radius=10,
                on_change=on_change,
            )

        hours = [f"{h:02d}" for h in range(0 if self.use_24h else 1, (24 if self.use_24h else 13))]
        minutes = [f"{m:02d}" for m in range(60)]
        seconds = [f"{s:02d}" for s in range(60)]

        self.dd_h = _dd(hours, f"{self._h:02d}", on_change=lambda e: setattr(self, "_h", int(e.control.value)))
        self.dd_m = _dd(minutes, f"{self._m:02d}", on_change=lambda e: setattr(self, "_m", int(e.control.value)))
        self.dd_s = _dd(seconds, f"{self._s:02d}", on_change=lambda e: setattr(self, "_s", int(e.control.value)))
        self.dd_ampm = None if self.use_24h else _dd(["AM", "PM"], self._ampm, width=90,
                                                     on_change=lambda e: setattr(self, "_ampm", e.control.value))

        # UI
        chips = [
            ft.Column([ft.Text("Hora", size=11, color=ft.colors.PRIMARY), self.dd_h], spacing=4),
            ft.Text(":", size=14, weight=ft.FontWeight.BOLD),
            ft.Column([ft.Text("Min", size=11, color=ft.colors.PRIMARY), self.dd_m], spacing=4),
            ft.Text(":", size=14, weight=ft.FontWeight.BOLD),
            ft.Column([ft.Text("Seg", size=11, color=ft.colors.PRIMARY), self.dd_s], spacing=4),
        ]
        if self.dd_ampm:
            chips += [ft.Container(width=8), ft.Column([ft.Text("AM/PM", size=11, color=ft.colors.PRIMARY), self.dd_ampm], spacing=4)]

        self.content = ft.Row(chips, spacing=8, alignment="center")

    def get_time(self) -> time:
        if self.use_24h:
            return time(hour=int(self.dd_h.value), minute=int(self.dd_m.value), second=int(self.dd_s.value))
        return _to_time_24h(h12=int(self.dd_h.value), m=int(self.dd_m.value), s=int(self.dd_s.value),
                            ampm=self.dd_ampm.value if self.dd_ampm else "AM")


# =========================================
# Grid de calendario (autónomo)
# =========================================
class CalendarGrid(ft.UserControl):
    """
    Calendario con selección simple o por rango.
    - No depende de otros módulos.
    - Puedes pasar: enabled_dates (whitelist), blocked_dates (fechas deshabilitadas).
    - Colores: Seleccionada (verde), Bloqueada (gris), Disponible (claro).
    """
    def __init__(
        self,
        *,
        year: int,
        month: int,
        cell_size: int = 40,
        auto_range: bool = True,
        enabled_dates: Iterable[date | str] = (),
        blocked_dates: Iterable[date | str] = (),
        on_selection_change: Optional[Callable[[set[date]], None]] = None,
    ):
        super().__init__()
        self.year = year
        self.month = month
        self.cell_size = cell_size
        self.auto_range = bool(auto_range)
        self._enabled = _normalize_dates(enabled_dates)  # si está vacío -> todo habilitado
        self._blocked = _normalize_dates(blocked_dates)
        self._sel: set[date] = set()
        self._anchor: Optional[date] = None
        self.on_selection_change = on_selection_change

        self._root = ft.Column(spacing=8, expand=True)

    # API pública
    @property
    def seleccionadas(self) -> set[date]:
        return set(self._sel)

    def set_month(self, year: int, month: int):
        self.year, self.month = year, month
        self.update()

    def clear_selection(self):
        self._sel.clear()
        self._anchor = None
        if self.on_selection_change:
            self.on_selection_change(self._sel)
        self.update()

    def set_enabled_dates(self, items: Iterable[date | str]):
        self._enabled = _normalize_dates(items)
        self.clear_selection()

    def set_blocked_dates(self, items: Iterable[date | str]):
        self._blocked = _normalize_dates(items)
        self.clear_selection()

    # Render
    def build(self):
        self._root.controls.clear()
        header = ft.Row(
            [
                ft.Container(width=self.cell_size),
                ft.Text(f"{_MONTHS[self.month]} {self.year}", expand=True, text_align="center", weight=ft.FontWeight.BOLD),
                ft.Container(width=self.cell_size),
            ],
            alignment="center",
        )
        week = ft.Row([ft.Text(d, width=self.cell_size, text_align="center", color=ft.colors.PRIMARY) for d in _DAYS], alignment="center")
        self._root.controls += [header, week]

        for week_days in _CAL.monthdayscalendar(self.year, self.month):
            row = ft.Row(alignment="center", spacing=6)
            for d in week_days:
                if d == 0:
                    row.controls.append(ft.Container(width=self.cell_size, height=self.cell_size))
                    continue
                f = date(self.year, self.month, d)
                is_blocked = f in self._blocked
                is_enabled = (not self._enabled) or (f in self._enabled)
                is_selected = f in self._sel

                clickable = (not is_blocked) and is_enabled

                if is_selected:
                    bg = ft.colors.GREEN
                    fg = ft.colors.WHITE
                elif is_blocked:
                    bg = ft.colors.GREY_300
                    fg = ft.colors.BLACK45
                elif is_enabled:
                    bg = ft.colors.GREY_50
                    fg = ft.colors.BLACK
                else:
                    bg = ft.colors.GREY_100
                    fg = ft.colors.BLACK38

                box = ft.Container(
                    width=self.cell_size, height=self.cell_size,
                    bgcolor=bg, border_radius=10, alignment=ft.alignment.center, ink=True,
                    content=ft.Text(str(d), color=fg, size=13),
                    on_click=(lambda e, ff=f: self._toggle(ff)) if clickable else None,
                    tooltip="Bloqueada" if is_blocked else ("Disponible" if is_enabled else "No disponible")
                )
                row.controls.append(box)
            self._root.controls.append(row)
        return self._root

    # Interacción
    def _toggle(self, f: date):
        if f in self._blocked:
            return
        if self._enabled and f not in self._enabled:
            return

        if (not self.auto_range) or (self._anchor is None) or (f == self._anchor):
            if f in self._sel:
                self._sel.remove(f)
                if self._anchor == f:
                    self._anchor = None
            else:
                self._sel.add(f)
                self._anchor = f
        else:
            a, b = (self._anchor, f) if self._anchor < f else (f, self._anchor)
            rng = list(_daterange(a, b))
            valids = [d for d in rng if (d not in self._blocked) and ((not self._enabled) or (d in self._enabled))]
            self._sel.update(valids)
            self._anchor = f

        if self.on_selection_change:
            self.on_selection_change(self._sel)
        self.update()


# =========================================
# Modal principal: calendario + hora
# =========================================
class DateTimeModalPicker:
    """
    Modal autónomo para seleccionar fechas + hora.
    - Sin dependencias de AppState ni otros módulos.
    - Presenta:
        * Calendario con selección simple o por rango
        * Selector de hora/minuto/segundo con AM/PM o 24h
    - Retorno:
        on_confirm(list[datetime] | list[str]) según return_format
          - "datetime": retorna objetos datetime
          - "iso": 'YYYY-MM-DD HH:MM:SS'
          - "date": 'YYYY-MM-DD' (si no requieres hora)
    """
    def __init__(
        self,
        on_confirm: Callable[[Sequence[datetime] | Sequence[str]], None],
        *,
        auto_range: bool = True,
        require_time: bool = True,
        use_24h: bool = False,
        return_format: str = "datetime",
        cell_size: int = 40,
        width: int = 600,
        height: int = 640,
        title: str = "Selecciona fecha y hora",
        subtitle: str = "Elige uno o varios días válidos y define la hora.",
    ):
        self.on_confirm = on_confirm
        self.auto_range = bool(auto_range)
        self.require_time = bool(require_time)
        self.use_24h = bool(use_24h)
        self.return_format = return_format.strip().lower()
        self.width = width
        self.height = height
        self.title = title
        self.subtitle = subtitle

        now = datetime.now()
        self.year = now.year
        self.month = now.month

        # Estado externo opcional
        self._enabled: set[date] = set()
        self._blocked: set[date] = set()

        # Dialog y Page
        self._dialog = ft.AlertDialog(modal=True)
        self._page: Optional[ft.Page] = None

        # Componentes UI
        self._calendar = CalendarGrid(
            year=self.year,
            month=self.month,
            cell_size=cell_size,
            auto_range=self.auto_range,
            on_selection_change=lambda s: None,
        )
        self._time = TimeSelector(use_24h=self.use_24h)

        # Alert centrado reutilizable
        self._alert = ft.AlertDialog(modal=True)

    # -------- API pública (config) --------
    def set_month(self, year: int, month: int):
        self.year, self.month = year, month
        self._calendar.set_month(year, month)

    def set_enabled_dates(self, items: Iterable[date | str]):
        self._enabled = _normalize_dates(items)
        self._calendar.set_enabled_dates(self._enabled)

    def set_blocked_dates(self, items: Iterable[date | str]):
        self._blocked = _normalize_dates(items)
        self._calendar.set_blocked_dates(self._blocked)

    # -------- Apertura / cierre --------
    def open(self, page: ft.Page):
        """Abre el modal. Requiere la Page actual."""
        self._page = page
        self._rebuild()
        if self._dialog not in page.overlay:
            page.overlay.append(self._dialog)
        self._dialog.open = True
        page.update()

    def close(self):
        if self._page:
            self._dialog.open = False
            self._page.update()

    # -------- UI interna --------
    def _rebuild(self):
        header = ft.Row(
            [
                ft.IconButton(icon=ft.icons.CHEVRON_LEFT, on_click=lambda e: self._change_month(-1)),
                ft.Text(f"{_MONTHS[self.month]} {self.year}", expand=True, text_align="center", weight=ft.FontWeight.BOLD),
                ft.IconButton(icon=ft.icons.CHEVRON_RIGHT, on_click=lambda e: self._change_month(1)),
            ],
            alignment="center",
        )

        legend = ft.Row(
            [
                ft.Container(width=12, height=12, bgcolor=ft.colors.GREEN, border_radius=3), ft.Text("Seleccionada", size=11),
                ft.Container(width=12, height=12, bgcolor=ft.colors.GREY_50, border_radius=3), ft.Text("Disponible", size=11),
                ft.Container(width=12, height=12, bgcolor=ft.colors.GREY_300, border_radius=3), ft.Text("Bloqueada", size=11),
            ],
            spacing=12,
        )

        calendar_card = ft.Container(
            content=ft.Column(
                [
                    header,
                    ft.Row([ft.Text(d, width=self._calendar.cell_size, text_align="center", color=ft.colors.PRIMARY) for d in _DAYS],
                           alignment="center"),
                    self._calendar,
                ],
                spacing=10,
            ),
            padding=16,
            bgcolor=ft.colors.SURFACE_VARIANT,
            border_radius=16,
        )

        time_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Hora", weight=ft.FontWeight.BOLD),
                    self._time if self.require_time else ft.Text("No se requiere hora", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                    ft.Text(("Formato 24h." if self.use_24h else "Formato 12h con AM/PM."), size=11, color=ft.colors.ON_SURFACE_VARIANT),
                ],
                spacing=8,
            ),
            padding=16,
            bgcolor=ft.colors.SURFACE_VARIANT,
            border_radius=16,
        )

        body = ft.Column(
            [
                ft.Text(self.title, weight=ft.FontWeight.BOLD, size=16),
                ft.Text(self.subtitle, size=12, color=ft.colors.ON_SURFACE_VARIANT),
                calendar_card,
                time_card,
                legend,
                ft.Divider(),
                ft.Row(
                    [
                        ft.TextButton("Cancelar", on_click=lambda e: self._on_cancel()),
                        ft.ElevatedButton("Guardar", on_click=lambda e: self._on_save()),
                    ],
                    alignment="end",
                ),
            ],
            spacing=14,
            tight=True,
        )

        self._dialog.content = ft.Container(
            content=body,
            padding=20,
            width=self.width,
            height=self.height,
            bgcolor=ft.colors.SURFACE,
            border_radius=20,
        )

    # -------- Interacción --------
    def _change_month(self, delta: int):
        self.month += int(delta)
        if self.month > 12:
            self.month = 1
            self.year += 1
        elif self.month < 1:
            self.month = 12
            self.year -= 1
        self.set_month(self.year, self.month)

    def _on_cancel(self):
        self._calendar.clear_selection()
        self.close()

    def _on_save(self):
        fechas = sorted(list(self._calendar.seleccionadas))
        if not fechas:
            self._center_alert("Sin selección", "Selecciona al menos un día disponible.", kind="info")
            return

        result_dt: list[datetime] = []
        if self.require_time:
            t = self._time.get_time()
            result_dt = [datetime.combine(f, t) for f in fechas]
        else:
            result_dt = [datetime(f.year, f.month, f.day, 0, 0, 0) for f in fechas]

        if self.return_format == "iso":
            payload: Sequence[datetime] | Sequence[str] = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in result_dt]
        elif self.return_format == "date":
            payload = [dt.strftime("%Y-%m-%d") for dt in result_dt]
        else:
            payload = result_dt

        try:
            self.on_confirm(payload)
        finally:
            self._calendar.clear_selection()
            self.close()

    # -------- Alert centrado --------
    def _center_alert(self, title: str, message: str, *, kind: str = "info"):
        if not self._page:
            return
        icon = ft.Icon(ft.icons.ERROR_OUTLINE if kind == "error" else ft.icons.INFO_OUTLINE, size=26)
        content = ft.Container(
            width=520,
            bgcolor=ft.colors.SURFACE,
            padding=20,
            border_radius=16,
            content=ft.Column(
                [
                    ft.Row([icon, ft.Text(title or "Aviso", weight=ft.FontWeight.BOLD, size=16)], spacing=10),
                    ft.Text(message or ""),
                    ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._close_center_alert())], alignment="end"),
                ],
                spacing=14,
                tight=True,
            ),
        )
        self._alert.content = content
        if self._alert not in self._page.overlay:
            self._page.overlay.append(self._alert)
        self._alert.open = True
        self._page.update()

    def _close_center_alert(self):
        if self._page:
            self._alert.open = False
            self._page.update()
