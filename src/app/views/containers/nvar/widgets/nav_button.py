# app/views/containers/nvar/widgets/nav_button.py
from __future__ import annotations
import flet as ft
from typing import Optional, Callable, Dict


class NavButton(ft.UserControl):
    """
    Botón de navegación unificado (menú y control):
    - Soporta icono por imagen (icon_src) o Icon (icon_name).
    - Muestra/oculta etiqueta según 'expanded'.
    - Usa paleta del área (BG_COLOR, BTN_BG, ITEM_BG, ITEM_FG, HOVER_BG,
      ACTIVE_BG, ACTIVE_FG, FG_COLOR).
    - Estados: hover / pressed / selected.
    """

    def __init__(
        self,
        *,
        icon_src: Optional[str] = None,
        icon_name: Optional[str] = None,
        label: Optional[str] = None,
        tooltip: str = "",
        on_click: Optional[Callable] = None,
        pal: Optional[Dict[str, str]] = None,
        expanded: bool = True,
        selected: bool = False,
        height: int = 40,
        radius: int = 8,
        padding: int = 8,
        show_label_when_expanded: bool = True,
    ):
        super().__init__()
        self.icon_src = icon_src
        self.icon_name = icon_name
        self.label_text = label or ""
        self.tooltip = tooltip
        self.on_click = on_click
        self.pal = pal or {}
        self.expanded = expanded
        self.selected = selected
        self.height = height
        self.radius = radius
        self.padding = padding
        self.show_label_when_expanded = show_label_when_expanded

        # runtime
        self._container: Optional[ft.Container] = None
        self._lbl: Optional[ft.Text] = None
        self._icon_ctl: Optional[ft.Control] = None
        self._hovered = False
        self._pressed = False

    # ---------- build ----------
    def build(self):
        # icon
        if self.icon_src:
            self._icon_ctl = ft.Image(src=self.icon_src, width=22, height=22)
        elif self.icon_name:
            self._icon_ctl = ft.Icon(self.icon_name, size=20)
        else:
            self._icon_ctl = ft.Container(width=22, height=22)

        # text
        self._lbl = ft.Text(self.label_text, size=13, weight=ft.FontWeight.W_500, no_wrap=True)

        row_children = [self._icon_ctl]
        if self.show_label_when_expanded:
            row_children += [ft.Container(width=10), self._lbl]

        row = ft.Row(
            controls=row_children,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        self._container = ft.Container(
            content=row,
            padding=self.padding,
            border_radius=self.radius,
            height=self.height,
            bgcolor=self._bg_for_state(),
            tooltip=self.tooltip,
        )

        return ft.GestureDetector(
            content=self._container,
            on_tap=self._on_tap,
            on_hover=self._on_hover,
            on_tap_down=self._on_tap_down,
            on_tap_up=self._on_tap_up,
        )

    # ---------- helpers ----------
    def _color(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.pal.get(key, default)

    def _bg_for_state(self) -> Optional[str]:
        if self.selected:
            return self._color("ACTIVE_BG", self._color("BTN_BG", self._color("ITEM_BG", self._color("BG_COLOR"))))
        if self._pressed:
            return self._color("ACTIVE_BG", self._color("HOVER_BG"))
        if self._hovered:
            return self._color("HOVER_BG", self._color("BTN_BG", self._color("ITEM_BG")))
        return self._color("BTN_BG", self._color("ITEM_BG", self._color("BG_COLOR")))

    def _fg_for_state(self) -> Optional[str]:
        if self.selected:
            return self._color("ACTIVE_FG", self._color("ITEM_FG", self._color("FG_COLOR")))
        return self._color("ITEM_FG", self._color("FG_COLOR"))

    def _apply_palette_now(self):
        if not self._container:
            return
        self._container.bgcolor = self._bg_for_state()
        fg = self._fg_for_state()
        if isinstance(self._icon_ctl, ft.Icon):
            self._icon_ctl.color = fg
        if self._lbl:
            self._lbl.color = fg

    def _apply_expanded_now(self):
        if self.show_label_when_expanded and self._lbl:
            self._lbl.visible = bool(self.expanded)

    # ---------- events ----------
    def _on_hover(self, e: ft.HoverEvent):
        self._hovered = (e.data == "true")
        if self._container:
            self._container.bgcolor = self._bg_for_state()
            self._container.update()

    def _on_tap_down(self, e: ft.TapEvent):
        self._pressed = True
        if self._container:
            self._container.bgcolor = self._bg_for_state()
            self._container.update()

    def _on_tap_up(self, e: ft.TapEvent):
        self._pressed = False
        if self._container:
            self._container.bgcolor = self._bg_for_state()
            self._container.update()

    def _on_tap(self, e):
        if callable(self.on_click):
            self.on_click(e)

    # ---------- public API ----------
    def set_selected(self, selected: bool):
        self.selected = bool(selected)
        self._apply_palette_now()
        self.update()

    def set_expanded(self, expanded: bool):
        self.expanded = bool(expanded)
        self._apply_expanded_now()
        self.update()

    def set_palette(self, pal: Dict[str, str]):
        self.pal = pal or {}
        self._apply_palette_now()
        self.update()

    def set_label(self, text: Optional[str]):
        self.label_text = text or ""
        if self._lbl:
            self._lbl.value = self.label_text
            self._apply_expanded_now()
            self.update()

    def set_icon_src(self, src: Optional[str]):
        self.icon_src = src or ""
        # si es imagen, actualiza; si era Icon, reemplaza
        if isinstance(self._icon_ctl, ft.Image):
            self._icon_ctl.src = self.icon_src
        else:
            self._icon_ctl = ft.Image(src=self.icon_src, width=22, height=22)
            if self._container and isinstance(self._container.content, ft.Row):
                self._container.content.controls[0] = self._icon_ctl
        self._apply_palette_now()
        self.update()
