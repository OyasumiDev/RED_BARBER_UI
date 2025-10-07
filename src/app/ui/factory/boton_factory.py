from __future__ import annotations
import flet as ft
from typing import Callable, Optional, List


class BotonFactory:
    """
    Fábrica de botones reutilizables y consistentes para toda la app.

    - Botones de header (pill): importar, exportar, agregar
    - Acciones de fila (IconButton): aceptar, cancelar, editar, borrar

    Notas:
    - Los "pill buttons" usan GestureDetector + Container para replicar el estilo
      de encabezado con ícono/imagen + texto.
    - Las acciones de fila usan IconButton con tooltips y colores de estado.
      ⚠️ Se devuelven SIN contenedores envolventes para que el click no se bloquee.
    """

    # ===== Estilos por defecto =====
    _PILL_BG = ft.colors.SURFACE_VARIANT
    _PILL_PAD = 10
    _PILL_RADIUS = 12
    _PILL_TEXT_SIZE = 11

    _ICON_SIZE = 20
    _ICON_EDIT = (ft.icons.EDIT, ft.colors.BLUE_600)
    _ICON_DELETE = (ft.icons.DELETE_OUTLINE, ft.colors.RED_600)

    # ✅ Alineado con los que te funcionaron en el container:
    _ICON_ACCEPT = (ft.icons.CHECK, ft.colors.GREEN_600)
    _ICON_CANCEL = (ft.icons.CLOSE, ft.colors.RED_600)

    def __init__(self) -> None:
        pass

    # ==============================
    # Helpers internos
    # ==============================
    def _pill_button(
        self,
        text: str,
        on_tap: Callable[[], None],
        *,
        img_src: Optional[str] = None,
        icon_name: Optional[str] = None,
        tooltip: Optional[str] = None,
        bgcolor: Optional[str] = None,
    ) -> ft.GestureDetector:
        """
        Crea un botón tipo 'pastilla' con ícono/imagen + texto.
        Si 'img_src' no se provee, se usa 'icon_name' de Flet.
        """
        content: List[ft.Control] = []
        if img_src:
            content.append(ft.Image(src=img_src, width=20, height=20))
        elif icon_name:
            content.append(ft.Icon(name=icon_name, size=20))

        content.append(ft.Text(text, size=self._PILL_TEXT_SIZE, weight="bold"))

        return ft.GestureDetector(
            on_tap=lambda _: on_tap(),
            mouse_cursor=ft.MouseCursor.CLICK,
            content=ft.Container(
                padding=self._PILL_PAD,
                border_radius=self._PILL_RADIUS,
                bgcolor=bgcolor or self._PILL_BG,
                tooltip=tooltip,
                content=ft.Row(
                    content,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=6,
                ),
            ),
        )

    def _icon_action(
        self,
        icon_name: str,
        tooltip: str,
        color: str,
        on_click: Callable[[ft.ControlEvent], None],
        *,
        disabled: bool = False,
    ) -> ft.IconButton:
        """
        Crea un IconButton estándar para acciones de fila.
        ⚠️ Sin wrappers: úsalo directo dentro del DataCell.
        """
        return ft.IconButton(
            icon=icon_name,
            icon_size=self._ICON_SIZE,
            icon_color=color,
            tooltip=tooltip,
            on_click=on_click,
            disabled=disabled,
        )

    # ==============================
    # Acciones de fila (IconButton)
    # ==============================
    def crear_boton_aceptar(
        self,
        on_click: Callable[[ft.ControlEvent], None],
        *,
        disabled: bool = False,
    ) -> ft.IconButton:
        icon, color = self._ICON_ACCEPT
        return self._icon_action(icon, "Aceptar", color, on_click, disabled=disabled)

    def crear_boton_cancelar(
        self,
        on_click: Callable[[ft.ControlEvent], None],
        *,
        disabled: bool = False,
    ) -> ft.IconButton:
        icon, color = self._ICON_CANCEL
        return self._icon_action(icon, "Cancelar", color, on_click, disabled=disabled)

    def crear_boton_editar(
        self,
        on_click: Callable[[ft.ControlEvent], None],
        *,
        disabled: bool = False,
    ) -> ft.IconButton:
        icon, color = self._ICON_EDIT
        return self._icon_action(icon, "Editar", color, on_click, disabled=disabled)

    def crear_boton_borrar(
        self,
        on_click: Callable[[ft.ControlEvent], None],
        *,
        disabled: bool = False,
    ) -> ft.IconButton:
        icon, color = self._ICON_DELETE
        return self._icon_action(icon, "Borrar", color, on_click, disabled=disabled)

    # ==============================
    # Botones de header (Pills)
    # ==============================
    def crear_boton_importar(
        self,
        on_tap: Callable[[], None],
        *,
        img_src: Optional[str] = "assets/buttons/import-button.png",
        tooltip: str = "Importar datos",
    ) -> ft.GestureDetector:
        return self._pill_button("Importar", on_tap, img_src=img_src, tooltip=tooltip)

    def crear_boton_exportar(
        self,
        on_tap: Callable[[], None],
        *,
        img_src: Optional[str] = "assets/buttons/export-button.png",
        tooltip: str = "Exportar datos",
    ) -> ft.GestureDetector:
        return self._pill_button("Exportar", on_tap, img_src=img_src, tooltip=tooltip)

    def crear_boton_agregar(
        self,
        on_tap: Callable[[], None],
        *,
        tooltip: str = "Agregar registro",
    ) -> ft.GestureDetector:
        return self._pill_button("Agregar", on_tap, icon_name=ft.icons.ADD, tooltip=tooltip)


# ==============================
#  Helpers de módulo (singleton)
# ==============================
_factory = BotonFactory()

# Pills
def boton_importar(on_tap: Callable[[], None], img_src: Optional[str] = "assets/buttons/import-button.png"):
    return _factory.crear_boton_importar(on_tap, img_src=img_src)

def boton_exportar(on_tap: Callable[[], None], img_src: Optional[str] = "assets/buttons/export-button.png"):
    return _factory.crear_boton_exportar(on_tap, img_src=img_src)

def boton_agregar(on_tap: Callable[[], None]):
    return _factory.crear_boton_agregar(on_tap)

# Icon actions
def boton_aceptar(on_click: Callable[[ft.ControlEvent], None], disabled: bool = False):
    return _factory.crear_boton_aceptar(on_click, disabled=disabled)

def boton_cancelar(on_click: Callable[[ft.ControlEvent], None], disabled: bool = False):
    return _factory.crear_boton_cancelar(on_click, disabled=disabled)

def boton_editar(on_click: Callable[[ft.ControlEvent], None], disabled: bool = False):
    return _factory.crear_boton_editar(on_click, disabled=disabled)

def boton_borrar(on_click: Callable[[ft.ControlEvent], None], disabled: bool = False):
    return _factory.crear_boton_borrar(on_click, disabled=disabled)
