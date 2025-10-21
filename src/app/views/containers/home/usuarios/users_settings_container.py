from __future__ import annotations
import flet as ft
from typing import Any, Dict, List, Optional

from app.config.application.app_state import AppState
from app.config.application.theme_controller import ThemeController

from app.models.usuarios_model import UsuariosModel
from app.core.enums.e_usuarios import E_USUARIOS, E_USU_ROL, E_USER_ESTADO

from app.ui.builders.table_builder import TableBuilder
from app.ui.sorting.sort_manager import SortManager
try:
    from app.ui.scroll.table_scroll_controller import ScrollTableController
except Exception:
    ScrollTableController = None

from app.ui.factory.boton_factory import (
    boton_aceptar, boton_cancelar, boton_editar, boton_borrar
)

def _txt(v: Any) -> str:
    return "" if v is None else str(v)


class UsersSettingsContainer(ft.Container):
    """
    Administración de usuarios:
      - Filtros: rol / estado / búsqueda por username
      - Ordenamiento por encabezado
      - Alta y edición en línea (root)
      - Acciones: editar, borrar, toggle estado (root)
      - Campo de contraseña editable en la fila (root)
      - Recepcionista: solo lectura
    """

    def __init__(self):
        super().__init__(expand=True)

        # Core
        self.app_state = AppState()
        self.theme_ctrl = ThemeController()
        self.page = self.app_state.page
        self.colors = self.app_state.get_colors()

        self.model = UsuariosModel()

        # Sesión / permisos
        sess = None
        try:
            sess = self.page.client_storage.get("app.user") if self.page else None
        except Exception:
            pass
        role = (sess.get("rol") if isinstance(sess, dict) else "") or ""
        self.is_root = (role or "").lower() == E_USU_ROL.ROOT.value
        self.read_only = not self.is_root

        # Estado UI
        self._mounted = False
        self._theme_listener = None

        self.fila_editando: Optional[int] = None
        self.fila_nueva_en_proceso: bool = False

        # Filtros/orden
        self.filter_role: Optional[str] = None
        self.filter_state: Optional[str] = None
        self.filter_username: Optional[str] = None
        self.orden_actual: Dict[str, Optional[str]] = {
            E_USUARIOS.ID.value: None,
            E_USUARIOS.USERNAME.value: None,
            E_USUARIOS.ROL.value: None,
            E_USUARIOS.ESTADO_USR.value: None,
            E_USUARIOS.FECHA_CREACION.value: None,
        }

        # Refs de controles por fila
        self._edit_controls: Dict[int, Dict[str, ft.Control]] = {}

        # ---------- Contenedor tabla ----------
        self.table_container = ft.Container(
            expand=True,
            alignment=ft.alignment.top_center,
            bgcolor=self.colors.get("BG_COLOR"),
            content=ft.Column(
                controls=[],
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self.scroll_anchor = ft.Container(height=1, key="bottom-anchor")
        self.scroll_column = ft.Column(
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
            controls=[self.table_container, self.scroll_anchor],
        )

        # ---------------- Toolbar ----------------
        self.dd_roles = ft.Dropdown(
            label="Rol",
            width=180,
            options=[
                ft.dropdown.Option(E_USU_ROL.ROOT.value, "root"),
                ft.dropdown.Option(E_USU_ROL.RECEPCIONISTA.value, "recepcionista"),
            ],
            # Permite dejarlo en None para "todos" (sin opción "Todos" en el menú)
            value=self.filter_role,
            on_change=lambda e: self._aplicar_rol((e.control.value or "").strip() or None),
        )
        self.dd_roles.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        self.dd_estado = ft.Dropdown(
            label="Estado",
            width=180,
            options=[
                ft.dropdown.Option(E_USER_ESTADO.ACTIVO.value, "activo"),
                ft.dropdown.Option(E_USER_ESTADO.INACTIVO.value, "inactivo"),
            ],
            value=self.filter_state,
            on_change=lambda e: self._aplicar_estado((e.control.value or "").strip() or None),
        )
        self.dd_estado.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        self.search_input = ft.TextField(
            label="Buscar username (Enter)",
            hint_text="username...",
            width=260,
            on_submit=lambda e: self._aplicar_username(),
            on_change=self._username_on_change_auto_reset,
        )
        self._apply_textfield_palette(self.search_input)

        # Botón para limpiar TODOS los filtros (rol, estado y búsqueda)
        self.filters_clear_btn = ft.IconButton(
            icon=ft.icons.CLEAR_ALL,
            tooltip="Limpiar filtros",
            icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
            on_click=lambda e: self._limpiar_filtros(),
        )

        def _pill(icon_name, text, on_click):
            return ft.GestureDetector(
                on_tap=on_click,
                content=ft.Container(
                    padding=10,
                    border_radius=20,
                    bgcolor=self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT),
                    content=ft.Row(
                        [
                            ft.Icon(icon_name, size=18, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
                            ft.Text(text, size=12, weight="bold", color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=6,
                    ),
                ),
            )

        self.add_button = _pill(ft.icons.ADD, "Agregar", lambda e: self._insertar_fila_nueva())

        # Layout raíz: botón Agregar primero y filtros a un lado
        toolbar_controls = []
        if not self.read_only:
            toolbar_controls.append(self.add_button)
        toolbar_controls += [self.dd_roles, self.dd_estado, self.search_input, self.filters_clear_btn]


        self.content = ft.Container(
            expand=True,
            bgcolor=self.colors.get("BG_COLOR"),
            padding=20,
            content=ft.Column(
                expand=True,
                alignment=ft.MainAxisAlignment.START,
                spacing=10,
                controls=[
                    ft.Row(spacing=10, alignment=ft.MainAxisAlignment.START, controls=toolbar_controls),
                    ft.Divider(color=self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)),
                    ft.Container(
                        alignment=ft.alignment.top_center,
                        padding=ft.padding.only(top=10),
                        expand=True,
                        content=self.scroll_column,
                    ),
                ],
            ),
        )

        # ---------- TableBuilder + SortManager ----------
        self.sort_manager = SortManager()
        self.ID = E_USUARIOS.ID.value
        self.USERNAME = E_USUARIOS.USERNAME.value
        self.ROL = E_USUARIOS.ROL.value
        self.ESTADO = E_USUARIOS.ESTADO_USR.value
        self.CREADO = E_USUARIOS.FECHA_CREACION.value
        self.PASSWORD = E_USUARIOS.PASSWORD.value  # para columna condicional (root)

        columns = [
            {"key": self.ID, "title": "ID", "width": 80, "align": "center", "formatter": self._fmt_id},
            {"key": self.USERNAME, "title": "Usuario", "width": 240, "align": "start", "formatter": self._fmt_username},
            {"key": self.ROL, "title": "Rol", "width": 160, "align": "start", "formatter": self._fmt_rol},
            {"key": self.ESTADO, "title": "Estado", "width": 140, "align": "start", "formatter": self._fmt_estado},
        ]
        # Columna de contraseña SOLO para root
        if self.is_root:
            columns.insert(2, {"key": self.PASSWORD, "title": "Contraseña", "width": 220, "align": "start", "formatter": self._fmt_password})

        columns.append({"key": self.CREADO, "title": "Creado", "width": 200, "align": "start", "formatter": self._fmt_creado})

        self.table_builder = TableBuilder(
            group="usuarios",
            sort_manager=self.sort_manager,
            columns=columns,
            on_sort_change=self._on_sort_change,
            on_accept=self._on_accept_row if self.is_root else None,
            on_cancel=self._on_cancel_row if self.is_root else None,
            on_edit=self._on_edit_row if self.is_root else None,
            on_delete=self._on_delete_row if self.is_root else None,
            id_key=self.ID,
            dense_text=True,
            auto_scroll_new=True,
            actions_title="Acciones",
        )
        self.table_builder.attach_actions_builder(self._actions_builder)

        if ScrollTableController:
            try:
                self.stc = ScrollTableController()
                self.table_builder.attach_scroll_controller(self.stc)
            except Exception:
                self.stc = None
        else:
            self.stc = None

        self._refrescar_dataset()

        # Suscripción a tema
        try:
            self._theme_listener = self._on_theme_changed
            self.app_state.on_theme_change(self._theme_listener)
        except Exception:
            self._theme_listener = None

    # Ciclo de vida
    def did_mount(self):
        self._mounted = True
        self.page = self.app_state.get_page()
        self.colors = self.app_state.get_colors()
        self._recolor_ui()
        self._safe_update()

    def will_unmount(self):
        self._mounted = False
        if self._theme_listener:
            try:
                self.app_state.off_theme_change(self._theme_listener)
            except Exception:
                pass
            self._theme_listener = None

    def _safe_update(self):
        p = getattr(self, "page", None)
        if p:
            try:
                p.update()
            except AssertionError:
                pass

    # Theme
    def _apply_textfield_palette(self, tf: ft.TextField):
        tf.bgcolor = self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT))
        tf.color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.label_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf.hint_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        tf.cursor_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        tf.border_color = self.colors.get("DIVIDER_COLOR", ft.colors.OUTLINE_VARIANT)
        tf.focused_border_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)

    def _on_theme_changed(self):
        self.colors = self.app_state.get_colors()
        self._recolor_ui()
        self._refrescar_dataset()

    def _recolor_ui(self):
        self._apply_textfield_palette(self.search_input)
        # En _recolor_ui() reemplaza la línea del botón clear por esta
        self.filters_clear_btn.icon_color = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        self.dd_roles.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        self.dd_estado.text_style = ft.TextStyle(color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))
        self.bgcolor = self.colors.get("BG_COLOR")
        self.table_container.bgcolor = self.colors.get("BG_COLOR")
        if isinstance(self.content, ft.Container):
            self.content.bgcolor = self.colors.get("BG_COLOR")
        self._safe_update()

    # Filtros
    # --------- Sección de Filtros (reemplaza estas funciones) ---------
    def _aplicar_rol(self, rol: Optional[str]):
        # rol = None -> sin filtro (muestra todos)
        self.filter_role = rol if rol in (E_USU_ROL.ROOT.value, E_USU_ROL.RECEPCIONISTA.value) else None
        self._refrescar_dataset()

    def _aplicar_estado(self, estado: Optional[str]):
        # estado = None -> sin filtro (muestra todos)
        self.filter_state = estado if estado in (E_USER_ESTADO.ACTIVO.value, E_USER_ESTADO.INACTIVO.value) else None
        self._refrescar_dataset()

    def _aplicar_username(self):
        txt = (self.search_input.value or "").strip()
        self.filter_username = txt if txt else None
        self._refrescar_dataset()

    def _limpiar_filtros(self):
        # Reset de valores internos...
        self.filter_role = None
        self.filter_state = None
        self.filter_username = None
        # ...y de los controles visuales
        self.dd_roles.value = None
        self.dd_estado.value = None
        self.search_input.value = ""
        self._refrescar_dataset()

    def _username_on_change_auto_reset(self, e: ft.ControlEvent):
        if (e.control.value or "").strip() == "" and self.filter_username is not None:
            self.filter_username = None
            self._refrescar_dataset()


    # Orden por encabezado
    def _on_sort_change(self, campo: str, *_):
        prev = self.orden_actual.get(campo)
        nuevo = "desc" if prev == "asc" else "asc"
        self.orden_actual = {k: None for k in self.orden_actual}
        self.orden_actual[campo] = nuevo
        self._refrescar_dataset()

    # Dataset / Render
    def _fetch(self) -> List[Dict[str, Any]]:
        rows = self.model.listar(rol=self.filter_role, estado=self.filter_state) or []
        if self.filter_username:
            q = self.filter_username.lower()
            rows = [r for r in rows if q in str(r.get(self.USERNAME, "")).lower()]
        return rows

    def _aplicar_orden(self, datos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ordered = list(datos)
        col_activa = next((k for k, v in self.orden_actual.items() if v), None)
        if col_activa:
            asc = self.orden_actual[col_activa] == "asc"
            def keyfn(x):
                val = x.get(col_activa)
                if col_activa == self.ID:
                    try:
                        return int(val or 0)
                    except Exception:
                        return 0
                return (val or "")
            ordered.sort(key=keyfn, reverse=not asc)
        return ordered

    def _refrescar_dataset(self):
        datos = self._aplicar_orden(self._fetch())
        if not self.table_container.content.controls:
            self.table_container.content.controls.append(self.table_builder.build())
        self.table_builder.set_rows(datos)
        self._safe_update()

    # Formatters
    def _fmt_id(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        return ft.Text(_txt(value), size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

    def _fmt_username(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = self.is_root and ((self.fila_editando == rid) or bool(row.get("_is_new")))
        if not en_edicion:
            return ft.Text(_txt(value), size=12, color=fg)

        tf = ft.TextField(
            value=_txt(value),
            hint_text="username",
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
        )
        self._apply_textfield_palette(tf)

        def validar(_):
            v = (tf.value or "").strip()
            tf.border_color = None if len(v) >= 3 else ft.colors.RED
            self._safe_update()
        tf.on_change = validar

        key = rid if rid is not None else -1
        self._ensure_edit_map(key)
        self._edit_controls[key]["username"] = tf
        return tf

    def _fmt_password(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        # Por seguridad, la contraseña actual no se conoce (solo se guarda hash).
        # En edición, permitir escribir una nueva y revelar/ocultar mientras se escribe.
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = self.is_root and ((self.fila_editando == rid) or bool(row.get("_is_new")))
        if not en_edicion:
            return ft.Text("••••••", size=12, color=fg)  # solo indicador visual

        tf = ft.TextField(
            value="",
            hint_text="(dejar vacío para no cambiar)",
            password=True,
            can_reveal_password=True,
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
        )
        self._apply_textfield_palette(tf)

        key = rid if rid is not None else -1
        self._ensure_edit_map(key)
        self._edit_controls[key]["password"] = tf
        return tf

    def _fmt_rol(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = self.is_root and ((self.fila_editando == rid) or bool(row.get("_is_new")))
        if not en_edicion:
            return ft.Text(_txt(value), size=12, color=fg)

        dd = ft.Dropdown(
            value=value or E_USU_ROL.RECEPCIONISTA.value,
            options=[
                ft.dropdown.Option(E_USU_ROL.RECEPCIONISTA.value, "recepcionista"),
                ft.dropdown.Option(E_USU_ROL.ROOT.value, "root"),
            ],
            dense=True,
            width=160,
            text_style=ft.TextStyle(color=fg),
        )
        key = rid if rid is not None else -1
        self._ensure_edit_map(key)
        self._edit_controls[key]["rol"] = dd
        return dd

    def _fmt_estado(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        fg = self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)
        rid = row.get(self.ID)
        en_edicion = self.is_root and ((self.fila_editando == rid) or bool(row.get("_is_new")))
        if not en_edicion:
            return ft.Text(_txt(value), size=12, color=fg)

        dd = ft.Dropdown(
            value=value or E_USER_ESTADO.ACTIVO.value,
            options=[
                ft.dropdown.Option(E_USER_ESTADO.ACTIVO.value, "activo"),
                ft.dropdown.Option(E_USER_ESTADO.INACTIVO.value, "inactivo"),
            ],
            dense=True,
            width=140,
            text_style=ft.TextStyle(color=fg),
        )
        key = rid if rid is not None else -1
        self._ensure_edit_map(key)
        self._edit_controls[key]["estado"] = dd
        return dd

    def _fmt_creado(self, value: Any, row: Dict[str, Any]) -> ft.Control:
        return ft.Text(_txt(value), size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

    def _ensure_edit_map(self, key: int):
        if key not in self._edit_controls:
            self._edit_controls[key] = {}

    # Actions
    def _actions_builder(self, row: Dict[str, Any], is_new: bool) -> ft.Control:
        if self.read_only:
            return ft.Text("—", size=12, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE))

        rid = row.get(self.ID)
        estado = row.get(self.ESTADO, E_USER_ESTADO.ACTIVO.value)

        def _btn(icon, tooltip, on_click):
            return ft.IconButton(
                icon=icon,
                tooltip=tooltip,
                icon_color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE),
                on_click=on_click,
            )

        # NUEVA o EN EDICIÓN → aceptar / cancelar
        if is_new or self.fila_editando == rid:
            return ft.Row(
                [boton_aceptar(lambda e, r=row: self._on_accept_row(r)),
                boton_cancelar(lambda e, r=row: self._on_cancel_row(r))],
                spacing=6, alignment=ft.MainAxisAlignment.START
            )

        # NORMAL → (sin botón de "reseto" de contraseña)
        toggle_icon = ft.icons.TOGGLE_ON if estado == E_USER_ESTADO.ACTIVO.value else ft.icons.TOGGLE_OFF
        return ft.Row(
            [
                _btn(toggle_icon, "Cambiar estado", lambda e, r=row: self._toggle_estado(r)),
                boton_editar(lambda e, r=row: self._on_edit_row(r)),
                boton_borrar(lambda e, r=row: self._on_delete_row(r)),
            ],
            spacing=6, alignment=ft.MainAxisAlignment.START
        )

    # Callbacks acciones
    def _on_edit_row(self, row: Dict[str, Any]):
        if self.read_only:
            return
        self.fila_editando = row.get(self.ID)
        self._edit_controls.pop(self.fila_editando if self.fila_editando is not None else -1, None)
        self._refrescar_dataset()

    def _on_delete_row(self, row: Dict[str, Any]):
        if self.read_only:
            return
        rid = int(row.get(self.ID))
        self._confirmar_eliminar(rid)

    def _on_accept_row(self, row: Dict[str, Any]):
        if self.read_only:
            return

        is_new = bool(row.get("_is_new")) or (row.get(self.ID) in (None, "", 0))
        key = (row.get(self.ID) if not is_new else -1)
        ctrls = self._edit_controls.get(key, {})

        username_tf: ft.TextField = ctrls.get("username")  # type: ignore
        rol_dd: ft.Dropdown       = ctrls.get("rol")       # type: ignore
        est_dd: ft.Dropdown       = ctrls.get("estado")    # type: ignore
        pw_tf: ft.TextField       = ctrls.get("password")  # type: ignore

        errores = []
        un_val = (username_tf.value or "").strip() if username_tf else ""
        if len(un_val) < 3:
            if username_tf: username_tf.border_color = ft.colors.RED
            errores.append("Username inválido")

        if errores:
            self._snack_error("❌ " + " / ".join(errores))
            return

        # Construir cambios
        rol_val = (rol_dd.value if rol_dd else None)
        est_val = (est_dd.value if est_dd else None)
        pw_val = (pw_tf.value or "").strip() if pw_tf else ""

        if is_new:
            # Crear requiere password inicial
            if not pw_val:
                if pw_tf: pw_tf.border_color = ft.colors.RED
                self._snack_error("❌ La contraseña inicial es obligatoria.")
                return
            res = self.model.crear_usuario(username=un_val, password=pw_val,
                                        rol=rol_val or E_USU_ROL.RECEPCIONISTA.value,
                                        estado=est_val or E_USER_ESTADO.ACTIVO.value)
            self.fila_nueva_en_proceso = False
        else:
            rid = int(row.get(self.ID))
            res = self.model.actualizar_usuario(
                rid,
                username=un_val,
                password=(pw_val if pw_val else None),  # si vacío, no cambia
                rol=rol_val,
                estado=est_val,
            )
            self.fila_editando = None
            self._edit_controls.pop(rid, None)

        if res.get("status") == "success":
            self._snack_ok("✅ Cambios guardados.")
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ No se pudo guardar: {res.get('message')}")

    def _on_cancel_row(self, row: Dict[str, Any]):
        if self.read_only:
            return
        if row.get("_is_new") or (row.get(self.ID) in (None, "", 0)):
            self.fila_nueva_en_proceso = False
            rows = self.table_builder.get_rows()
            try:
                idx = next(i for i, r in enumerate(rows) if r is row or r.get("_is_new"))
                self.table_builder.remove_row_at(idx)
            except Exception:
                pass
            self._edit_controls.pop(-1, None)
            self._safe_update()
            return

        rid = row.get(self.ID)
        self.fila_editando = None
        self._edit_controls.pop(rid if rid is not None else -1, None)
        self._refrescar_dataset()

    # Alta / Estado / Delete
    def _insertar_fila_nueva(self, _e=None):
        if self.read_only:
            return
        if self.fila_nueva_en_proceso:
            self._snack_ok("ℹ️ Ya hay un registro nuevo en proceso.")
            return
        self.fila_nueva_en_proceso = True
        nueva = {
            self.ID: None,
            self.USERNAME: "",
            self.ROL: E_USU_ROL.RECEPCIONISTA.value,
            self.ESTADO: E_USER_ESTADO.ACTIVO.value,
            self.CREADO: "",
            "_is_new": True,
        }
        self.table_builder.add_row(nueva, auto_scroll=True)

    def _toggle_estado(self, row: Dict[str, Any]):
        if self.read_only:
            return
        rid = int(row.get(self.ID))
        estado = row.get(self.ESTADO, E_USER_ESTADO.ACTIVO.value)
        nuevo = E_USER_ESTADO.INACTIVO.value if estado == E_USER_ESTADO.ACTIVO.value else E_USER_ESTADO.ACTIVO.value
        res = self.model.cambiar_estado(rid, estado=nuevo)
        if res.get("status") == "success":
            self._snack_ok("✅ Estado actualizado.")
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ No se pudo cambiar: {res.get('message')}")

    def _confirmar_eliminar(self, rid: int):
        if self.read_only:
            return
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Eliminar usuario?"),
            content=ft.Text(f"Esta acción no se puede deshacer. ID: {rid}"),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dlg)),
                ft.ElevatedButton("Eliminar", icon=ft.icons.DELETE_OUTLINE, bgcolor=ft.colors.RED_600, color=ft.colors.WHITE,
                                on_click=lambda e: self._do_delete(e, rid, dlg)),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self._safe_update()

    def _do_delete(self, _e, rid: int, dlg: ft.AlertDialog):
        res = self.model.eliminar_usuario(int(rid))
        self.page.close(dlg)
        if res.get("status") == "success":
            self._snack_ok("✅ Usuario eliminado.")
            self._refrescar_dataset()
        else:
            self._snack_error(f"❌ No se pudo eliminar: {res.get('message')}")

    # Notificaciones
    def _snack_ok(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=self.colors.get("FG_COLOR", ft.colors.ON_SURFACE)),
            bgcolor=self.colors.get("CARD_BG", self.colors.get("BTN_BG", ft.colors.SURFACE_VARIANT)),
        )
        self.page.snack_bar.open = True
        self._safe_update()

    def _snack_error(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(ft.Text(msg, color=ft.colors.WHITE), bgcolor=ft.colors.RED_600)
        self.page.snack_bar.open = True
        self._safe_update()
