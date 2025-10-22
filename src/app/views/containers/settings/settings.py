# app/views/containers/settings.py
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional, Callable
import flet as ft

# ------------------- LOG helper -------------------
def _log(msg: str):
    print(f"[SettingsDB] {msg}")

# Invokers (100% genéricos)
try:
    from app.ui.io.file_save import FileSaver
    from app.ui.io.file_open import FileOpener
    _log("Invokers cargados: FileSaver / FileOpener OK.")
except Exception as e:
    _log(f"❌ No se pudieron importar los invokers genéricos: {e}")
    raise

# DB (ruta estable en tu proyecto)
try:
    from app.config.db.database_mysql import DatabaseMysql
    _log("DatabaseMysql importado desde app.config.db.database_mysql.")
except Exception as e:
    _log(f"❌ No se pudo importar DatabaseMysql: {e}")
    raise

# ---------------- Mensajes / Modales ----------------
# Solo notifications.messages -> ModalAlert -> SnackBar

ModalAlert = None  # se asignará si está disponible

try:
    # firma: (page, titulo, mensaje, texto_boton="Aceptar", on_close=None)
    from app.views.notifications.messages import mostrar_mensaje
    _log("mostrar_mensaje tomado de app.views.notifications.messages")
except Exception as e1:
    _log(f"⚠️ No se encontró notifications.messages: {e1}")
    try:
        from app.views.modals.modal_alert import ModalAlert as _ModalAlert
        ModalAlert = _ModalAlert
        _log("Usando ModalAlert como fallback para mostrar_mensaje")

        def mostrar_mensaje(page: ft.Page, titulo: str, mensaje: str, texto_boton: str = "Aceptar", on_close=None):
            try:
                ModalAlert.mostrar_info(titulo, mensaje)
                # ModalAlert no expone on_close; ejecutamos cleanup inmediatamente.
                if callable(on_close):
                    on_close(None)
            except Exception as ex:
                _log(f"⚠️ Error usando ModalAlert, cayendo a SnackBar: {ex}")
                sb = ft.SnackBar(ft.Text(f"{titulo}: {mensaje}"))
                try:
                    page.snack_bar = sb
                    sb.open = True
                    page.update()
                except Exception:
                    pass
                if callable(on_close):
                    try:
                        on_close(None)
                    except Exception:
                        pass
    except Exception as e3:
        _log(f"⚠️ No se encontró ModalAlert, usando SnackBar simple: {e3}")

        def mostrar_mensaje(page: ft.Page, titulo: str, mensaje: str, texto_boton: str = "Aceptar", on_close=None):
            sb = ft.SnackBar(ft.Text(f"{titulo}: {mensaje}"))
            try:
                page.snack_bar = sb
                sb.open = True
                page.update()
            except Exception:
                pass
            if callable(on_close):
                try:
                    on_close(None)
                except Exception:
                    pass


