# app/views/containers/nvar/user_icon_area.py
import flet as ft

class UserIconArea(ft.Container):
    def __init__(
        self,
        is_root: bool = False,
        accent: str = ft.colors.RED,  # valor por defecto
        nav_width: int = 72,                    # ancho por defecto (colapsado)
        expanded: bool = False,
        height: int = 64
    ):
        super().__init__(
            width=nav_width,
            height=height,
            bgcolor=accent,
            border_radius=8,
            alignment=ft.alignment.center,
        )

        self.is_root = is_root
        self.expanded = expanded
        self.accent = accent
        self.nav_width = nav_width
        self.height = height

        self._build()

    def _build(self):
        """Construye el contenido dinámicamente según expanded."""
        avatar_src = "assets/logos/root.png" if self.is_root else "assets/logos/user.png"

        avatar = ft.Image(
            src=avatar_src,
            width=32,
            height=32,
            fit=ft.ImageFit.COVER,
        )

        if self.expanded:
            self.content = ft.Row(
                controls=[
                    avatar,
                    ft.Text(
                        "Administrador" if self.is_root else "Usuario",
                        size=14,
                        weight="bold",
                        color=ft.colors.BLACK,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            )
        else:
            self.content = avatar
