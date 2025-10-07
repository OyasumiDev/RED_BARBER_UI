# app/views/containers/trabajadores/trabajadores_container.py

from __future__ import annotations
from typing import Any, Dict, List, Optional
import flet as ft

from app.config.application.app_state import AppState
from app.models.trabajadores_model import TrabajadoresModel
from app.core.enums.e_trabajadores import E_TRABAJADORES, E_TRAB_TIPO, E_TRAB_ESTADO

from app.ui.factory.boton_factory import boton_agregar
from app.ui.builders.table_builder import TableBuilder
from app.ui.sorting.sort_manager import SortManager
from app.ui.scroll.table_scroll_controller import ScrollTableController

from app.ui.io.file_open_invoker import FileOpenInvoker
from app.ui.io.file_save_invoker import FileSaveInvoker


# -----------------------------
# Helpers de formato
# -----------------------------
def fmt_text(v: Any) -> str:
    return "" if v is None else str(v)

def fmt_float2(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "0.00"


class TrabajadoresContainer(ft.Container):
    """
    Área de TRABAJADORES:
      - Agregar / Importar / Exportar (placeholders)
      - Búsqueda + Orden
      - Tabla editable inline
      - Aceptar/Cancelar SOLO para filas nuevas (sin ID)
      - Editar/Eliminar para filas existentes
    """
    def __init__(self):
        super().__init__(expand=True, padding=20)

        # --- Estado / modelo ---
        self.model = TrabajadoresModel()
        self.sort = SortManager()
        self.group = "trabajadores"

        self._rows: List[Dict[str, Any]] = []
        self._search_text: str = ""
        self._order_dd_value: str = "id"

        # Invokers (IO) – placeholders
        page_ref = AppState().page
        self._open_invoker = FileOpenInvoker(
            page=page_ref,
            on_select=self._on_import_selected,
            dialog_title="Importar trabajadores",
            allowed_extensions=["csv", "xlsx", "json"],
        )
        self._save_invoker = FileSaveInvoker(
            page=page_ref,
            on_save=lambda p: None,
            save_dialog_title="Exportar trabajadores",
            file_name="trabajadores_export.sql",
            allowed_extensions=["sql"],
        )

        # Scroll controller (tabla)
        self._stc = ScrollTableController(min_width=980, max_height=520)

        # ---- UI base ----
        self._build_ui()

    # ==========================
    # Construcción de UI
    # ==========================
    def _build_ui(self):
        title = ft.Text("ÁREA DE TRABAJADORES", size=20, weight="bold")

        buttons_row = ft.Row(
            [
                boton_agregar(self._on_add_new),
                self._open_invoker.get_import_button(),
                self._save_invoker.get_export_button(),
            ],
            spacing=12,
        )

        # Filtros
        self._order_dd = ft.Dropdown(
            label="Ordenar por",
            width=260,
            value="id",
            options=[
                ft.dropdown.Option(key="id", text="Nómina (ID)"),
                ft.dropdown.Option(key="nombre", text="Nombre"),
                ft.dropdown.Option(key="tipo", text="Tipo"),
                ft.dropdown.Option(key="comision", text="Comisión %"),
                ft.dropdown.Option(key="estado", text="Estado"),
            ],
            on_change=self._on_order_change,
            dense=True,
        )

        self._clear_order_btn = ft.IconButton(
            icon=ft.icons.CLOSE,
            tooltip="Limpiar orden",
            on_click=lambda e: self._clear_order(),
        )

        self._search_tf = ft.TextField(
            label="Buscar por Nombre",
            width=360,
            on_submit=lambda e: self._reload_from_db(),
            prefix_icon=ft.icons.SEARCH,
            dense=True,
            height=40,
        )

        self._clear_search_btn = ft.IconButton(
            icon=ft.icons.CLOSE,
            tooltip="Limpiar búsqueda",
            on_click=lambda e: self._clear_search(),
        )

        filters_row = ft.Row(
            [self._order_dd, self._clear_order_btn, self._search_tf, self._clear_search_btn],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        # --- Tabla ---
        self._table_builder = TableBuilder(
            group=self.group,
            sort_manager=self.sort,
            columns=[
                {
                    "key": E_TRABAJADORES.ID.value, "title": "Nómina", "width": 120,
                    "formatter": lambda v, r: ft.Text(fmt_text(v)) if not r.get("_edit") and not r.get("_is_new")
                    else self._mk_ro_text(fmt_text(v))  # ID no editable
                },
                {
                    "key": E_TRABAJADORES.NOMBRE.value, "title": "Nombre", "width": 360,
                    "formatter": lambda v, r: self._fmt_nombre(v, r),
                },
                {
                    "key": E_TRABAJADORES.TIPO.value, "title": "Tipo", "width": 160,
                    "formatter": lambda v, r: self._fmt_tipo(v, r),
                },
                {
                    "key": E_TRABAJADORES.COMISION.value, "title": "Comisión %", "width": 140,
                    "formatter": lambda v, r: self._fmt_comision(v, r),
                },
                {
                    "key": E_TRABAJADORES.ESTADO.value, "title": "Estado", "width": 140,
                    "formatter": lambda v, r: self._fmt_estado(v, r),
                },
            ],
            on_sort_change=self._on_sort_change,
            on_accept=self._wrap_accept,    # Acepta SOLO nuevos (sin ID)
            on_cancel=self._wrap_cancel,    # Cancela SOLO nuevos
            on_edit=self._on_row_edit,      # Toggle: entrar/guardar edición para existentes
            on_delete=self._on_row_delete,
            heading_row_height=46,
            data_row_min_height=64,
            actions_title="Acciones",
            actions_width=220,
            dense_text=True,
            id_key=E_TRABAJADORES.ID.value,  # clave para detectar "fila nueva"
            # Scroll / auto-scroll
            scroll_controller=self._stc,
            auto_scroll_new=True,
            auto_scroll_target="last",
        )

        table_control = self._table_builder.build()
        self._table_builder.attach_scroll_controller(self._stc)
        table_wrapper = self._stc.build(table_control)

        self.content = ft.Column(
            [
                title,
                buttons_row,
                filters_row,
                ft.Divider(height=12),
                table_wrapper,
            ],
            spacing=12,
            expand=True,
        )

    # ==========================
    # did_mount
    # ==========================
    def did_mount(self):
        # Asegurar pickers en overlay real
        if self._open_invoker and self._open_invoker.picker not in self.page.overlay:
            self.page.overlay.append(self._open_invoker.picker)
        if self._save_invoker and self._save_invoker.save_picker not in self.page.overlay:
            self.page.overlay.append(self._save_invoker.save_picker)

        self._reload_from_db()

    # ==========================
    # Column formatters (edición inline)
    # ==========================
    def _mk_ro_text(self, value: str) -> ft.Control:
        return ft.Text(value, size=12)

    def _fmt_nombre(self, v: Any, row: Dict[str, Any]) -> ft.Control:
        if row.get("_edit") or row.get("_is_new"):
            tf = row.setdefault("_ctrl_nombre", ft.TextField(
                value=fmt_text(v), width=340, dense=True, height=40,
                on_submit=(lambda e, r=row: self._wrap_accept(r) if r.get(E_TRABAJADORES.ID.value) in (None, "", 0) else None)
            ))
            return tf
        return ft.Text(fmt_text(v), size=12)

    def _fmt_tipo(self, v: Any, row: Dict[str, Any]) -> ft.Control:
        if row.get("_edit") or row.get("_is_new"):
            dd = row.get("_ctrl_tipo")
            options = [
                ft.dropdown.Option(key=E_TRAB_TIPO.OCASIONAL.value, text="ocasional"),
                ft.dropdown.Option(key=E_TRAB_TIPO.PLANTA.value, text="planta"),
                ft.dropdown.Option(key=E_TRAB_TIPO.DUENO.value, text="dueno"),
            ]
            if not dd:
                dd = ft.Dropdown(value=v or E_TRAB_TIPO.OCASIONAL.value, width=150, options=options, dense=True)
                row["_ctrl_tipo"] = dd
            return ft.Container(dd, height=40, alignment=ft.alignment.center_left)
        return ft.Text(fmt_text(v), size=12)

    def _fmt_comision(self, v: Any, row: Dict[str, Any]) -> ft.Control:
        if row.get("_edit") or row.get("_is_new"):
            tf = row.setdefault("_ctrl_comision", ft.TextField(value=fmt_float2(v), width=120, dense=True, height=40))
            return tf
        return ft.Text(fmt_float2(v), size=12)

    def _fmt_estado(self, v: Any, row: Dict[str, Any]) -> ft.Control:
        if row.get("_edit") or row.get("_is_new"):
            dd = row.get("_ctrl_estado")
            options = [
                ft.dropdown.Option(key=E_TRAB_ESTADO.ACTIVO.value, text="activo"),
                ft.dropdown.Option(key=E_TRAB_ESTADO.INACTIVO.value, text="inactivo"),
            ]
            if not dd:
                dd = ft.Dropdown(value=v or E_TRAB_ESTADO.ACTIVO.value, width=130, options=options, dense=True)
                row["_ctrl_estado"] = dd
            return ft.Container(dd, height=40, alignment=ft.alignment.center_left)
        return ft.Text(fmt_text(v), size=12)

    # ==========================
    # Envolturas TableBuilder
    # ==========================
    def _wrap_accept(self, row: Dict[str, Any]):
        """Aceptar SOLO filas nuevas (sin ID)."""
        self._save_row(row, is_new=True)

    def _wrap_cancel(self, row: Dict[str, Any]):
        """Cancelar SOLO filas nuevas (sin ID)."""
        if row.get(E_TRABAJADORES.ID.value) in (None, "", 0):
            # quitar fila temporal
            self._rows = [r for r in self._rows if r is not row]
            self._table_builder.set_rows(self._rows)
        else:
            # por si acaso, limpiar flags
            row.pop("_edit", None)
            row.pop("_is_new", None)
            self._table_builder.refresh()

    # ==========================
    # Acciones top
    # ==========================
    def _on_add_new(self):
        """Inserta una fila nueva temporal (sin ID) para Aceptar/Cancelar desde la tabla."""
        new_row = {
            E_TRABAJADORES.ID.value: None,
            E_TRABAJADORES.NOMBRE.value: "",
            E_TRABAJADORES.TIPO.value: E_TRAB_TIPO.OCASIONAL.value,
            E_TRABAJADORES.COMISION.value: 0.0,
            E_TRABAJADORES.ESTADO.value: E_TRAB_ESTADO.ACTIVO.value,
            "_is_new": True,
        }
        self._rows.append(new_row)
        self._table_builder.set_rows(self._rows)

    def _on_import_selected(self, path: str):
        # Placeholder
        self._notify(f"Archivo seleccionado: {path}")

    # ==========================
    # Acciones por fila
    # ==========================
    def _on_row_edit(self, row: Dict[str, Any]):
        """
        Toggle edición para filas existentes:
        - Si no está en edición -> activar edición inline.
        - Si ya está en edición -> guardar cambios (usar botón Editar como 'Guardar').
        """
        has_id = row.get(E_TRABAJADORES.ID.value) not in (None, "", 0)
        if not has_id:
            return  # nuevas se aceptan via Aceptar del builder

        if not row.get("_edit"):
            row["_edit"] = True
            self._table_builder.refresh()
            return

        # Ya estaba en edición -> guardar como update
        self._save_row(row, is_new=False)

    def _save_row(self, row: Dict[str, Any], *, is_new: bool):
        try:
            nombre = (row.get("_ctrl_nombre").value if row.get("_ctrl_nombre") else row.get(E_TRABAJADORES.NOMBRE.value) or "").strip()
            tipo   = (row.get("_ctrl_tipo").value   if row.get("_ctrl_tipo")   else row.get(E_TRABAJADORES.TIPO.value)) or E_TRAB_TIPO.OCASIONAL.value
            com_v  =  row.get("_ctrl_comision").value if row.get("_ctrl_comision") else row.get(E_TRABAJADORES.COMISION.value)
            estado = (row.get("_ctrl_estado").value if row.get("_ctrl_estado") else row.get(E_TRABAJADORES.ESTADO.value)) or E_TRAB_ESTADO.ACTIVO.value

            if not nombre:
                self._notify("⚠️ El nombre es obligatorio.")
                return

            try:
                comision = float(com_v)
            except Exception:
                comision = 0.0

            insert_id: Optional[int] = None

            if is_new:
                res = self.model.crear_trabajador(
                    nombre=nombre,
                    tipo=tipo,
                    comision_porcentaje=comision,
                    telefono=None,
                    email=None,
                    estado=estado,
                )
                if res.get("status") != "success":
                    self._notify(f"❌ No se pudo crear: {res.get('message')}")
                    return

                # Intentar leer id insertado en distintas convenciones
                insert_id = res.get("insert_id") or res.get("id") \
                            or (res.get("data") or {}).get("id")

            else:
                res = self.model.actualizar_trabajador(
                    trabajador_id=row[E_TRABAJADORES.ID.value],
                    nombre=nombre,
                    tipo=tipo,
                    comision_porcentaje=comision,
                    estado=estado,
                )
                if res.get("status") != "success":
                    self._notify(f"❌ No se pudo actualizar: {res.get('message')}")
                    return
                insert_id = row.get(E_TRABAJADORES.ID.value)

            self._notify("✅ Cambios guardados.")
            self._reload_from_db(new_focus_id=insert_id)

        except Exception as ex:
            self._notify(f"❌ Error: {ex}")

    def _on_row_delete(self, row: Dict[str, Any]):
        idv = row.get(E_TRABAJADORES.ID.value)
        if not idv:
            # fila nueva sin guardar -> quitar
            self._rows = [r for r in self._rows if r is not row]
            self._table_builder.set_rows(self._rows)
            return

        def do_delete(_):
            res = self.model.eliminar_trabajador(int(idv))
            self.page.close(dlg)
            if res.get("status") == "success":
                self._notify("🗑️ Registro eliminado.")
                self._reload_from_db()
            else:
                self._notify(f"❌ No se pudo eliminar: {res.get('message')}")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar eliminación"),
            content=ft.Text("¿Deseas eliminar este trabajador? Esta acción no se puede deshacer."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dlg)),
                ft.ElevatedButton("Eliminar", on_click=do_delete, bgcolor=ft.colors.RED_600, color=ft.colors.WHITE),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    # ==========================
    # Filtros / Sorting / Data
    # ==========================
    def _on_sort_change(self, grupo: str, key: str, asc: Optional[bool]):
        self._apply_in_memory_sort(key, asc)

    def _on_order_change(self, e: ft.ControlEvent):
        self._order_dd_value = self._order_dd.value or "id"
        key_map = {
            "id": E_TRABAJADORES.ID.value,
            "nombre": E_TRABAJADORES.NOMBRE.value,
            "tipo": E_TRABAJADORES.TIPO.value,
            "comision": E_TRABAJADORES.COMISION.value,
            "estado": E_TRABAJADORES.ESTADO.value,
        }
        self.sort.set(self.group, key_map.get(self._order_dd_value, E_TRABAJADORES.ID.value), True)
        self._apply_in_memory_sort(*self.sort.get(self.group))

    def _clear_order(self):
        self._order_dd.value = "id"
        self.sort.clear_sort(self.group)  # alias en SortManager
        self._apply_in_memory_sort(None, None)

    def _clear_search(self):
        self._search_tf.value = ""
        self._search_text = ""
        self._reload_from_db()

    def _apply_in_memory_sort(self, key: Optional[str], asc: Optional[bool]):
        if key and asc is not None:
            self._rows.sort(
                key=lambda r: (r.get(key) is None, str(r.get(key)).lower() if r.get(key) is not None else ""),
                reverse=(asc is False),
            )
        self._table_builder.set_rows(self._rows)

    def _reload_from_db(self, new_focus_id: Optional[int] = None):
        try:
            data = self.model.listar() if hasattr(self.model, "listar") else []

            # Limpieza de flags UI
            for r in data:
                r.pop("_edit", None)
                r.pop("_is_new", None)

            # Búsqueda que prioriza coincidencias pero NO oculta las demás
            self._search_text = (self._search_tf.value or "").strip().lower()
            if self._search_text:
                matches = []
                rest = []
                for r in data:
                    name = (r.get(E_TRABAJADORES.NOMBRE.value, "") or "").lower()
                    (matches if self._search_text in name else rest).append(r)
                data = matches + rest

            self._rows = data

            key, asc = self.sort.get(self.group)
            self._apply_in_memory_sort(key, asc)

            # Scroll al nuevo registro si lo conocemos
            if new_focus_id:
                idx = next((i for i, r in enumerate(self._rows) if r.get(E_TRABAJADORES.ID.value) == new_focus_id), -1)
                if idx >= 0 and self._stc:
                    try:
                        self._stc.scroll_to_row_index(idx, margin_top=8)
                    except Exception:
                        pass

        except Exception as ex:
            self._notify(f"❌ Error cargando datos: {ex}")

    # ==========================
    # Utilidades
    # ==========================
    def _notify(self, msg: str):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(ft.Text(msg))
        self.page.snack_bar.open = True
        self.page.update()
