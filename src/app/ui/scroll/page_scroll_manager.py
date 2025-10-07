# app/ui/scroll/page_scroll_manager.py

from __future__ import annotations
from typing import Optional, Callable
import flet as ft


class PageScrollManager:
    """
    Gestor de scroll de PÁGINA (no tablas).
    Envolvemos tu contenido dentro de un ListView "scaffold" para tener control total:
      - Ir arriba/abajo con animación
      - Habilitar / deshabilitar scroll
      - Cambiar modo de scroll (ALWAYS, AUTO, ADAPTIVE, NEVER)
      - Suscripción a eventos de scroll de la página

    Uso típico:
      psm = PageScrollManager()
      scaffold = psm.build(content=my_root_control)   # devuelve un ListView con anchors
      page.add(scaffold)

      # acciones
      psm.to_top()
      psm.to_bottom()

      # opciones
      psm.set_mode(ft.ScrollMode.ALWAYS)
      psm.enable()  # equivalente a set_mode(ALWAYS)
      psm.disable() # equivalente a set_mode(NEVER)

      # listener
      psm.set_scroll_listener(lambda e: print("pixels:", e.pixels), interval_ms=100)
    """

    def __init__(
        self,
        *,
        animate_ms: int = 300,
        animate_curve: str = ft.AnimationCurve.DECELERATE,
        default_mode: ft.ScrollMode = ft.ScrollMode.ALWAYS,
    ) -> None:
        self._page: Optional[ft.Page] = None
        self._lv: Optional[ft.ListView] = None
        self._content: Optional[ft.Control] = None
        self._animate_ms = animate_ms
        self._animate_curve = animate_curve
        self._default_mode = default_mode

        # anchors
        self._top_anchor = ft.Container(height=1, key="__psm_top__")
        self._bottom_anchor = ft.Container(height=1, key="__psm_bottom__")

    # --------------------------------
    # Vínculo con page (opcional)
    # --------------------------------
    def bind_page(self, page: ft.Page) -> None:
        """Guarda referencia a la Page actual (opcional, útil para ajustar page.scroll)."""
        self._page = page
        try:
            self.set_mode(self._default_mode)
            if self._page:
                self._page.update()
        except Exception:
            pass

    # --------------------------------
    # Construcción del scaffold
    # --------------------------------
    def build(
        self,
        *,
        content: ft.Control,
        expand: bool = True,
        spacing: int = 0,
        padding: int = 0,
        auto_scroll: bool = False,
        page: Optional[ft.Page] = None,
    ) -> ft.ListView:
        """
        Envuelve tu contenido principal en un ListView que controla el scroll global.
        Devuelve el ListView para que lo montes en page (page.add(...) o como parte de un layout).
        """
        if page is not None:
            self.bind_page(page)

        self._content = content
        self._lv = ft.ListView(
            expand=expand,
            spacing=spacing,
            padding=padding,
            auto_scroll=auto_scroll,
            controls=[self._top_anchor, content, self._bottom_anchor],
        )
        # Aseguramos modo por defecto en page (si está enlazada)
        if self._page:
            self.set_mode(self._default_mode)

        return self._lv

    # --------------------------------
    # Control de scroll
    # --------------------------------
    def _ensure_lv(self) -> ft.ListView:
        if not self._lv:
            raise RuntimeError("PageScrollManager no está inicializado. Llama a build(...) primero.")
        return self._lv

    def to_top(self) -> None:
        lv = self._ensure_lv()
        # top anchor está en índice 0
        try:
            lv.scroll_to(
                index=0,
                duration=self._animate_ms,
                curve=self._animate_curve,
            )
        except Exception:
            pass

    def to_bottom(self) -> None:
        lv = self._ensure_lv()
        # bottom anchor está en índice len(controls)-1
        try:
            lv.scroll_to(
                index=len(lv.controls) - 1,
                duration=self._animate_ms,
                curve=self._animate_curve,
            )
        except Exception:
            pass

    # --------------------------------
    # Modo / enable / disable
    # --------------------------------
    def set_mode(self, mode: ft.ScrollMode) -> None:
        """
        Ajusta el modo de scroll de la PAGE si está enlazada,
        y del scaffold ListView (para coherencia visual).
        """
        # Ajuste en Page (si se enlazó)
        if self._page:
            try:
                self._page.scroll = mode
            except Exception:
                pass

        # Ajuste en ListView (si existe)
        if self._lv:
            try:
                # Para ListView, el 'modo' se simula:
                # - ALWAYS/ADAPTIVE/AUTO => permitir desplazamiento
                # - NEVER => no permitir (expand + sin scroll)
                # ListView no tiene 'scroll' como Column, así que
                # usamos expand & auto_scroll de forma coherente.
                if mode == ft.ScrollMode.NEVER:
                    self._lv.auto_scroll = False
                # en otros modos dejamos auto_scroll como esté configurado
                if self._lv.page:
                    self._lv.update()
            except Exception:
                pass

    def enable(self) -> None:
        """Habilita scroll general (equivalente a set_mode(ALWAYS))."""
        self.set_mode(ft.ScrollMode.ALWAYS)

    def disable(self) -> None:
        """Deshabilita scroll general (equivalente a set_mode(NEVER))."""
        self.set_mode(ft.ScrollMode.NEVER)

    # --------------------------------
    # Listeners de scroll
    # --------------------------------
    def set_scroll_listener(self, callback: Optional[Callable[[ft.OnScrollEvent], None]], *, interval_ms: int = 100) -> None:
        """
        Suscribe un listener al evento de scroll del scaffold.
        e.pixels -> posición actual
        e.max_scroll_extent -> máximo desplazable (si disponible)
        """
        lv = self._ensure_lv()
        try:
            lv.on_scroll = callback
            lv.on_scroll_interval = interval_ms
            if lv.page:
                lv.update()
        except Exception:
            pass

    # --------------------------------
    # Utilidades
    # --------------------------------
    def replace_content(self, new_content: ft.Control) -> None:
        """
        Reemplaza el contenido central por otro control, manteniendo el scaffold.
        """
        lv = self._ensure_lv()
        try:
            # Estructura: [top_anchor, content, bottom_anchor]
            lv.controls[1] = new_content
            self._content = new_content
            if lv.page:
                lv.update()
        except Exception:
            pass

    def dispose(self) -> None:
        """Limpia referencias (no quita controles ya montados en la página)."""
        self._page = None
        self._lv = None
        self._content = None
