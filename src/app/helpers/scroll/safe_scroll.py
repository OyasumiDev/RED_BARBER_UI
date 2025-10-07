from threading import Timer


class SafeScrollInvoker:
    @staticmethod
    def scroll_to_bottom(page, key="bottom-anchor", delay=0.1):
        def hacer_scroll():
            try:
                if hasattr(page, "scroll_to") and page.views and page.views[-1] == page:
                    page.scroll_to(key=key, duration=300)
                    page.update()
                else:
                    print("⏳ View aún no está activa o método no disponible. No se hace scroll.")
            except Exception as e:
                print(f"⚠️ Error al hacer scroll: {e}")

        Timer(delay, hacer_scroll).start()

    @staticmethod
    def scroll_to_group_anchor(page, group_id: str, delay=0.1):
        def hacer_scroll():
            try:
                if hasattr(page, "scroll_to") and page.views and page.views[-1] == page:
                    page.scroll_to(key=group_id, duration=300)
                    page.update()
                else:
                    print(f"⏳ View aún no está activa o método no disponible. No se hace scroll al grupo '{group_id}'.")
            except Exception as e:
                print(f"⚠️ Error al hacer scroll al grupo '{group_id}': {e}")

        Timer(delay, hacer_scroll).start()
