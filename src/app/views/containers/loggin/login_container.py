# app/views/containers/loggin/login_container.py
from __future__ import annotations

import traceback
import flet as ft
from app.models.usuarios_model import UsuariosModel
from app.core.enums.e_usuarios import E_USUARIOS, E_USER_ESTADO
from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController


class LoginContainer(ft.Container):
    """
    Pantalla de inicio de sesión.
    - Aplica paletas desde ThemeController/PaletteFactory (área "login" + global).
    - Tras autenticar, redirige según rol (default: /trabajadores).
    """

    def __init__(self):
        # ⚠️ No uses atributo `theme` en controles Flet; usa ThemeController.
        self.theme_ctrl: ThemeController = ThemeController()
        super().__init__(expand=True, alignment=ft.alignment.center)
        self.page: ft.Page | None = None

        self.user_model = UsuariosModel()

        # Assets
        self._logo_light_src = "logos/red.png"
        self._logo_dark_src = "logos/red.png"
        self.logo = ft.Image(src=self._logo_light_src, width=250, height=250)

        # Campos
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

        # Feedback
        self.login_message = ft.Text(size=14, selectable=False)
        self.progress = ft.ProgressBar(width=300, visible=False)

        # Botón
        self.login_button = ft.ElevatedButton(
            "Iniciar sesión",
            on_click=self.on_login,
            width=300,
            height=45,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        )

        # Card
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
                    self.progress,
                    self.login_button,
                    self.login_message,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=16,
            ),
        )

        # Layout raíz
        self.content = ft.Column(
            [ft.Row([self.card], alignment=ft.MainAxisAlignment.CENTER)],
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

        # ⛔️ No llamamos self._apply_theme() aquí para evitar "Control must be added to the page first".
        # El tema se aplica en did_mount().

    # ===================== THEME =====================
    def _is_dark(self) -> bool:
        try:
            return bool(self.theme_ctrl.is_dark())
        except Exception:
            return False

    def _apply_theme(self):
        """Aplica colores a la vista. No hace self.update() si aún no hay page."""
        pal = self.theme_ctrl.get_colors("login")
        global_pal = self.theme_ctrl.get_colors()

        # Fondo
        self.bgcolor = pal.get("BG_COLOR", ft.colors.GREY_50)
        self.card.bgcolor = pal.get("CARD_BG", ft.colors.WHITE)
        self.card.shadow = ft.BoxShadow(
            blur_radius=12,
            color=global_pal.get("SHADOW", ft.colors.with_opacity(0.18, ft.colors.BLACK)),
            offset=ft.Offset(0, 4),
            spread_radius=1,
        )

        # Textos
        try:
            title: ft.Text = self.card.content.controls[1]
            title.color = global_pal.get("FG_COLOR", ft.colors.BLACK)
        except Exception as e:
            print(f"[ERROR] _apply_theme: fallo al ajustar título: {e}")
            traceback.print_exc()

        border_color = global_pal.get("BORDER_COLOR", ft.colors.OUTLINE)
        fill_color = global_pal.get("FIELD_BG", ft.colors.with_opacity(0.02, ft.colors.BLACK))
        text_color = global_pal.get("FG_COLOR", ft.colors.ON_SURFACE)
        text_muted = global_pal.get("MUTED", ft.colors.GREY_600)

        for tf in (self.user_field, self.password_field):
            try:
                tf.color = text_color
                tf.label_style = ft.TextStyle(color=text_muted)
                tf.border_color = border_color
                tf.bgcolor = fill_color
            except Exception as e:
                print(f"[ERROR] _apply_theme: fallo al aplicar estilo a TextField: {e}")
                traceback.print_exc()

        primary = global_pal.get("PRIMARY", ft.colors.RED_500)
        on_primary = global_pal.get("ON_PRIMARY", ft.colors.WHITE)
        try:
            self.login_button.bgcolor = primary
            self.login_button.color = on_primary
        except Exception as e:
            print(f"[ERROR] _apply_theme: fallo al aplicar estilo a login_button: {e}")
            traceback.print_exc()

        try:
            self.login_message.color = global_pal.get("ERROR", ft.colors.RED_400)
        except Exception:
            pass

        self.logo.src = self._logo_dark_src if self._is_dark() else self._logo_light_src

        # Actualiza solo si ya hay page (control montado)
        if self.page:
            try:
                self.page.update()
            except Exception as e2:
                print(f"[WARN] _apply_theme: page.update() falló: {e2}")
                traceback.print_exc()

    def did_mount(self):
        """Ahora sí, ya estamos en el árbol de la Page; aplica tema y suscribe listener."""
        try:
            self.page = AppState().page
            if not self.page:
                print("[WARN] did_mount: AppState().page es None")
            AppState().on_theme_change(self._apply_theme)
            self._apply_theme()
            if self.page:
                self.page.update()
        except Exception as e:
            print(f"[ERROR] did_mount: excepción: {e}")
            traceback.print_exc()

    def will_unmount(self):
        try:
            AppState().off_theme_change(self._apply_theme)
        except Exception as e:
            print(f"[ERROR] will_unmount: fallo al remover listener de tema: {e}")
            traceback.print_exc()

    # ===================== UX helpers =====================
    def _set_loading(self, state: bool):
        self.progress.visible = state
        self.user_field.disabled = state
        self.password_field.disabled = state
        self.login_button.disabled = state
        if self.page:
            try:
                self.page.update()
            except Exception as e:
                print(f"[WARN] _set_loading: page.update() falló: {e}")
                traceback.print_exc()

    def _show_error(self, msg: str):
        self.login_message.value = msg
        if self.page:
            try:
                self.page.snack_bar = ft.SnackBar(ft.Text(msg))
                self.page.snack_bar.open = True
                self.page.update()
            except Exception as e:
                print(f"[ERROR] _show_error: fallo mostrar snack_bar: {e}")
                traceback.print_exc()

    # ===================== Post-login routing =====================
    def _route_after_login(self, user: dict) -> str:
        """
        Devuelve la ruta destino según el rol.
        Por defecto, /trabajadores (tal como solicitaste).
        """
        rol = (
            user.get("rol")
            or user.get("ROL")
            or user.get(getattr(E_USUARIOS, "ROL", object()).value, None)
            or ""
        )
        rol = str(rol).strip().lower()

        if rol in ("inventarista", "inventario", "almacenista"):
            return "/inventario"
        if rol in ("root", "admin", "dueño", "dueno", "gerente", "cajero"):
            return "/home"
        # recepcionista, barbero u otros
        return "/trabajadores"

    # ===================== AUTH =====================
    def on_login(self, e: ft.ControlEvent):
        app_state = AppState()
        page: ft.Page | None = app_state.page

        username = (self.user_field.value or "").strip()
        password = (self.password_field.value or "").strip()

        if not username or not password:
            self.login_message.value = "Ingrese usuario y contraseña."
            if page:
                try:
                    page.update()
                except Exception as ex:
                    print(f"[WARN] on_login: page.update() falló al requerir campos: {ex}")
                    traceback.print_exc()
            else:
                print("[WARN] on_login: no hay page en AppState() al validar campos")
            return

        self._set_loading(True)
        try:
            print(f"[DEBUG] on_login: intentando autenticar usuario={username!r}")
            user = self.user_model.autenticar(username, password)
            print(f"[DEBUG] on_login: resultado autenticar -> {bool(user)}")

            if not user:
                existing = self.user_model.get_by_username(username)
                if existing and existing.get(E_USUARIOS.ESTADO_USR.value) == E_USER_ESTADO.INACTIVO.value:
                    self._show_error("Usuario inactivo. Contacte al administrador.")
                else:
                    self._show_error("Usuario o contraseña incorrectos.")
                return

            session_user = {
                E_USUARIOS.ID.value: user.get(E_USUARIOS.ID.value),
                E_USUARIOS.USERNAME.value: user.get(E_USUARIOS.USERNAME.value),
                E_USUARIOS.ROL.value: user.get(E_USUARIOS.ROL.value),
                E_USUARIOS.ESTADO_USR.value: user.get(E_USUARIOS.ESTADO_USR.value),
                "capabilities": user.get("capabilities", {}),
                "nombre_completo": user.get("nombre_completo") or user.get("USERNAME") or username,
            }
            print(f"[DEBUG] on_login: session_user -> {session_user}")

            if not page:
                print("[WARN] on_login: Page no disponible al intentar persistir app.user (se guardará solo en memoria)")

            app_state.set_client_value("app.user", session_user)

            # Redirección según rol (default: /trabajadores)
            dest = self._route_after_login(session_user)
            print(f"[DEBUG] on_login: redirigiendo a {dest!r}")
            if page:
                try:
                    page.go(dest)
                except Exception as ex:
                    print(f"[ERROR] on_login: page.go({dest}) falló: {ex}")
                    traceback.print_exc()
            else:
                print("[ERROR] on_login: AppState().page es None, no se puede page.go()")

        except Exception as ex:
            print(f"[ERROR] on_login: excepción inesperada: {ex}")
            traceback.print_exc()
            self._show_error(f"Error inesperado: {ex}")
        finally:
            self._set_loading(False)
            # Reaplicar tema por si cambió el modo mientras se autenticaba
            try:
                self._apply_theme()
            except Exception as ex:
                print(f"[ERROR] on_login: fallo _apply_theme en finally: {ex}")
                traceback.print_exc()
            if page:
                try:
                    page.update()
                except Exception as ex:
                    print(f"[WARN] on_login: page.update() en finally falló: {ex}")
                    traceback.print_exc()
