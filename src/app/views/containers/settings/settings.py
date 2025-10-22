# app/views/containers/settings.py
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional, Callable
import threading
import flet as ft

# Bootstrap principal (post drop / post import)
from app.config.db.bootstrap_db import bootstrap_after_drop

# ------------------- LOG helper -------------------
def _log(msg: str):
    print(f"[SettingsDB] {msg}")

# Invokers
try:
    from app.ui.io.file_save import FileSaver
    from app.ui.io.file_open import FileOpener
    _log("Invokers cargados: FileSaver / FileOpener OK.")
except Exception as e:
    _log(f"❌ No se pudieron importar los invokers genéricos: {e}")
    raise

# DB
try:
    from app.config.db.database_mysql import DatabaseMysql
    _log("DatabaseMysql importado desde app.config.db.database_mysql.")
except Exception as e:
    _log(f"❌ No se pudo importar DatabaseMysql: {e}")
    raise


class SettingsDBContainer(ft.Container):
    """
    Centro de mantenimiento MySQL:
      • Exportar (SQL)
      • Importar (SQL) OVERWRITE/REPLACE
      • Dropear base (con bootstrap posterior)
    """

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, padding=20)
        _log("Inicializando SettingsDBContainer...")
        self.page = page
        self.db = DatabaseMysql()
        self._busy = False

        self._setup_invokers()
        self._build_ui()
        _log("SettingsDBContainer listo.")

    # -------------------------- Infra básica --------------------------
    def _get_page(self) -> Optional[ft.Page]:
        return getattr(self, "page", None)

    def _safe_update(self):
        try:
            self.update();  return
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
            if isinstance(btn, (ft.ElevatedButton, ft.OutlinedButton,
                                ft.FilledButton, ft.TextButton)):
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
        _log("🔧 Post-action cleanup: reinyectando Page y re-habilitando botones.")
        self._busy = False
        self._set_buttons_enabled(True)
        self._ensure_invoker_page()
        self._safe_update()

    # --------- BG runner: SIEMPRE threading + call_from_thread ----------
    def _run_bg(self, work: Callable[[], object],
                after: Optional[Callable[[object, Optional[Exception]], None]] = None):
        """
        Ejecuta `work` en un hilo de fondo y, al terminar,
        llama `after(result, error)` garantizado en el hilo de UI.
        """
        self._show_busy()
        p = self._get_page()
        _log("🔧 Ejecutando tarea en background.")

        def worker_wrapper():
            try:
                res = work()
                return (res, None)
            except Exception as ex:
                _log(f"❌ Excepción en worker: {ex}")
                return (None, ex)

        def finish_on_main(res_tuple):
            try:
                result, error = res_tuple
            except Exception as ex:
                result, error = None, ex
            finally:
                self._hide_busy()
            _log(f"🧪 on_done -> result={bool(result)} error={error}")
            if callable(after):
                try:
                    after(result, error)
                except Exception as ex:
                    _log(f"❌ Error ejecutando callback after: {ex}")

        def runner():
            res = worker_wrapper()
            pg = self._get_page()
            if pg and hasattr(pg, "call_from_thread"):
                pg.call_from_thread(lambda: finish_on_main(res))
            else:
                # Último recurso: ejecutar directo (no ideal, pero evita quedarte bloqueado)
                finish_on_main(res)

        threading.Thread(target=runner, daemon=True).start()

    # -------------------------- Mensajes propios --------------------------
    def _show_message(self, title: str, message: str, *,
                      kind: str = "info",
                      on_close: Optional[Callable] = None,
                      button_text: str = "Aceptar"):
        """
        Modal simple sin dependencias externas.
        kind: "info" | "success" | "error"
        """
        p = self._get_page()
        if not p:
            _log(f"⚠️ No hay Page para mostrar mensaje: {title}")
            return

        self._close_any_dialog()  # evita quedarte con un dialog previo abierto

        color = {
            "info": ft.colors.PRIMARY,
            "success": ft.colors.GREEN_500,
            "error": ft.colors.RED_400
        }.get(kind, ft.colors.PRIMARY)

        icon = {
            "info": ft.icons.INFO_OUTLINED,
            "success": ft.icons.CHECK_CIRCLE_OUTLINED,
            "error": ft.icons.ERROR_OUTLINE
        }.get(kind, ft.icons.INFO_OUTLINED)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(name=icon, color=color),
                ft.Text(title, weight="bold", color=color),
            ], spacing=8),
            content=ft.Text(message),
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def _ok(_):
            try:
                dlg.open = False
            except Exception:
                pass
            if getattr(p, "dialog", None) is dlg:
                p.dialog = None
            try:
                p.update()
            except Exception:
                pass
            if callable(on_close):
                try:
                    on_close(None)
                except Exception:
                    pass

        dlg.actions = [ft.ElevatedButton(button_text, on_click=_ok)]
        try:
            p.dialog = dlg
            dlg.open = True
            p.update()
            _log(f"Modal mostrado: {title}")
        except Exception as ex:
            _log(f"⚠️ No se pudo abrir modal ({ex}); usando SnackBar.")
            try:
                sb = ft.SnackBar(ft.Text(f"{title}: {message}"))
                p.snack_bar = sb
                sb.open = True
                p.update()
            except Exception:
                pass
            if callable(on_close):
                try:
                    on_close(None)
                except Exception:
                    pass

    def _info(self, titulo: str, mensaje: str, *, kind: str = "info",
              on_close: Optional[Callable] = None):
        # Rehabilita primero; luego muestra (para que el usuario pueda accionar)
        if on_close is None:
            on_close = lambda *_: self._post_action_cleanup()
        self._post_action_cleanup()
        self._show_message(titulo, mensaje, kind=kind, on_close=on_close)

    # -------------------------- Invokers --------------------------
    def _setup_invokers(self):
        _log("Configurando invokers de archivo...")
        self.saver_sql = FileSaver(
            page=self.page,
            on_save=self._do_export_db_sql,
            save_dialog_title="Guardar base completa (SQL)",
            file_name="backup_total.sql",
            allowed_extensions=["sql"],
        )
        self.opener_sql = FileOpener(
            page=self.page,
            on_select=self._do_import_db_sql_overwrite,
            dialog_title="Selecciona archivo .sql",
            allowed_extensions=["sql"],
        )
        self._tmp_saver: Optional[FileSaver] = None
        _log("Invokers configurados correctamente.")

    def _ensure_invoker_page(self):
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

    # -------------------------- Modales de confirmación --------------------------
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
                self._info("❌ No se pudo abrir el diálogo de guardado", str(e), kind="error")

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
                self._info("❌ No se pudo abrir el diálogo de importación", str(e), kind="error")

        def _guardar_e_importar(_):
            _log("Import SQL: usuario eligió 'Guardar e importar' → pedir ruta de backup.")
            self._close_dialog(dlg)
            fecha = datetime.today().strftime("%Y%m%d_%H%M%S")
            nombre = f"backup_pre_import_{fecha}.sql"

            def _after_backup_save(path: str):
                _log(f"Import SQL: ruta guardado pre-import -> {path}")

                def work():
                    return self._db_export_sql_internal(path)

                def done(result, error):
                    if error or not result:
                        _log(f"⚠️ Respaldo fallido antes de importar: {error}")
                        self._info("⚠️ Respaldo fallido",
                                   f"No se pudo crear el respaldo.\n{error or ''}".strip(),
                                   kind="error")
                    else:
                        _log("✅ Respaldo creado correctamente (pre-import).")
                        self._info("✅ Respaldo creado", f"Archivo: {path}",
                                   kind="success")
                    self._ensure_invoker_page()
                    try:
                        self.opener_sql.open()
                    except Exception as e:
                        _log(f"❌ Error abriendo diálogo de importación luego de backup: {e}")
                        self._info("❌ No se pudo abrir el diálogo de importación", str(e), kind="error")

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
                self._info("❌ No se pudo abrir el diálogo de guardado", str(e), kind="error")

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
                                   kind="error")
                        self._confirm_continuar_borrado()
                    else:
                        _log("✅ Respaldo creado correctamente (pre-drop).")
                        self._info("✅ Respaldo creado", f"Archivo: {path}",
                                   kind="success")
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
                self._info("❌ No se pudo abrir el diálogo de guardado", str(e), kind="error")

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
            ft.TextButton("Cancelar",
                          on_click=lambda e: (_log("Drop DB: cancelar posterior a fallo de respaldo."),
                                              self._close_dialog(dlg))),
            ft.ElevatedButton("Borrar de todos modos",
                              on_click=lambda e: (_log("Drop DB: continuar sin respaldo."),
                                                  self._close_dialog(dlg), self._do_drop_db())),
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

    def _do_export_db_sql(self, path: str):
        _log(f"Solicitado export DB a ruta: {path}")
        def work():
            return self._db_export_sql_internal(path)

        def done(result, error):
            self._close_any_dialog()
            if error:
                _log(f"❌ Export DB error: {error}")
                self._info("❌ Error al exportar", str(error), kind="error")
                return
            if result:
                final = self._ensure_ext(path, 'sql')
                _log(f"✅ Export DB OK → {final}")
                self._info("✅ Exportación completa",
                           f"La base fue exportada correctamente.\nRuta: {final}",
                           kind="success")
            else:
                _log("⚠️ Export DB devolvió False.")
                self._info("⚠️ Error", "No se pudo exportar la base.", kind="error")
        self._run_bg(work, after=done)

    def _do_import_db_sql_overwrite(self, path: str):
        _log(f"Solicitado import DB desde: {path}")
        path = (path or "").strip()
        if not path or not os.path.exists(path) or not self._check_allowed(path, ["sql"]):
            self._close_any_dialog()
            _log("⚠️ Archivo inválido para importación.")
            self._info("⚠️ Archivo inválido", "Selecciona un archivo .sql válido.", kind="error")
            return

        def work():
            try:
                _log("Intentando importar (mode='overwrite', recreate_schema=False).")
                return bool(self.db.importar_base_datos(path, mode="overwrite", recreate_schema=False))  # type: ignore
            except TypeError:
                _log("Firma avanzada no soportada; usando importar_base_datos(path).")
                return bool(self.db.importar_base_datos(path))

        def done(result, error):
            self._close_any_dialog()
            if error:
                _log(f"❌ Import DB error: {error}")
                self._info("❌ Error al importar", f"Ocurrió un error:\n{error}", kind="error")
                return
            if result:
                # Por si el .sql no trae todo en orden, corre bootstrap
                try:
                    bootstrap_after_drop(db=self.db, logger=_log)
                    _log("Bootstrap post-import ejecutado.")
                except Exception as e:
                    _log(f"⚠️ Bootstrap post-import falló: {e}")
                try:
                    self.db.connect()
                    _log("Conexión restablecida tras importación.")
                except Exception as e:
                    _log(f"⚠️ db.connect tras import falló: {e}")

                self._info("✅ Importación completa",
                           f"Base '{self.db.database}' importada correctamente.\nArchivo: {path}",
                           kind="success")
                self._publish_refresh()
            else:
                _log("⚠️ Import DB devolvió False.")
                self._info("⚠️ Error", f"No se pudo importar la base '{self.db.database}'.", kind="error")
        self._run_bg(work, after=done)

    def _do_drop_db(self):
        _log("Ejecutando drop DB...")
        def work():
            try:
                res = bool(self.db.dropear_base_datos(
                    bootstrap_cb=lambda: bootstrap_after_drop(db=self.db, logger=_log)
                ))  # type: ignore
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
            if error or not result:
                _log(f"❌ Drop DB error/result={result}: {error}")
                self._info("❌ Error", f"No se pudo dropear la base.\n{error or ''}".strip(), kind="error")
                return
            try:
                self.db.connect()
                _log("Conexión restablecida tras drop DB.")
            except Exception as e:
                _log(f"⚠️ db.connect tras drop falló: {e}")
            self._info("🗑️ Base eliminada",
                       "La base fue eliminada, reconstruida (bootstrap) y la conexión restablecida.",
                       kind="success")
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
