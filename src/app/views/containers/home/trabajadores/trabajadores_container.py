from __future__ import annotations
import flet as ft
from typing import Any, Dict, List, Optional

# Usa el AppState de tu proyecto (misma ruta que en tu contenedor previo)
from app.config.application.app_state import AppState

# Modelo y enums
from app.models.trabajadores_model import TrabajadoresModel
from app.core.enums.e_trabajadores import E_TRABAJADORES, E_TRAB_TIPO, E_TRAB_ESTADO


# ----------------------------- Helpers -----------------------------
def _txt(v: Any) -> str:
    return "" if v is None else str(v)

def _f2(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "0.00"


class TrabajadoresContainer(ft.Container):
    """
    Carga de datos al estilo EmpleadosContainer:
      - Se cargan en __init__ invocando _actualizar_tabla()
      - DataTable reconstruida explícitamente (sin TableBuilder)
      - Acciones con IconButton directos (clickeables)
      - Nuevo registro: fila editable con Aceptar/Cancelar
      - Existentes: Editar -> entra en edición; Guardar (CHECK) confirma
    """

    def __init__(self):
        super().__init__()

        # Core
        self.page = AppState().page
        self.model = TrabajadoresModel()

        # Estado de edición / nuevo
        self.fila_editando: Optional[int] = None      # guarda ID en edición
        self.fila_nueva_en_proceso: bool = False

        # Filtros/orden (similar a tu ejemplo)
        self.sort_id_filter: Optional[str] = None
        self.sort_name_filter: Optional[str] = None
        self.orden_actual = {
            E_TRABAJADORES.ID.value: None,
            E_TRABAJADORES.NOMBRE.value: None,
            E_TRABAJADORES.TIPO.value: None,
            E_TRABAJADORES.COMISION.value: None,
            E_TRABAJADORES.ESTADO.value: None,
        }

        # Tabla y scroll
        self.table: Optional[ft.DataTable] = None
        self.table_container = ft.Container(
            expand=True,
            alignment=ft.alignment.top_center,
            content=ft.Column(
                controls=[],
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self.scroll_column_ref = ft.Ref[ft.Column]()
        self.scroll_anchor = ft.Container(height=1, key="bottom-anchor")
        self.scroll_column = ft.Column(
            ref=self.scroll_column_ref,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
            controls=[self.table_container, self.scroll_anchor],
        )

        # ---- Botones header (estilo tu ejemplo con GestureDetector) ----
        self.import_button = ft.GestureDetector(
            on_tap=lambda e: self._on_importar(),
            content=ft.Container(
                padding=10,
                border_radius=20,
                bgcolor=ft.colors.SURFACE_VARIANT,
                content=ft.Row(
                    [
                        ft.Icon(name=ft.icons.FILE_DOWNLOAD_OUTLINED, size=18),
                        ft.Text("Importar", size=12, weight="bold"),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=6,
                ),
            ),
        )
        self.export_button = ft.GestureDetector(
            on_tap=lambda e: self._on_exportar(),
            content=ft.Container(
                padding=10,
                border_radius=20,
                bgcolor=ft.colors.SURFACE_VARIANT,
                content=ft.Row(
                    [
                        ft.Icon(name=ft.icons.FILE_UPLOAD_OUTLINED, size=18),
                        ft.Text("Exportar", size=12, weight="bold"),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=6,
                ),
            ),
        )
        self.add_button = ft.GestureDetector(
            on_tap=lambda e: self._insertar_fila_nueva(),
            content=ft.Container(
                padding=10,
                border_radius=20,
                bgcolor=ft.colors.SURFACE_VARIANT,
                content=ft.Row(
                    [
                        ft.Icon(name=ft.icons.ADD, size=18),
                        ft.Text("Agregar", size=12, weight="bold"),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=6,
                ),
            ),
        )

        # ---- Toolbar (filtros) ----
        self.sort_id_input = ft.TextField(
            label="Ordenar por ID",
            hint_text="Escribe un ID y presiona Enter",
            width=180,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=lambda e: self._aplicar_sort_id(),
            on_change=self._id_on_change_auto_reset,
        )
        self.sort_id_clear_btn = ft.IconButton(
            icon=ft.icons.CLEAR,
            tooltip="Limpiar ID",
            on_click=lambda e: self._limpiar_sort_id(),
        )

        self.sort_name_input = ft.TextField(
            label="Buscar por Nombre",
            hint_text="Escribe nombre y presiona Enter",
            width=260,
            on_submit=lambda e: self._aplicar_sort_nombre(),
            on_change=self._nombre_on_change_auto_reset,
        )
        self.sort_name_clear_btn = ft.IconButton(
            icon=ft.icons.CLEAR,
            tooltip="Limpiar nombre",
            on_click=lambda e: self._limpiar_sort_nombre(),
        )

        # Content raíz
        self.content = ft.Container(
            expand=True,
            padding=20,
            content=ft.Column(
                expand=True,
                alignment=ft.MainAxisAlignment.START,
                spacing=10,
                controls=[
                    ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                        controls=[self.add_button, self.import_button, self.export_button],
                    ),
                    ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                        controls=[
                            self.sort_id_input,
                            self.sort_id_clear_btn,
                            self.sort_name_input,
                            self.sort_name_clear_btn,
                        ],
                    ),
                    ft.Divider(height=1),
                    ft.Container(
                        alignment=ft.alignment.top_center,
                        padding=ft.padding.only(top=10),
                        expand=True,
                        content=self.scroll_column,
                    ),
                ],
            ),
        )

        # 👇 Cargar datos inmediatamente (como en tu ejemplo)
        self._actualizar_tabla()

    # ----------------------------- Filtros / Orden -----------------------------
    def _aplicar_sort_id(self):
        v = (self.sort_id_input.value or "").strip()
        if v and not v.isdigit():
            self._snack_error("❌ ID inválido. Usa solo números.")
            return
        self.sort_id_filter = v if v else None
        self._actualizar_tabla()

    def _limpiar_sort_id(self):
        self.sort_id_input.value = ""
        self.sort_id_filter = None
        self._actualizar_tabla()

    def _id_on_change_auto_reset(self, e: ft.ControlEvent):
        if (e.control.value or "").strip() == "" and self.sort_id_filter is not None:
            self.sort_id_filter = None
            self._actualizar_tabla()

    def _aplicar_sort_nombre(self):
        texto = (self.sort_name_input.value or "").strip()
        if not texto:
            self.sort_name_filter = None
            self._actualizar_tabla()
            return

        res = self.model.listar()
        data = res if isinstance(res, list) else res.get("data", [])
        hay = any(texto.lower() in (str(r.get(E_TRABAJADORES.NOMBRE.value, "")).lower()) for r in data)
        if not hay:
            self._snack_error("esta busqueda no esta disponible")
            return

        self.sort_name_filter = texto
        self._actualizar_tabla()

    def _limpiar_sort_nombre(self):
        self.sort_name_input.value = ""
        self.sort_name_filter = None
        self._actualizar_tabla()

    def _nombre_on_change_auto_reset(self, e: ft.ControlEvent):
        if (e.control.value or "").strip() == "" and self.sort_name_filter is not None:
            self.sort_name_filter = None
            self._actualizar_tabla()

    # ----------------------------- Orden por columna -----------------------------
    def _icono_orden(self, columna: str) -> str:
        estado = self.orden_actual.get(columna)
        if estado == "asc":
            return "▲"
        if estado == "desc":
            return "▼"
        return "⇅"

    def _ordenar_por_columna(self, columna: str):
        ascendente = self.orden_actual.get(columna) != "asc"
        # limpiar estado
        self.orden_actual = {k: None for k in self.orden_actual}
        self.orden_actual[columna] = "asc" if ascendente else "desc"

        datos_result = self.model.listar()
        datos = datos_result if isinstance(datos_result, list) else datos_result.get("data", [])
        datos = self._ordenar_lista(datos, columna=columna, asc=ascendente)
        self._refrescar_tabla(datos)

    def _ordenar_lista(self, datos: list, columna: Optional[str] = None, asc: bool = True) -> list:
        ordered = list(datos)

        # Prioridad por ID exacto
        if self.sort_id_filter:
            id_str = str(self.sort_id_filter)
            id_key = E_TRABAJADORES.ID.value
            ordered = sorted(
                ordered,
                key=lambda r: 0 if str(r.get(id_key)) == id_str else 1
            )

        # Prioridad por nombre contiene
        if self.sort_name_filter:
            texto = self.sort_name_filter.lower()
            name_key = E_TRABAJADORES.NOMBRE.value
            ordered = sorted(
                ordered,
                key=lambda r: 0 if texto in str(r.get(name_key, "")).lower() else 1
            )

        # Orden por columna (numérica o texto)
        if columna:
            keyfn = lambda x: (x.get(columna) if x.get(columna) is not None else "")
            if columna in (E_TRABAJADORES.ID.value, E_TRABAJADORES.COMISION.value):
                def keyfn(x):
                    try:
                        return float(x.get(columna) or 0)
                    except Exception:
                        return 0.0
            ordered.sort(key=keyfn, reverse=not asc)

        return ordered

    # ----------------------------- Tabla y datos -----------------------------
    def _actualizar_tabla(self, fila_en_edicion: Optional[int] = None):
        # lee
        datos_result = self.model.listar() if hasattr(self.model, "listar") else []
        datos = datos_result if isinstance(datos_result, list) else datos_result.get("data", [])

        # setea fila en edición si te lo piden
        self.fila_editando = fila_en_edicion

        # ordena según filtros actuales
        datos = self._ordenar_lista(datos)

        # pinta
        self._refrescar_tabla(datos)

    def _refrescar_tabla(self, trabajadores: list):
        self.table = self._build_table(trabajadores)
        self.table_container.content.controls.clear()
        self.table_container.content.controls.append(self.table)
        if self.page:
            self.page.update()

    # ----------------------------- Build table -----------------------------
    def _build_table(self, trabajadores: list) -> ft.DataTable:
        rows: List[ft.DataRow] = []
        ID = E_TRABAJADORES.ID.value
        NOMBRE = E_TRABAJADORES.NOMBRE.value
        TIPO = E_TRABAJADORES.TIPO.value
        COMISION = E_TRABAJADORES.COMISION.value
        ESTADO = E_TRABAJADORES.ESTADO.value

        for r in trabajadores:
            rid = r.get(ID)
            en_edicion = (self.fila_editando == rid)

            # Nombre
            if en_edicion:
                nombre_tf = self._mk_tf_nombre(_txt(r.get(NOMBRE)))
                nombre_cell = ft.DataCell(ft.Container(nombre_tf, width=300, expand=True))
            else:
                nombre_cell = ft.DataCell(ft.Container(ft.Text(_txt(r.get(NOMBRE))), width=300, expand=True))

            # Tipo
            if en_edicion:
                tipo_dd = self._mk_dd_tipo(r.get(TIPO, E_TRAB_TIPO.OCASIONAL.value))
                tipo_cell = ft.DataCell(ft.Container(tipo_dd, width=140, expand=True))
            else:
                tipo_cell = ft.DataCell(ft.Container(ft.Text(_txt(r.get(TIPO))), width=140, expand=True))

            # Comisión
            if en_edicion:
                com_tf = self._mk_tf_comision(_f2(r.get(COMISION)))
                com_cell = ft.DataCell(ft.Container(com_tf, width=120, expand=True))
            else:
                com_cell = ft.DataCell(ft.Container(ft.Text(_f2(r.get(COMISION))), width=120, expand=True))

            # Estado
            if en_edicion:
                est_dd = self._mk_dd_estado(r.get(ESTADO, E_TRAB_ESTADO.ACTIVO.value))
                est_cell = ft.DataCell(ft.Container(est_dd, width=120, expand=True))
            else:
                est_cell = ft.DataCell(ft.Container(ft.Text(_txt(r.get(ESTADO))), width=120, expand=True))

            # Acciones
            if en_edicion:
                # Guardar / Cancelar (CHECK / CLOSE)
                acciones = ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.icons.CHECK,
                            icon_color=ft.colors.GREEN_600,
                            tooltip="Guardar",
                            on_click=lambda e, _rid=rid,
                                              _nombre=nombre_cell.content.content if isinstance(nombre_cell.content.content, ft.TextField) else None,
                                              _tipo=tipo_cell.content.content if isinstance(tipo_cell.content.content, ft.Dropdown) else None,
                                              _com=com_cell.content.content if isinstance(com_cell.content.content, ft.TextField) else None,
                                              _est=est_cell.content.content if isinstance(est_cell.content.content, ft.Dropdown) else None:  # noqa
                                self._guardar_edicion(_rid, _nombre, _tipo, _com, _est)
                        ),
                        ft.IconButton(
                            icon=ft.icons.CLOSE,
                            icon_color=ft.colors.RED_600,
                            tooltip="Cancelar",
                            on_click=lambda e, _rid=rid: self._cancelar_edicion(_rid)
                        ),
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.START
                )
            else:
                # Editar / Eliminar
                acciones = ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.icons.EDIT,
                            tooltip="Editar",
                            on_click=lambda e, _rid=rid: self._activar_edicion(_rid)
                        ),
                        ft.IconButton(
                            icon=ft.icons.DELETE_OUTLINE,
                            icon_color=ft.colors.RED_600,
                            tooltip="Eliminar",
                            on_click=lambda e, _rid=rid: self._confirmar_eliminar(_rid)
                        ),
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.START
                )

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(_txt(rid))),
                        nombre_cell,
                        tipo_cell,
                        com_cell,
                        est_cell,
                        ft.DataCell(acciones),
                    ]
                )
            )

        # Encabezados con sort (como tu ejemplo)
        return ft.DataTable(
            expand=True,
            columns=[
                ft.DataColumn(
                    ft.Container(
                        ft.Text(f"Nómina {self._icono_orden(E_TRABAJADORES.ID.value)}", size=12, weight="bold"),
                        width=100,
                        alignment=ft.alignment.center,
                    ),
                    on_sort=lambda _: self._ordenar_por_columna(E_TRABAJADORES.ID.value),
                ),
                ft.DataColumn(
                    ft.Container(ft.Text("Nombre", size=12, weight="bold"), width=300)
                ),
                ft.DataColumn(
                    ft.Container(ft.Text("Tipo", size=12, weight="bold"), width=140)
                ),
                ft.DataColumn(
                    ft.Container(ft.Text(f"Comisión % {self._icono_orden(E_TRABAJADORES.COMISION.value)}", size=12, weight="bold"), width=120),
                    on_sort=lambda _: self._ordenar_por_columna(E_TRABAJADORES.COMISION.value),
                ),
                ft.DataColumn(
                    ft.Container(ft.Text("Estado", size=12, weight="bold"), width=120)
                ),
                ft.DataColumn(
                    ft.Container(ft.Text("Editar - Eliminar", size=12, weight="bold"), width=160)
                ),
            ],
            rows=rows,
        )

    # ----------------------------- Inputs celdas -----------------------------
    def _mk_tf_nombre(self, val: str) -> ft.TextField:
        tf = ft.TextField(
            value=val,
            expand=True,
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
        )

        def validar(_):
            ok = len(tf.value.strip()) >= 3 and all(c.isalpha() or c.isspace() for c in tf.value.strip())
            tf.border_color = None if ok else ft.colors.RED
            self.page.update()

        tf.on_change = validar
        return tf

    def _mk_tf_comision(self, val: str) -> ft.TextField:
        tf = ft.TextField(
            value=str(val),
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
        )

        def validar(_):
            try:
                v = float(tf.value)
                tf.border_color = None if v >= 0 else ft.colors.RED
            except Exception:
                tf.border_color = ft.colors.RED
            self.page.update()

        tf.on_change = validar
        return tf

    def _mk_dd_tipo(self, value: str) -> ft.Dropdown:
        return ft.Dropdown(
            value=value or E_TRAB_TIPO.OCASIONAL.value,
            options=[
                ft.dropdown.Option(E_TRAB_TIPO.OCASIONAL.value, "ocasional"),
                ft.dropdown.Option(E_TRAB_TIPO.PLANTA.value, "planta"),
                ft.dropdown.Option(E_TRAB_TIPO.DUENO.value, "dueno"),
            ],
            width=140,
            dense=True,
        )

    def _mk_dd_estado(self, value: str) -> ft.Dropdown:
        return ft.Dropdown(
            value=value or E_TRAB_ESTADO.ACTIVO.value,
            options=[
                ft.dropdown.Option(E_TRAB_ESTADO.ACTIVO.value, "activo"),
                ft.dropdown.Option(E_TRAB_ESTADO.INACTIVO.value, "inactivo"),
            ],
            width=120,
            dense=True,
        )

    # ----------------------------- Acciones fila existente -----------------------------
    def _activar_edicion(self, rid: int):
        self._actualizar_tabla(fila_en_edicion=rid)

    def _cancelar_edicion(self, rid: int):
        self.fila_editando = None
        self._actualizar_tabla()

    def _guardar_edicion(self, rid: int, tf_nombre: ft.TextField, dd_tipo: ft.Dropdown,
                         tf_com: ft.TextField, dd_estado: ft.Dropdown):
        errores: List[str] = []

        nombre_val = (tf_nombre.value or "").strip()
        if len(nombre_val) < 3 or not all(c.isalpha() or c.isspace() for c in nombre_val):
            tf_nombre.border_color = ft.colors.RED
            errores.append("Nombre inválido")

        try:
            com_val = float(tf_com.value)
            if com_val < 0:
                raise ValueError
            tf_com.border_color = None
        except Exception:
            tf_com.border_color = ft.colors.RED
            errores.append("Comisión inválida")

        self.page.update()

        if errores:
            self._snack_error("❌ " + " / ".join(errores))
            return

        res = self.model.actualizar_trabajador(
            trabajador_id=rid,
            nombre=nombre_val,
            tipo=dd_tipo.value or E_TRAB_TIPO.OCASIONAL.value,
            comision_porcentaje=com_val,
            estado=dd_estado.value or E_TRAB_ESTADO.ACTIVO.value,
        )
        self.fila_editando = None
        if res.get("status") == "success":
            self._actualizar_tabla()
            self._snack_ok("✅ Cambios guardados correctamente.")
        else:
            self._snack_error(f"❌ No se pudo guardar: {res.get('message')}")

    def _confirmar_eliminar(self, rid: int):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Eliminar trabajador?"),
            content=ft.Text(f"Esta acción no se puede deshacer. ID: {rid}"),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dlg)),
                ft.ElevatedButton(
                    "Eliminar",
                    icon=ft.icons.DELETE_OUTLINE,
                    bgcolor=ft.colors.RED_600,
                    color=ft.colors.WHITE,
                    on_click=lambda e: self._do_delete(e, rid, dlg),
                ),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def _do_delete(self, _e, rid: int, dlg: ft.AlertDialog):
        res = self.model.eliminar_trabajador(int(rid))
        self.page.close(dlg)
        if res.get("status") == "success":
            self._snack_ok("✅ Trabajador eliminado.")
            self._actualizar_tabla()
        else:
            self._snack_error(f"❌ No se pudo eliminar: {res.get('message')}")

    # ----------------------------- Fila NUEVA -----------------------------
    def _insertar_fila_nueva(self, _e=None):
        if self.fila_nueva_en_proceso:
            self._snack_ok("ℹ️ Ya hay un registro nuevo en proceso.")
            return

        self.fila_nueva_en_proceso = True

        # Inputs
        nombre_input = ft.TextField(hint_text="Nombre completo", expand=True, text_size=12,
                                    content_padding=ft.padding.symmetric(horizontal=8, vertical=6))
        tipo_input = self._mk_dd_tipo(E_TRAB_TIPO.OCASIONAL.value)
        com_input = ft.TextField(hint_text="Comisión %", keyboard_type=ft.KeyboardType.NUMBER, expand=True, text_size=12,
                                 content_padding=ft.padding.symmetric(horizontal=8, vertical=6))
        estado_input = self._mk_dd_estado(E_TRAB_ESTADO.ACTIVO.value)

        def validar_nombre(_):
            val = nombre_input.value.strip()
            nombre_input.border_color = None if len(val) >= 3 and all(c.isalpha() or c.isspace() for c in val) else ft.colors.RED
            self.page.update()

        def validar_comision(_):
            try:
                v = float(com_input.value)
                com_input.border_color = None if v >= 0 else ft.colors.RED
            except Exception:
                com_input.border_color = ft.colors.RED
            self.page.update()

        nombre_input.on_change = validar_nombre
        com_input.on_change = validar_comision

        def on_guardar(_):
            errores = []

            val_nombre = (nombre_input.value or "").strip()
            if len(val_nombre) < 3 or not all(c.isalpha() or c.isspace() for c in val_nombre):
                nombre_input.border_color = ft.colors.RED
                errores.append("Nombre inválido (mín. 3 letras)")

            try:
                val_com = float(com_input.value)
                if val_com < 0:
                    raise ValueError
            except Exception:
                com_input.border_color = ft.colors.RED
                errores.append("Comisión inválida (número positivo)")

            self.page.update()

            if errores:
                self._snack_error("❌ " + " / ".join(errores))
                return

            res = self.model.crear_trabajador(
                nombre=val_nombre,
                tipo=tipo_input.value or E_TRAB_TIPO.OCASIONAL.value,
                comision_porcentaje=float(com_input.value),
                telefono=None,
                email=None,
                estado=estado_input.value or E_TRAB_ESTADO.ACTIVO.value,
            )
            self.fila_nueva_en_proceso = False
            if res.get("status") == "success":
                self._snack_ok("✅ Trabajador agregado.")
                self._actualizar_tabla()
            else:
                self._snack_error(f"❌ {res.get('message')}")

        def on_cancelar(_):
            self.fila_nueva_en_proceso = False
            # quita la última fila añadida (la nueva)
            try:
                self.table.rows.pop()
            except Exception:
                pass
            if self.page:
                self.page.update()

        nueva_fila = ft.DataRow(cells=[
            ft.DataCell(ft.Text("-")),  # ID todavía no asignado
            ft.DataCell(ft.Container(nombre_input, width=300, expand=True)),
            ft.DataCell(ft.Container(tipo_input, width=140, expand=True)),
            ft.DataCell(ft.Container(com_input, width=120, expand=True)),
            ft.DataCell(ft.Container(estado_input, width=120, expand=True)),
            ft.DataCell(ft.Row([
                ft.IconButton(icon=ft.icons.CHECK, icon_color=ft.colors.GREEN_600, tooltip="Aceptar", on_click=on_guardar),
                ft.IconButton(icon=ft.icons.CLOSE, icon_color=ft.colors.RED_600, tooltip="Cancelar", on_click=on_cancelar),
            ], spacing=6)),
        ])

        # Inserta la fila nueva al final de la tabla actual
        if self.table is None:
            self._actualizar_tabla()
        if self.table:  # seguridad
            self.table.rows.append(nueva_fila)
        if self.page:
            self.page.update()

        # focus inicial
        nombre_input.focus()

    # ----------------------------- Import / Export (placeholder) -----------------------------
    def _on_importar(self):
        self._snack_ok("ℹ️ Importar: pendiente de implementación.")

    def _on_exportar(self):
        self._snack_ok("ℹ️ Exportar: pendiente de implementación.")

    # ----------------------------- Notificaciones -----------------------------
    def _snack_ok(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(ft.Text(msg))
        self.page.snack_bar.open = True
        self.page.update()

    def _snack_error(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=ft.colors.RED_200)
        self.page.snack_bar.open = True
        self.page.update()
