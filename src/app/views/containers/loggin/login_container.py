# app/views/containers/loggin/login_container.py

from __future__ import annotations

import flet as ft
from app.models.usuarios_model import UsuariosModel
from app.core.enums.e_usuarios import E_USUARIOS, E_USER_ESTADO
from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController
from app.config.application.settings_app import SettingsApp  # ⬅️ NUEVO

class LoginContainer(ft.Container):
    def __init__(self):
        self.theme: ThemeController = ThemeController()
        self._theme_token = None

        super().__init__(
            expand=True,
            alignment=ft.alignment.center,
        )
        self.page: ft.Page | None = None

        self.user_model = UsuariosModel()

        self._logo_light_src = "logos/red.png"
        self._logo_dark_src = "logos/red.png"
        self.logo = ft.Image(src=self._logo_light_src, width=250, height=250)

        self.user_field = ft.TextField(
            label="Usuario",
            prefix_icon=ft.icons.PERSON,
            width=300,
            on_submit=self.on_login,
        )
        self.password_field = ft.TextField(
            label="Contraseña",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.icons.LOCK,
            width=300,
            on_submit=self.on_login,
        )
        self.login_message = ft.Text(size=14)

        self.login_button = ft.ElevatedButton(
            "Iniciar sesión",
            on_click=self.on_login,
            width=300,
            height=45,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        )

        self.card = ft.Container(
            width=400,
            padding=30,
            border_radius=15,
            content=ft.Column(
                [
                    self.logo,
                    ft.Text("Iniciar sesión", size=22, weight="bold"),
                    self.user_field,
                    self.password_field,
                    self.login_button,
                    self.login_message,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=20,
            ),
        )

        self.content = ft.Column(
            [ft.Row([self.card], alignment=ft.MainAxisAlignment.CENTER)],
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

        # ⬅️ Boot inicial desde Settings persistido ANTES de pintar colores
        self._boot_from_settings()
        self._apply_theme()

    # ===================== THEME INTEGRATION =====================

    def _boot_from_settings(self):
        """Lee el modo desde SettingsApp y lo propaga a Page y ThemeController."""
        try:
            mode = (SettingsApp().get("theme", "light") or "light").lower()
            p = AppState().page
            if p:
                p.theme_mode = ft.ThemeMode.DARK if mode == "dark" else ft.ThemeMode.LIGHT
            # Notificar al ThemeController si expone setters
            if hasattr(self.theme, "set_mode"):
                self.theme.set_mode(mode)  # espera "dark"/"light"
            elif hasattr(self.theme, "apply"):
                self.theme.apply(mode)
            elif hasattr(self.theme, "is_dark") and not callable(getattr(self.theme, "is_dark")):
                # si es propiedad booleana
                try:
                    self.theme.is_dark = (mode == "dark")
                except Exception:
                    pass
        except Exception:
            pass

    def _c(self, key: str, default: str) -> str:
        tc = self.theme
        val = None
        try:
            if hasattr(tc, "get_color"):
                val = tc.get_colors(key)
            elif hasattr(tc, "color"):
                val = tc.color(key)
            elif hasattr(tc, "get"):
                val = tc.get(key)
            elif hasattr(tc, "palette") and isinstance(tc.palette, dict):
                val = tc.palette.get(key)
        except Exception:
            val = None
        return val or default

    def _is_dark(self) -> bool:
        # 1) Settings persistido
        try:
            mode = SettingsApp().get("theme", None)
            if isinstance(mode, str) and mode.lower() == "dark":
                return True
        except Exception:
            pass
        # 2) ThemeController / Page
        tc = self.theme
        try:
            if hasattr(tc, "is_dark") and callable(tc.is_dark):
                return bool(tc.is_dark())
            if hasattr(tc, "mode"):
                return str(tc.mode).lower() == "dark"
            if hasattr(tc, "theme_mode"):
                return str(tc.theme_mode).lower() == "dark"
        except Exception:
            pass
        try:
            p = AppState().page
            if p and p.theme and getattr(p.theme, "brightness", None):
                return str(p.theme.brightness).lower() == "dark"
        except Exception:
            pass
        return False

    def _apply_theme(self):
        self.bgcolor = self._c("background", self._c("bg", ft.colors.GREY_50))

        self.card.bgcolor = self._c("surface", self._c("card", ft.colors.WHITE))
        shadow_color = self._c("shadow_color", ft.colors.with_opacity(0.18, ft.colors.BLACK))
        self.card.shadow = ft.BoxShadow(blur_radius=12, color=shadow_color, offset=ft.Offset(0, 4), spread_radius=1)

        text_color = self._c("on_surface", self._c("text", ft.colors.BLACK))
        text_muted = self._c("on_surface_variant", self._c("text_muted", text_color))

        try:
            title_text: ft.Text = self.card.content.controls[1]
            title_text.color = text_color
        except Exception:
            pass

        border_color = self._c("outline", self._c("input_border", ft.colors.GREY_400))
        fill_color = self._c("surface_container", self._c("field_bg", ft.colors.with_opacity(0.02, ft.colors.BLACK)))

        for tf in (self.user_field, self.password_field):
            tf.color = text_color
            tf.label_style = ft.TextStyle(color=text_muted)
            tf.border_color = border_color
            tf.bgcolor = fill_color

        primary = self._c("primary", ft.colors.RED_500)
        on_primary = self._c("on_primary", ft.colors.WHITE)
        self.login_button.bgcolor = primary
        self.login_button.color = on_primary

        error_color = self._c("error", self._c("danger", ft.colors.RED_400))
        self.login_message.color = error_color

        self.logo.src = self._logo_dark_src if self._is_dark() else self._logo_light_src

        try:
            self.update()
        except Exception:
            p = getattr(self, "page", None)
            if p:
                p.update()

    def did_mount(self):
        self.page = AppState().page
        # ⬅️ Refuerza el modo nada más montar (por si __init__ no tuvo page aún)
        self._boot_from_settings()
        self._apply_theme()
        # Suscripción a cambios de tema si existe
        try:
            if hasattr(self.theme, "subscribe"):
                self._theme_token = self.theme.subscribe(lambda *_: self._apply_theme())
            elif hasattr(self.theme, "on_change"):
                self._theme_token = self.theme.on_change(lambda *_: self._apply_theme())
        except Exception:
            self._theme_token = None

    def will_unmount(self):
        try:
            if self._theme_token is not None:
                if hasattr(self.theme, "unsubscribe"):
                    self.theme.unsubscribe(self._theme_token)
                elif hasattr(self.theme, "remove_listener"):
                    self.theme.remove_listener(self._theme_token)
        except Exception:
            pass

    # ===================== AUTH =====================

    def on_login(self, e: ft.ControlEvent):
        page: ft.Page = AppState().page

        username = (self.user_field.value or "").strip()
        password = (self.password_field.value or "").strip()

        if not username or not password:
            self.login_message.value = "Ingrese usuario y contraseña."
            page.update()
            return

        try:
            user = self.user_model.autenticar(username, password)

            if not user:
                existing = self.user_model.get_by_username(username)
                if existing and existing.get(E_USUARIOS.ESTADO_USR.value) == E_USER_ESTADO.INACTIVO.value:
                    self.login_message.value = "Usuario inactivo. Contacte al administrador."
                else:
                    self.login_message.value = "Usuario o contraseña incorrectos."
                page.update()
                return

            session_user = {
                E_USUARIOS.ID.value: user.get(E_USUARIOS.ID.value),
                E_USUARIOS.USERNAME.value: user.get(E_USUARIOS.USERNAME.value),
                E_USUARIOS.ROL.value: user.get(E_USUARIOS.ROL.value),
                E_USUARIOS.ESTADO_USR.value: user.get(E_USUARIOS.ESTADO_USR.value),
                "capabilities": user.get("capabilities", {}),
            }
            page.client_storage.set("app.user", session_user)

            page.go("/home")

        except Exception as ex:
            self.login_message.value = f"Error inesperado: {ex}"
        finally:
            self._apply_theme()
            page.update()
