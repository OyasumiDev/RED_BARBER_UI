import flet as ft
from typing import Callable, Optional

def mostrar_mensaje(
    page: ft.Page,
    titulo: str,
    mensaje: str,
    texto_boton: str = "Aceptar",
    on_close: Optional[Callable[[ft.ControlEvent], None]] = None
):
    """
    Muestra un diálogo modal informativo.

    Args:
        page (ft.Page): Página actual.
        titulo (str): Título del mensaje.
        mensaje (str): Contenido del mensaje.
        texto_boton (str, optional): Texto del botón de cierre.
        on_close (Callable, optional): Función a ejecutar al cerrar el diálogo.
    """

    def cerrar_dialogo(e: ft.ControlEvent):
        dlg.open = False
        page.update()
        if on_close:
            on_close(e)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(titulo),
        content=ft.Text(mensaje),
        actions=[
            ft.TextButton(texto_boton, on_click=cerrar_dialogo)
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )

    page.dialog = dlg
    dlg.open = True
    page.update()
