from __future__ import annotations
import flet as ft
from typing import List, Dict, Any, Callable, Optional
from app.config.application.app_state import AppState


class MenuButtonsArea(ft.Column):
    """
    Área de botones de navegación principal (lateral izquierda).
    - Construye dinámicamente los botones con íconos y rutas.
    - Cada botón invoca page.go(route) en tiempo real usando AppState.
    - Soporta modo expandido / colapsado, sincronización de tema y recoloreo robusto.
    """

    def __init__(
        self,
        expanded: bool,
        dark: bool,
        bg: str,
        fg: str,
        items: List[Dict[str, Any]],
        spacing: int = 10,
        padding: int = 8,
        current_route: Optional[str] = None,
    ):
        super().__init__()
        self.expand = False
        self.spacing = spacing
        self.padding = padding
        self.alignment = ft.MainAxisAlignment.START
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.controls: List[ft.Control] = []

        self._expanded = expanded
        self._dark = dark
        self._bg = bg
        self._fg = fg
        self._current_route = (current_route or "/").rstrip("/") or "/"
        self._items = items

        print(f"[MenuButtonsArea] 🧩 Inicializando → expanded={expanded}, dark={dark}, route={self._current_route}")
        self._build_buttons()

    # ============================================================
    # Construcción de botones
    # ============================================================
    def _build_buttons(self):
        """Construye todos los botones a partir del listado de ítems."""
        self.controls.clear()

        for spec in self._items:
            route = (spec.get("route") or "").rstrip("/") or None
            label = spec.get("label", "")
            icon_src = spec.get("icon_src", "")
            tooltip = spec.get("tooltip", "")
            key = spec.get("key", "")

            # Contenido base
            row = ft.Row(
                controls=[
                    ft.Image(src=icon_src, width=26, height=26, fit=ft.ImageFit.CONTAIN),
                    ft.Text(label, visible=self._expanded, size=14),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

            btn = ft.Container(
                content=row,
                padding=ft.padding.symmetric(horizontal=8, vertical=6),
                border_radius=ft.border_radius.all(8),
                tooltip=tooltip,
                on_click=self._ensure_on_tap(spec),
            )

            # 🔐 Metadatos estables para selección
            btn.data = {"route": route, "key": key}

            # Estilo inicial según estado seleccionado
            selected = (route == self._current_route)
            self._apply_style(btn, selected)

            self.controls.append(btn)

        print(f"[MenuButtonsArea] ✅ {len(self.controls)} botones construidos correctamente.")

    # ============================================================
    # Estilos
    # ============================================================
    def _apply_style(self, ctrl: ft.Container, selected: bool) -> None:
        """
        Aplica el estilo a un botón según tema y si está seleccionado.
        """
        # Colores base desde paleta (heredados del Nav)
        base_bg = self._bg or ("#1E1E1E" if self._dark else "#F6F6F6")
        base_fg = self._fg or ("#F6F6F6" if self._dark else "#1E1E1E")

        # Colores del activo (marca)
        active_bg = "#D32F2F"
        active_fg = "#FFFFFF"

        # Contenido esperado: Row[Image, Text]
        row = ctrl.content
        txt = None
        if isinstance(row, ft.Row) and len(row.controls) >= 2 and isinstance(row.controls[1], ft.Text):
            txt = row.controls[1]

        # Mostrar/ocultar texto según expandido
        if isinstance(txt, ft.Text):
            txt.visible = self._expanded

        if selected:
            ctrl.bgcolor = active_bg
            if isinstance(txt, ft.Text):
                txt.color = active_fg
            ctrl.border = None
        else:
            ctrl.bgcolor = base_bg
            if isinstance(txt, ft.Text):
                txt.color = base_fg
            ctrl.border = None

    # ============================================================
    # Callbacks dinámicos de navegación
    # ============================================================
    def _ensure_on_tap(self, spec: Dict[str, Any]) -> Callable:
        """
        Devuelve un callback dinámico que obtiene la página activa
        desde AppState y ejecuta page.go(route) en tiempo real.
        """
        route = spec.get("route")
        if not route:
            return lambda *_: None

        def _go(_):
            try:
                page = AppState().get_page()  # ← obtiene la page actual cada vez
                if page:
                    print(f"[MenuButtonsArea] 🚀 Navegando a → {route}")
                    page.go(route)
                else:
                    print(f"[MenuButtonsArea] ⚠️ No se encontró Page activa (AppState vacío)")
            except Exception as e:
                print(f"[MenuButtonsArea] ⚠️ Error navegando a {route}: {e}")

        return _go

    # ============================================================
    # Actualización dinámica del estado visual
    # ============================================================
    def update_state(
        self,
        *,
        current_route: Optional[str] = None,
        expanded: Optional[bool] = None,
        dark: Optional[bool] = None,
        bg: Optional[str] = None,      # ← NUEVO
        fg: Optional[str] = None,      # ← NUEVO
        force: bool = False,
    ) -> None:
        new_route = (current_route or self._current_route or "/").rstrip("/") or "/"
        changed = force

        if expanded is not None and expanded != self._expanded:
            self._expanded = expanded
            changed = True
        if dark is not None and dark != self._dark:
            self._dark = dark
            changed = True

        # ← NUEVO: refrescar paleta base cuando cambie el tema
        if bg is not None and bg != self._bg:
            self._bg = bg
            changed = True
        if fg is not None and fg != self._fg:
            self._fg = fg
            changed = True

        if new_route != self._current_route:
            self._current_route = new_route
            changed = True

        if not changed:
            return

        for ctrl in self.controls:
            if not isinstance(ctrl, ft.Container):
                continue
            d = getattr(ctrl, "data", None) or {}
            spec_route = (d.get("route") or "").rstrip("/") or None
            selected = (spec_route == self._current_route)
            self._apply_style(ctrl, selected)

        print(f"[MenuButtonsArea] 🎨 Estado actualizado → expanded={self._expanded}, dark={self._dark}, route={self._current_route}")
        self.update()

    # ============================================================
    # Cambio manual de ruta (sin redibujar toda la barra)
    # ============================================================
    def set_current_route(self, route: str) -> None:
        """Sincroniza el estado visual con la ruta actual."""
        route = (route or "/").rstrip("/") or "/"
        print(f"[MenuButtonsArea] 📍 Sincronizando ruta → {route}")
        self.update_state(current_route=route)
