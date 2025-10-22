# main.py
import flet as ft
from app.views.window_main_view import window_main

# Tema global
from app.config.application.theme_controller import ThemeController

# ✅ Bootstrap principal (nuevo módulo)
from app.config.db.bootstrap_db import bootstrap_db


# -----------------------------
# 🌗 Inicialización de tema + UI
# -----------------------------
def _entrypoint(page: ft.Page):
    """Adjunta la Page al controlador de tema y lanza la ventana principal."""
    ThemeController().attach_page(page)
    return window_main(page)


def iniciar_aplicacion():
    """Punto de entrada principal."""
    # 🧱 Bootstrap de base de datos (preflight + modelos + seeds)
    res = bootstrap_db()  # puedes pasar logger=_print si quieres prefijar
    if not res.get("ok", True):
        print("⚠️ Bootstrap terminó con advertencias/errores:")
        for e in res.get("errors", []):
            print("   -", e)

    print("🚀 Lanzando aplicación...")
    ft.app(target=_entrypoint, assets_dir="assets")


# -----------------------------
# 🧩 Ejecución directa
# -----------------------------
if __name__ == "__main__":
    try:
        iniciar_aplicacion()
    except Exception as e:
        print(f"❌ Error al iniciar la aplicación: {e}")
