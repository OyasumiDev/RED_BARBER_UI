# app/views/containers/nvar/menu_buttons_area.py
from __future__ import annotations

from typing import Callable, List, Optional, Dict, Any
import flet as ft

from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController
from app.views.containers.nvar.widgets.nav_button import NavButton


class MenuButtonsArea(ft.Column):
    """
    Menú de navegación usando NavButton.
    - Expandida: icono + etiqueta
    - Colapsada: solo icono
    - Selección por ruta actual (exacta o prefijo)
    - Paleta: ThemeController.get_colors("navbar")
    """

    def __init__(
        self,
        *,
        expanded: bool,
        dark: bool,
        # compat (no usados directamente):
        on_toggle_nav=None,
        on_toggle_theme=None,
        on_exit=None,
        bg: str,                        # solo para mantener firma; no se pasa a NavButton
        fg: Optional[str] = None,       # solo para mantener firma
        items: Optional[List[Dict[str, Any]]] = None,
        spacing: int = 10,
        padding: int = 6,
        current_route: Optional[str] = None,
    ):
        super().__init__(
            spacing=spacing,
            expand=False,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.expanded = bool(expanded)
        self.dark = bool(dark)
        self.bg = bg
        self.fg = fg or ft.colors.ON_SURFACE
        self._padding = padding
        self._items: List[Dict[str, Any]] = items or []
        self._current_route: Optional[str] = current_route

        self._mounted = False
        self._buttons: List[NavButton] = []

        self.app = AppState()
        self.page = self.app.get_page()
        self.theme = ThemeController()
        self.pal = self.theme.get_colors("navbar")

        self.app.on_theme_change(self._on_theme_change)

        self._build()

    # Ciclo de vida
    def did_mount(self):
        self._mounted = True
        self._apply_state_to_buttons()
        try:
            self.update()
        except Exception:
            pass

    def will_unmount(self):
        self._mounted = False
        try:
            self.app.off_theme_change(self._on_theme_change)
        except Exception:
            pass

    # API
    def set_items(self, items: List[Dict[str, Any]]) -> None:
        self._items = items or []
        self._build()
        if self._mounted:
            self._apply_state_to_buttons()
            self.update()

    def add_item(
        self,
        *,
        icon_src: Optional[str] = None,
        icon_name: Optional[str] = None,
        label: str = "",
        tooltip: Optional[str] = None,
        on_tap: Optional[Callable] = None,
        route: Optional[str] = None,
        selected: Optional[bool] = None,
        key: Optional[str] = None,
    ) -> None:
        self._items.append({
            "icon_src": icon_src,
            "icon_name": icon_name,
            "label": label,
            "tooltip": tooltip or label,
            "on_tap": on_tap,
            "route": route,
            "selected": selected,
            "key": key,
        })
        self._build()
        if self._mounted:
            self._apply_state_to_buttons()
            self.update()

    def update_state(
        self,
        *,
        expanded: Optional[bool] = None,
        dark: Optional[bool] = None,
        current_route: Optional[str] = None,
    ):
        if expanded is not None:
            self.expanded = bool(expanded)
        if dark is not None:
            self.dark = bool(dark)
        if current_route is not None:
            self._current_route = current_route

        if not self._mounted:
            return

        self._apply_state_to_buttons()
        try:
            self.update()
        except Exception:
            pass

    def set_current_route(self, route: Optional[str]):
        self._current_route = route
        if not self._mounted:
            return
        self._apply_state_to_buttons()
        try:
            self.update()
        except Exception:
            pass

    # Internos
    def _is_selected(self, item: Dict[str, Any]) -> bool:
        if isinstance(item.get("selected"), bool):
            return bool(item["selected"])
        it_route = (item.get("route") or "").strip().rstrip("/")
        cur_route = (self._current_route or "").strip().rstrip("/")
        return bool(it_route and cur_route and (cur_route == it_route or cur_route.startswith(it_route + "/")))

    def _on_theme_change(self):
        self.pal = self.theme.get_colors("navbar")
        if not self._mounted:
            return
        for btn in self._buttons:
            try:
                btn.set_palette(self.pal)
                btn.set_expanded(self.expanded)
            except AssertionError:
                pass
        try:
            self.update()
        except Exception:
            pass

    def _ensure_on_tap(self, spec: Dict[str, Any]) -> Callable:
        if callable(spec.get("on_tap")):
            return spec["on_tap"]
        route = spec.get("route")
        if route and self.page:
            def _go(_):
                try:
                    self.page.go(route)
                except Exception:
                    pass
            return _go
        return lambda *_: None

    def _apply_state_to_buttons(self):
        for btn, spec in zip(self._buttons, self._items):
            if not btn:
                continue
            try:
                btn.set_expanded(self.expanded)
                btn.set_selected(self._is_selected(spec))
            except AssertionError:
                pass

    def _build(self) -> None:
        self.controls.clear()
        self._buttons.clear()
        self.pal = self.theme.get_colors("navbar")

        for spec in self._items:
            btn = NavButton(
                icon_src=spec.get("icon_src"),
                icon_name=spec.get("icon_name"),
                label=spec.get("label", ""),
                tooltip=spec.get("tooltip") or spec.get("label", ""),
                on_click=self._ensure_on_tap(spec),
                pal=self.pal,                   # << usa tokens de PaletteFactory
                expanded=self.expanded,
                selected=self._is_selected(spec),
                height=40,
                radius=8,
                padding=self._padding,
                show_label_when_expanded=True,
            )
            self._buttons.append(btn)
            self.controls.append(btn)