class SettingsDBContainer(ft.Container):
    """
    Centro modal de mantenimiento MySQL (intermediario de I/O):
      • Exportar base (SQL)
      • Importar base (SQL) con sobrescritura (OVERWRITE/REPLACE) de duplicados
      • Dropear base (con reconexión)

    Flujo de modales:
      • Importar:  Guardar e importar |  Importar |  Cancelar
      • Exportar:  Explicación -> Guardar
      • Dropear:   Guardar y borrar |  Borrar |  Cancelar
    """

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, padding=20)
        _log("Inicializando SettingsDBContainer...")
        self.page = page
        self.db = DatabaseMysql()

        # Estado simple
        self._busy = False

        # Invokers
        self._setup_invokers()

        # UI
        self._build_ui()
        _log("SettingsDBContainer listo.")

    # -------------------------- Infra básica --------------------------
    def _get_page(self) -> Optional[ft.Page]:
        return getattr(self, "page", None)

    def _safe_update(self):
        try:
            self.update()
            return
        except Exception as e:
            _log(f"⚠️ self.update falló: {e}")
        p = self._get_page()
        if p:
            try:
                p.update()
            except Exception as e:
                _log(f"⚠️ page.update falló: {e}")

    def _close_any_dialog(self):
        p = self._get_page()
        if not p:
            return
        dlg = getattr(p, "dialog", None)
        if dlg:
            try:
                dlg.open = False
            except Exception as e:
                _log(f"⚠️ No se pudo cerrar dlg.open: {e}")
            try:
                p.dialog = None
                p.update()
            except Exception as e:
                _log(f"⚠️ No se pudo limpiar page.dialog: {e}")

    def _set_buttons_enabled(self, enabled: bool):
        for btn in (getattr(self, "btn_export_sql", None),
                    getattr(self, "btn_import_sql", None),
                    getattr(self, "btn_drop_db", None)):
            if isinstance(btn, (ft.ElevatedButton, ft.OutlinedButton, ft.FilledButton, ft.TextButton)):
                btn.disabled = not enabled
        _log(f"Botones {'habilitados' if enabled else 'deshabilitados'}.")
        self._safe_update()

    def _show_busy(self):
        if not self._busy:
            self._busy = True
            self._set_buttons_enabled(False)
            _log("⏳ Estado ocupado ON.")

    def _hide_busy(self):
        if self._busy:
            self._busy = False
            self._set_buttons_enabled(True)
            self._close_any_dialog()
            _log("✅ Estado ocupado OFF.")

    def _post_action_cleanup(self):
        """
        Rehabilita controles y asegura que los FilePicker sigan operativos
        tras cerrar el modal de resultado.
        """
        _log("🔧 Post-action cleanup: reinyectando Page y re-habilitando botones.")
        self._busy = False
        self._set_buttons_enabled(True)
        self._ensure_invoker_page()
        # No cerramos el modal aquí; esto lo hace el propio notifications.messages.
        try:
            self._safe_update()
        except Exception as e:
            _log(f"⚠️ Error en _post_action_cleanup.update: {e}")

    def _run_bg(self, target: Callable, *args, after: Optional[Callable] = None):
        """Ejecuta `target` (sin bloquear UI). Llama `after(result, error)` al finalizar."""
        self._show_busy()
        p = self._get_page()
        _log(f"🔧 Ejecutando tarea en background: {getattr(target, '__name__', str(target))}")

        # ⚠️ Aceptar *args porque Flet inyecta un argumento al worker
        def worker(*_args, **_kwargs):
            try:
                res = target(*args)
                return (res, None)
            except Exception as e:
                _log(f"❌ Excepción en worker: {e}")
                return (None, e)

        # ⚠️ Aceptar *args porque Flet llama on_done con 1 arg (resultado)
        def on_done(*_cb_args, **_cb_kwargs):
            res = _cb_args[0] if _cb_args else (None, None)
            try:
                if isinstance(res, tuple) and len(res) == 2:
                    result, error = res
                else:
                    result, error = res, None
            except Exception as e:
                _log(f"❌ Error en on_done desempaquetando resultado: {e}")
                result, error = None, e
            finally:
                self._hide_busy()

            _log(f"🧪 on_done -> result={bool(result)} error={error}")
            if callable(after):
                try:
                    after(result, error)
                except Exception as e:
                    _log(f"❌ Error ejecutando callback after: {e}")

        if p and hasattr(p, "run_thread"):
            p.run_thread(worker, on_done)
        else:
            _log("⚠️ Page sin run_thread: ejecutando en línea.")
            result, error = worker()
            self._hide_busy()
            if callable(after):
                try:
                    after(result, error)
                except Exception as e:
                    _log(f"❌ Error en after (sync): {e}")

    # -------------------------- Invokers --------------------------
    def _setup_invokers(self):
        _log("Configurando invokers de archivo...")
        # Guardar SQL (export)
        self.saver_sql = FileSaver(
            page=self.page,
            on_save=self._do_export_db_sql,           # callback tras elegir ruta
            save_dialog_title="Guardar base completa (SQL)",
            file_name="backup_total.sql",
            allowed_extensions=["sql"],
        )
        # Abrir SQL (import)
        self.opener_sql = FileOpener(
            page=self.page,
            on_select=self._do_import_db_sql_overwrite,  # callback tras seleccionar archivo
            dialog_title="Selecciona archivo .sql",
            allowed_extensions=["sql"],
        )
        # Saver temporal para flujos de “Guardar y ...”
        self._tmp_saver: Optional[FileSaver] = None
        _log("Invokers configurados correctamente.")

    def _ensure_invoker_page(self):
        # Reinyecta la Page por si cambió
        try:
            self.saver_sql.page = self.page
            self.opener_sql.page = self.page
            if self._tmp_saver:
                self._tmp_saver.page = self.page
            _log("Page reinyectada en invokers.")
        except Exception as e:
            _log(f"⚠️ No se pudo reinyectar Page en invokers: {e}")

    # -------------------------- UI --------------------------
    def _build_ui(self):
        _log("Construyendo UI de SettingsDBContainer...")
        title = ft.Text("Mantenimiento de Base de Datos (MySQL)", size=24, weight="bold")

        # Export
        export_title = ft.Text("Exportar (SQL)", size=18, weight="bold")
        self.btn_export_sql = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Image(src="assets/buttons/save-database-button.png", width=20, height=20),
                    ft.Text("Exportar base completa (.sql)"),
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=self._confirm_export_sql,
        )
        export_block = ft.Column(
            controls=[
                export_title,
                ft.Text(
                    "Genera un .sql con estructura y datos de TODA la base (incluye triggers, routines y events).",
                    size=12, color=ft.colors.GREY_700
                ),
                self.btn_export_sql,
            ],
            spacing=10,
        )

        # Import
        import_title = ft.Text("Importar (SQL – sobrescribe duplicados)", size=18, weight="bold")
        self.btn_import_sql = ft.OutlinedButton(
            content=ft.Row(
                controls=[
                    ft.Image(src="assets/buttons/import_database-button.png", width=20, height=20),
                    ft.Text("Importar base desde .sql (REPLACE)"),
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=self._confirm_import_sql,
        )
        import_block = ft.Column(
            controls=[
                import_title,
                ft.Text(
                    "Importa un .sql y sobrescribe registros duplicados (modo OVERWRITE). "
                    "Se recomienda crear un respaldo antes.",
                    size=12, color=ft.colors.GREY_700
                ),
                self.btn_import_sql,
            ],
            spacing=10,
        )

        # Drop
        cleanup_title = ft.Text("Borrar base de datos", size=18, weight="bold")
        self.btn_drop_db = ft.OutlinedButton(
            content=ft.Row(
                controls=[
                    ft.Image(src="assets/buttons/trash-bin.png", width=20, height=20),
                    ft.Text("Dropear base completa"),
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            style=ft.ButtonStyle(color=ft.colors.RED_400),
            on_click=self._confirm_drop_db,
        )
        cleanup_block = ft.Column(
            controls=[
                cleanup_title,
                ft.Text(
                    "Elimina completamente la base actual. Te ofrecemos guardar un respaldo antes.",
                    size=12, color=ft.colors.GREY_700
                ),
                self.btn_drop_db,
            ],
            spacing=10,
        )

        self.content = ft.Column(
            controls=[
                title,
                ft.Divider(height=16),
                export_block,
                ft.Divider(height=24),
                import_block,
                ft.Divider(height=24),
                cleanup_block,
            ],
            spacing=14,
        )
        _log("UI construida.")

    # -------------------------- Modales --------------------------
    def _open_dialog(self, dlg: ft.AlertDialog):
        p = self._get_page()
        if p:
            p.dialog = dlg
            dlg.open = True
            try:
                p.update()
            except Exception as e:
                _log(f"⚠️ p.update al abrir modal falló: {e}")

    def _close_dialog(self, dlg: ft.AlertDialog):
        p = self._get_page()
        try:
            dlg.open = False
        except Exception as e:
            _log(f"⚠️ dlg.open=False falló: {e}")
        if p and getattr(p, "dialog", None) is dlg:
            p.dialog = None
            try:
                p.update()
            except Exception as e:
                _log(f"⚠️ p.update al cerrar modal falló: {e}")

    def _confirm_export_sql(self, _e):
        _log("Abrir modal de confirmación para EXPORT SQL.")
        bullets = [
            "Exportará ESTRUCTURA y DATOS de toda la base en un archivo .sql.",
            "Incluye triggers, procedures, functions y events cuando existan.",
            "No modifica tu base actual; solo crea el archivo de respaldo.",
        ]
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Exportar base completa (SQL)", weight="bold"),
            content=ft.Column([ft.Text(f"• {b}", size=13) for b in bullets], spacing=6, tight=True),
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def _cancel(_):
            _log("Export SQL: cancelado por usuario.")
            self._close_dialog(dlg)

        def _ok(_):
            _log("Export SQL: usuario aceptó → abrir FileSaver.save_file.")
            self._close_dialog(dlg)
            self._ensure_invoker_page()
            try:
                self.saver_sql.open_save()
            except Exception as e:
                _log(f"❌ Error al abrir diálogo de guardado: {e}")
                mostrar_mensaje(self.page, "❌ No se pudo abrir el diálogo de guardado", str(e),
                                on_close=lambda *_: self._post_action_cleanup())

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=_cancel),
            ft.ElevatedButton("Entendido, continuar", on_click=_ok),
        ]
        self._open_dialog(dlg)

    def _confirm_import_sql(self, _e):
        _log("Abrir modal de confirmación para IMPORT SQL.")
        bullets = [
            "Recomendado: crear un respaldo ANTES de importar.",
            "La importación usará modo OVERWRITE (sobrescribe duplicados).",
            "Opciones: Guardar e importar | Importar | Cancelar.",
        ]
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Importar base desde .sql (sobrescribir duplicados)", weight="bold"),
            content=ft.Column([ft.Text(f"• {b}", size=13) for b in bullets], spacing=6, tight=True),
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def _cancel(_):
            _log("Import SQL: cancelado por usuario.")
            self._close_dialog(dlg)

        def _importar(_):
            _log("Import SQL: usuario eligió 'Importar' → abrir FileOpener.pick_files.")
            self._close_dialog(dlg)
            self._ensure_invoker_page()
            try:
                self.opener_sql.open()
            except Exception as e:
                _log(f"❌ Error al abrir diálogo de importación: {e}")
                mostrar_mensaje(self.page, "❌ No se pudo abrir el diálogo de importación", str(e),
                                on_close=lambda *_: self._post_action_cleanup())

        def _guardar_e_importar(_):
            _log("Import SQL: usuario eligió 'Guardar e importar' → pedir ruta de backup.")
            self._close_dialog(dlg)
            fecha = datetime.today().strftime("%Y%m%d_%H%M%S")
            nombre = f"backup_pre_import_{fecha}.sql"

            def _after_backup_save(path: str):
                _log(f"Import SQL: ruta guardado pre-import -> {path}")
                # Exporta y luego abre picker de importación
                def work():
                    return self._db_export_sql_internal(path)

                def done(result, error):
                    if error or not result:
                        _log(f"⚠️ Respaldo fallido antes de importar: {error}")
                        self._info("⚠️ Respaldo fallido", f"No se pudo crear el respaldo.\n{error or ''}".strip(),
                                   on_close=lambda *_: self._post_action_cleanup())
                    else:
                        _log("✅ Respaldo creado correctamente (pre-import).")
                        self._info("✅ Respaldo creado", f"Archivo: {path}",
                                   on_close=lambda *_: self._post_action_cleanup())
                    self._ensure_invoker_page()
                    try:
                        self.opener_sql.open()
                    except Exception as e:
                        _log(f"❌ Error abriendo diálogo de importación luego de backup: {e}")
                        mostrar_mensaje(self.page, "❌ No se pudo abrir el diálogo de importación", str(e),
                                        on_close=lambda *_: self._post_action_cleanup())

                self._run_bg(work, after=done)

            self._tmp_saver = FileSaver(
                page=self.page,
                on_save=_after_backup_save,
                save_dialog_title="Guardar respaldo antes de importar",
                file_name=nombre,
                allowed_extensions=["sql"],
            )
            self._ensure_invoker_page()
            try:
                self._tmp_saver.open_save()
            except Exception as e:
                _log(f"❌ Error al abrir diálogo de guardado (pre-import): {e}")
                mostrar_mensaje(self.page, "❌ No se pudo abrir el diálogo de guardado", str(e),
                                on_close=lambda *_: self._post_action_cleanup())

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=_cancel),
            ft.TextButton("Importar", on_click=_importar),
            ft.ElevatedButton("Guardar e importar", on_click=_guardar_e_importar),
        ]
        self._open_dialog(dlg)

    def _confirm_drop_db(self, _e):
        _log("Abrir modal de confirmación para DROP DB.")
        bullets = [
            "⚠️ Se borrará COMPLETAMENTE la base de datos actual.",
            "Puedes guardar un respaldo .sql antes de borrar.",
            "Opciones: Guardar y borrar | Borrar | Cancelar.",
        ]
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Dropear base de datos", weight="bold", color=ft.colors.RED_400),
            content=ft.Column([ft.Text(f"• {b}", size=13) for b in bullets], spacing=6, tight=True),
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def _cancel(_):
            _log("Drop DB: cancelado por usuario.")
            self._close_dialog(dlg)

        def _borrar(_):
            _log("Drop DB: usuario eligió 'Borrar'.")
            self._close_dialog(dlg)
            self._do_drop_db()

        def _guardar_y_borrar(_):
            _log("Drop DB: usuario eligió 'Guardar y borrar' → pedir ruta de backup.")
            self._close_dialog(dlg)
            fecha = datetime.today().strftime("%Y%m%d_%H%M%S")
            nombre = f"backup_pre_drop_{fecha}.sql"

            def _after_backup_save(path: str):
                _log(f"Drop DB: ruta guardado pre-drop -> {path}")
                def work():
                    return self._db_export_sql_internal(path)

                def done(result, error):
                    if error or not result:
                        _log(f"⚠️ Respaldo fallido antes de borrar: {error}")
                        self._info("⚠️ Respaldo fallido",
                                   f"No se pudo crear el respaldo.\n{error or ''}".strip(),
                                   on_close=lambda *_: self._post_action_cleanup())
                        # Confirmar si desea continuar
                        self._confirm_continuar_borrado()
                    else:
                        _log("✅ Respaldo creado correctamente (pre-drop).")
                        self._info("✅ Respaldo creado", f"Archivo: {path}",
                                   on_close=lambda *_: self._post_action_cleanup())
                        self._do_drop_db()

                self._run_bg(work, after=done)

            self._tmp_saver = FileSaver(
                page=self.page,
                on_save=_after_backup_save,
                save_dialog_title="Guardar respaldo antes de borrar",
                file_name=nombre,
                allowed_extensions=["sql"],
            )
            self._ensure_invoker_page()
            try:
                self._tmp_saver.open_save()
            except Exception as e:
                _log(f"❌ Error al abrir diálogo de guardado (pre-drop): {e}")
                mostrar_mensaje(self.page, "❌ No se pudo abrir el diálogo de guardado", str(e),
                                on_close=lambda *_: self._post_action_cleanup())

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=_cancel),
            ft.TextButton("Borrar", on_click=_borrar, style=ft.ButtonStyle(color=ft.colors.RED_400)),
            ft.ElevatedButton("Guardar y borrar", on_click=_guardar_y_borrar),
        ]
        self._open_dialog(dlg)

    def _confirm_continuar_borrado(self):
        _log("Confirmación secundaria: continuar borrado sin respaldo.")
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Continuar sin respaldo?", weight="bold"),
            content=ft.Text("No se pudo crear el respaldo. ¿Deseas borrar la base de todas maneras?"),
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg.actions = [
            ft.TextButton("Cancelar", on_click=lambda e: ( _log("Drop DB: cancelar posterior a fallo de respaldo."), self._close_dialog(dlg) )),
            ft.ElevatedButton("Borrar de todos modos", on_click=lambda e: ( _log("Drop DB: continuar sin respaldo."), self._close_dialog(dlg), self._do_drop_db())),
        ]
        self._open_dialog(dlg)

    # -------------------------- Helpers de ruta --------------------------
    @staticmethod
    def _ensure_ext(path: str, ext: str) -> str:
        ext = ext.lower().lstrip(".")
        return path if path.lower().endswith("." + ext) else f"{path}.{ext}"

    @staticmethod
    def _check_allowed(path: str, allowed_exts: list[str]) -> bool:
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        return ext in [e.lower().lstrip(".") for e in allowed_exts]

    # -------------------------- Operaciones reales --------------------------
    def _db_export_sql_internal(self, path: str) -> bool:
        """Intenta exportar con firma nueva; si no, cae a firma antigua."""
        path = self._ensure_ext((path or "").strip(), "sql")
        _log(f"Export interno a: {path}")
        try:
            res = self.db.exportar_base_datos(path, insert_mode="standard")  # type: ignore
            _log(f"Export DB (firma nueva) → {bool(res)}")
            return bool(res)
        except TypeError:
            _log("Firma nueva no soportada, usando firma clásica.")
            res = self.db.exportar_base_datos(path)
            _log(f"Export DB (clásica) → {bool(res)}")
            return bool(res)

    def _info(self, titulo: str, mensaje: str, *, on_close: Optional[Callable] = None):
        """Muestra modal informativo y ejecuta cleanup al cerrarlo (cuando es posible)."""
        try:
            mostrar_mensaje(self.page, titulo, mensaje, on_close=on_close or (lambda *_: self._post_action_cleanup()))
            _log(f"mostrar_mensaje -> '{titulo}' (con on_close)")
        except Exception as e:
            _log(f"⚠️ mostrar_mensaje falló ({e}); intentando ModalAlert o SnackBar.")
            # Fallback ya está definido arriba en import-time

    def _do_export_db_sql(self, path: str):
        _log(f"Solicitado export DB a ruta: {path}")
        def work():
            return self._db_export_sql_internal(path)

        def done(result, error):
            self._close_any_dialog()
            # habilitar antes de mostrar el modal (por si el modal no tiene on_close)
            self._post_action_cleanup()
            if error:
                _log(f"❌ Export DB error: {error}")
                self._info("❌ Error al exportar", str(error))
                return
            if result:
                final = self._ensure_ext(path, 'sql')
                _log(f"✅ Export DB OK → {final}")
                self._info("✅ Exportación completa", f"La base fue exportada correctamente.\nRuta: {final}")
            else:
                _log("⚠️ Export DB devolvió False.")
                self._info("⚠️ Error", "No se pudo exportar la base.")
        self._run_bg(work, after=done)

    def _do_import_db_sql_overwrite(self, path: str):
        _log(f"Solicitado import DB desde: {path}")
        path = (path or "").strip()
        if not path or not os.path.exists(path) or not self._check_allowed(path, ["sql"]):
            self._close_any_dialog()
            _log("⚠️ Archivo inválido para importación.")
            self._post_action_cleanup()
            self._info("⚠️ Archivo inválido", "Selecciona un archivo .sql válido.")
            return

        def work():
            try:
                _log("Intentando importar con firma avanzada (mode='overwrite', recreate_schema=False).")
                return bool(self.db.importar_base_datos(path, mode="overwrite", recreate_schema=False, page=self.page))  # type: ignore
            except TypeError:
                _log("Firma avanzada no soportada; usando importar_base_datos(path).")
                return bool(self.db.importar_base_datos(path, page=self.page))

        def done(result, error):
            self._close_any_dialog()
            # re-habilitar controles ANTES del modal
            self._post_action_cleanup()
            if error:
                _log(f"❌ Import DB error: {error}")
                self._info("❌ Error al importar", f"Ocurrió un error:\n{error}")
                return
            if result:
                try:
                    self.db.connect()
                    _log("Conexión restablecida tras importación.")
                except Exception as e:
                    _log(f"⚠️ db.connect tras import falló: {e}")
                self._info("✅ Importación completa",
                           f"Base '{self.db.database}' importada correctamente.\nArchivo: {path}")
                self._publish_refresh()
            else:
                _log("⚠️ Import DB devolvió False.")
                self._info("⚠️ Error", f"No se pudo importar la base '{self.db.database}'.")
        self._run_bg(work, after=done)

    def _do_drop_db(self):
        _log("Ejecutando drop DB...")
        def work():
            try:
                res = bool(self.db.dropear_base_datos(bootstrap_cb=None))  # type: ignore
                _log(f"dropear_base_datos → {res}")
                return res
            except AttributeError:
                _log("❌ dropear_base_datos no existe en DatabaseMysql.")
                raise RuntimeError(
                    "El método 'dropear_base_datos' no existe en DatabaseMysql. "
                    "Actualiza tu módulo DB para soportarlo."
                )

        def done(result, error):
            self._close_any_dialog()
            # re-habilitar controles ANTES del modal
            self._post_action_cleanup()
            if error or not result:
                _log(f"❌ Drop DB error/result={result}: {error}")
                self._info("❌ Error", f"No se pudo dropear la base.\n{error or ''}".strip())
                return
            try:
                self.db.connect()
                _log("Conexión restablecida tras drop DB.")
            except Exception as e:
                _log(f"⚠️ db.connect tras drop falló: {e}")
            self._info("🗑️ Base eliminada", "La base fue eliminada y la conexión restablecida.")
            self._publish_refresh()
        self._run_bg(work, after=done)

    # -------------------------- Utilidades UI --------------------------
    def _publish_refresh(self):
        pubsub = getattr(self.page, "pubsub", None)
        if not pubsub:
            _log("No hay pubsub disponible para notificar refresh.")
            return
        try:
            if hasattr(pubsub, "publish"):
                pubsub.publish("db:refrescar_datos", True)
                _log("pubsub.publish('db:refrescar_datos', True) enviado.")
            elif hasattr(pubsub, "send_all"):
                pubsub.send_all("db:refrescar_datos", True)
                _log("pubsub.send_all('db:refrescar_datos', True) enviado.")
        except Exception as e:
            _log(f"⚠️ Error notificando por pubsub: {e}")
