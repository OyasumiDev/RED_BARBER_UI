# app/views/containers/loggin/login_container.py

import flet as ft
from app.models.usuarios_model import UsuariosModel
from app.core.enums.e_usuarios import E_USUARIOS, E_USER_ESTADO
from app.config.application.app_state import AppState


class LoginContainer(ft.Container):
    def __init__(self):
        super().__init__(
            expand=True,
            alignment=ft.alignment.center,
            bgcolor=ft.colors.GREY_50  # fondo neutro suave
        )
        self.page = None

        # Model
        self.user_model = UsuariosModel()

        # Campos de texto (texto/label siempre negros para contrastar)
        self.user_field = ft.TextField(
            label="Usuario",
            prefix_icon=ft.icons.PERSON,
            width=300,
            on_submit=self.on_login,
            color=ft.colors.BLACK,
            label_style=ft.TextStyle(color=ft.colors.BLACK),
        )

        self.password_field = ft.TextField(
            label="Contraseña",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.icons.LOCK,
            width=300,
            on_submit=self.on_login,
            color=ft.colors.BLACK,
            label_style=ft.TextStyle(color=ft.colors.BLACK),
        )

        self.login_message = ft.Text(color=ft.colors.RED_400, size=14)

        # Tarjeta visual
        card = ft.Container(
            width=400,
            padding=30,
            border_radius=15,
            bgcolor=ft.colors.WHITE,
            shadow=ft.BoxShadow(
                blur_radius=12,
                color=ft.colors.GREY_400,
                offset=ft.Offset(0, 4),
                spread_radius=1,
            ),
            content=ft.Column(
                [
                    ft.Image(src="logos/red.png", width=250, height=250),
                    ft.Text(
                        "Iniciar sesión",
                        size=22,
                        weight="bold",
                        color=ft.colors.BLACK
                    ),
                    self.user_field,
                    self.password_field,
                    ft.ElevatedButton(
                        "Iniciar sesión",
                        on_click=self.on_login,
                        bgcolor=ft.colors.RED_500,
                        color=ft.colors.WHITE,
                        width=300,
                        height=45,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=8)
                        )
                    ),
                    self.login_message,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=20,
            ),
        )

        # Centrado en pantalla
        self.content = ft.Column(
            [
                ft.Row([card], alignment=ft.MainAxisAlignment.CENTER),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

    def on_login(self, e: ft.ControlEvent):
        page: ft.Page = AppState().page

        username = (self.user_field.value or "").strip()
        password = (self.password_field.value or "").strip()

        if not username or not password:
            self.login_message.value = "Ingrese usuario y contraseña."
            page.update()
            return

        try:
            # Autenticación con hash + capabilities
            user = self.user_model.autenticar(username, password)

            if not user:
                # Si no autenticó, verificamos si existe pero está inactivo para dar mensaje más claro
                existing = self.user_model.get_by_username(username)
                if existing and existing.get(E_USUARIOS.ESTADO_USR.value) == E_USER_ESTADO.INACTIVO.value:
                    self.login_message.value = "Usuario inactivo. Contacte al administrador."
                else:
                    self.login_message.value = "Usuario o contraseña incorrectos."
                page.update()
                return

            # Guardar solo datos seguros en sesión (evitar guardar el hash)
            session_user = {
                E_USUARIOS.ID.value: user.get(E_USUARIOS.ID.value),
                E_USUARIOS.USERNAME.value: user.get(E_USUARIOS.USERNAME.value),
                E_USUARIOS.ROL.value: user.get(E_USUARIOS.ROL.value),
                E_USUARIOS.ESTADO_USR.value: user.get(E_USUARIOS.ESTADO_USR.value),
                "capabilities": user.get("capabilities", {}),
            }
            page.client_storage.set("app.user", session_user)

            # Navegación post-login
            page.go("/home")

        except Exception as ex:
            self.login_message.value = f"Error inesperado: {ex}"
        finally:
            page.update()
