# app/views/containers/nvar/control_buttons_area.py

import flet as ft


class ControlButtonsArea(ft.Column):
    """
    Controles globales anclados abajo:
      - Expandir/Contraer
      - Cambiar tema
      - Salir
    """
    def __init__(
        self,
        expanded: bool,
        dark: bool,
        on_toggle_nav,
        on_toggle_theme,
        on_settings,      # reservado (compatibilidad futura)
        on_exit,
        bg: str,
        mostrar_settings: bool = True,  # reservado
        mostrar_theme: bool = True,
        spacing: int = 10,
        padding: int = 6,
    ):
        super().__init__(spacing=spacing)

        self.expanded = expanded
        self.dark = dark
        self.on_toggle_nav = on_toggle_nav
        self.on_toggle_theme = on_toggle_theme
        self.on_settings = on_settings
        self.on_exit = on_exit
        self.bg = bg
        self.mostrar_settings = mostrar_settings
        self.mostrar_theme = mostrar_theme
        self._padding = padding

        self._build()

    def _build(self):
        controls: list[ft.Control] = []

        # Expandir/Contraer
        expand_icon = (
            "assets/buttons/layout_close-button.png"
            if self.expanded else "assets/buttons/layout_open-button.png"
        )
        btn_expand = ft.GestureDetector(
            on_tap=self.on_toggle_nav,
            content=ft.Container(
                bgcolor=self.bg,
                padding=self._padding,
                border_radius=6,
                content=ft.Image(src=expand_icon, width=24, height=24),
                tooltip="Contraer" if self.expanded else "Expandir",
            ),
        )
        controls.append(btn_expand)

        # Tema (opcional)
        if self.mostrar_theme:
            theme_icon = (
                "assets/buttons/light-color-button.png"
                if self.dark else "assets/buttons/dark-color-button.png"
            )
            btn_theme = ft.GestureDetector(
                on_tap=self.on_toggle_theme,
                content=ft.Container(
                    bgcolor=self.bg,
                    padding=self._padding,
                    border_radius=6,
                    content=ft.Image(src=theme_icon, width=24, height=24),
                    tooltip="Cambiar tema",
                ),
            )
            controls.append(btn_theme)

        # (Opcional) Settings en el futuro
        # if self.mostrar_settings:
        #     controls.append(...)

        # Salir
        btn_exit = ft.GestureDetector(
            on_tap=self.on_exit,
            content=ft.Container(
                bgcolor=self.bg,
                padding=self._padding,
                border_radius=6,
                content=ft.Image(src="assets/buttons/exit-button.png", width=24, height=24),
                tooltip="Salir",
            ),
        )
        controls.append(btn_exit)

        self.controls = controls

    def update_state(self, expanded: bool | None = None, dark: bool | None = None):
        if expanded is not None:
            self.expanded = expanded
        if dark is not None:
            self.dark = dark
        self._build()
        self.update()
