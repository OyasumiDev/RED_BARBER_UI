# app/ui/factory/palette_factory.py
from __future__ import annotations
import flet as ft
from typing import Dict, Optional, List
from app.helpers.class_singleton import class_singleton


@class_singleton
class PaletteFactory:
    """
    Abstract Factory + Registry para paletas por área y modo (light/dark).
    - Singleton (via @class_singleton)
    - Global base (marca roja) + overrides por área
    - API inmutable (devuelve copias)
    - Alias de compatibilidad para llaves antiguas
    """

    def __init__(self) -> None:
        # ---------- Paletas GLOBAL (marca roja) ----------
        self._global_light: Dict[str, str] = {
            "PRIMARY":       "#D32F2F",
            "ON_PRIMARY":    "#FFFFFF",
            "ACCENT":        "#C62828",
            "BG_COLOR":      "#FAFAFA",
            "FG_COLOR":      "#111827",
            "CARD_BG":       "#FFFFFF",
            "BTN_BG":        "#F6F7F8",
            "FIELD_BG":      "#F3F4F6",
            "DIVIDER_COLOR": "rgba(17,24,39,0.12)",
            "BORDER_COLOR":  "rgba(17,24,39,0.12)",
            "HOVER_BG":      "rgba(211,47,47,0.08)",
            "ACTIVE_BG":     "rgba(211,47,47,0.12)",
            "ICON_COLOR":    "#111827",
            "SHADOW":        "rgba(17,24,39,0.18)",
            "ERROR":   "#D32F2F",
            "WARNING": "#ED6C02",
            "SUCCESS": "#2E7D32",
            "INFO":    "#0288D1",
            "MUTED":   "#6B7280",
        }

        self._global_dark: Dict[str, str] = {
            "PRIMARY":       "#FF5252",
            "ON_PRIMARY":    "#1B1B1F",
            "ACCENT":        "#EF5350",
            "BG_COLOR":      "#0F1115",
            "FG_COLOR":      "#E5E7EB",
            "CARD_BG":       "#1C1F26",
            "BTN_BG":        "rgba(255,255,255,0.06)",
            "FIELD_BG":      "#101318",
            "DIVIDER_COLOR": "rgba(229,231,235,0.16)",
            "BORDER_COLOR":  "rgba(229,231,235,0.12)",
            "HOVER_BG":      "rgba(255,82,82,0.10)",
            "ACTIVE_BG":     "rgba(255,82,82,0.14)",
            "ICON_COLOR":    "#E5E7EB",
            "SHADOW":        "rgba(0,0,0,0.40)",
            "ERROR":   "#EF9A9A",
            "WARNING": "#FFA000",
            "SUCCESS": "#66BB6A",
            "INFO":    "#81D4FA",
            "MUTED":   "#9CA3AF",
        }

        # ---------- Overrides por ÁREA ----------
        self._areas: Dict[str, Dict[str, Dict[str, str]]] = {
            "navbar": {
                "light": {
                    "BG_COLOR": ft.colors.GREY_50,
                    "ITEM_BG":  ft.colors.GREY_200,
                    "ITEM_FG":  ft.colors.BLACK,
                    "ICON":     ft.colors.BLACK,
                    "ICON_MUTED": ft.colors.GREY_700,
                    "HOVER_BG":  ft.colors.with_opacity(0.06, ft.colors.RED_600),
                    "ACTIVE_BG": ft.colors.RED_500,
                    "ACTIVE_FG": ft.colors.BLACK,
                    "DIVIDER_COLOR": ft.colors.RED_300,
                    "BORDER_COLOR":  ft.colors.with_opacity(0.10, ft.colors.BLACK),
                    "BTN_BG":   ft.colors.GREY_200,
                    "CARD_BG":  ft.colors.GREY_100,
                    "ACCENT":   ft.colors.RED_400,
                },
                "dark": {
                    "BG_COLOR": ft.colors.GREY_900,
                    "ITEM_BG":  ft.colors.GREY_800,
                    "ITEM_FG":  ft.colors.GREY_300,
                    "ICON":     ft.colors.GREY_200,
                    "ICON_MUTED": ft.colors.GREY_600,
                    "HOVER_BG":  ft.colors.with_opacity(0.08, ft.colors.RED_ACCENT_200),
                    "ACTIVE_BG": ft.colors.RED_600,
                    "ACTIVE_FG": ft.colors.BLACK,
                    "DIVIDER_COLOR": ft.colors.with_opacity(0.35, ft.colors.RED_ACCENT_200),
                    "BORDER_COLOR":  ft.colors.with_opacity(0.22, ft.colors.WHITE),
                    "BTN_BG":   ft.colors.GREY_800,
                    "CARD_BG":  "#23262D",
                    "ACCENT":   ft.colors.RED_ACCENT_200,
                },
            },

            "home": {
                "light": {
                    "BG_COLOR": ft.colors.WHITE,
                    "FG_COLOR": ft.colors.BLACK,
                    "CARD_BG":  ft.colors.WHITE,
                    "DIVIDER_COLOR": ft.colors.RED_300,
                    "SECTION_LINE":  ft.colors.RED_300,
                    "TITLE_BG":      ft.colors.RED_600,
                    "TITLE_FG":      ft.colors.WHITE,
                    "SUBTITLE_FG":   ft.colors.GREY_700,
                    "BTN_BG":   ft.colors.GREY_100,
                    "ACCENT":   ft.colors.RED_500,
                    "HOVER_BG": ft.colors.with_opacity(0.06, ft.colors.RED_600),
                    "BORDER_COLOR": ft.colors.with_opacity(0.12, ft.colors.BLACK),
                    "BADGE_BG": ft.colors.RED_50,
                    "BADGE_FG": ft.colors.RED_700,
                },
                "dark": {
                    "BG_COLOR": ft.colors.GREY_900,
                    "FG_COLOR": ft.colors.WHITE,
                    "CARD_BG":  "#23262D",
                    "DIVIDER_COLOR": ft.colors.with_opacity(0.45, ft.colors.RED_ACCENT_200),
                    "SECTION_LINE":  ft.colors.with_opacity(0.45, ft.colors.RED_ACCENT_200),
                    "TITLE_BG":      ft.colors.RED_700,
                    "TITLE_FG":      ft.colors.WHITE,
                    "SUBTITLE_FG":   ft.colors.GREY_300,
                    "BTN_BG":   ft.colors.GREY_800,
                    "ACCENT":   ft.colors.RED_ACCENT_200,
                    "HOVER_BG": ft.colors.with_opacity(0.08, ft.colors.RED_ACCENT_200),
                    "BORDER_COLOR": ft.colors.with_opacity(0.20, ft.colors.WHITE),
                    "BADGE_BG":  ft.colors.with_opacity(0.14, ft.colors.RED_ACCENT_100),
                    "BADGE_FG":  ft.colors.RED_ACCENT_200,
                },
            },

            "trabajadores": {
                "light": {
                    "BG_COLOR":  "#F9FAFB",
                    "CARD_BG":   "#FFFFFF",
                    "HEADER":    "#8B1D1D",
                    "ACCENT":    "#C62828",
                    "ROW_HOVER": "rgba(211,47,47,0.06)",
                    "CHIP_OK_BG":    "#E8F5E9",
                    "CHIP_OK_TXT":   "#2E7D32",
                    "CHIP_OFF_BG":   "#FFF3E0",
                    "CHIP_OFF_TXT":  "#ED6C02",
                },
                "dark": {
                    "BG_COLOR":  "#0F1115",
                    "CARD_BG":   "#1C1F26",
                    "HEADER":    "#FF8A80",
                    "ACCENT":    "#EF5350",
                    "ROW_HOVER": "rgba(255,82,82,0.08)",
                    "CHIP_OK_BG":    "rgba(102,187,106,0.15)",
                    "CHIP_OK_TXT":   "#A5D6A7",
                    "CHIP_OFF_BG":   "rgba(255,160,0,0.15)",
                    "CHIP_OFF_TXT":  "#FFCC80",
                },
            },

            "inventario": {
                "light": {
                    "BG_COLOR":  "#F6F6F7",
                    "CARD_BG":   "#FFFFFF",
                    "HEADER":    "#7A1E1E",
                    "ACCENT":    "#D32F2F",
                    "ROW_HOVER": "rgba(211,47,47,0.05)",
                    "STOCK_LOW_BG":   "#FFEBEE",
                    "STOCK_LOW_TXT":  "#C62828",
                    "STOCK_OK_BG":    "#E8F5E9",
                    "STOCK_OK_TXT":   "#2E7D32",
                    "STOCK_WARN_BG":  "#FFF8E1",
                    "STOCK_WARN_TXT": "#ED6C02",
                },
                "dark": {
                    "BG_COLOR":  "#0F1115",
                    "CARD_BG":   "#1C1F26",
                    "HEADER":    "#FF8A80",
                    "ACCENT":    "#FF5252",
                    "ROW_HOVER": "rgba(255,82,82,0.08)",
                    "STOCK_LOW_BG":   "rgba(239,83,80,0.15)",
                    "STOCK_LOW_TXT":  "#EF9A9A",
                    "STOCK_OK_BG":    "rgba(102,187,106,0.15)",
                    "STOCK_OK_TXT":   "#A5D6A7",
                    "STOCK_WARN_BG":  "rgba(255,160,0,0.15)",
                    "STOCK_WARN_TXT": "#FFCC80",
                },
            },

            # -------- NUEVO: servicios --------
            "servicios": {
                "light": {
                    "BG_COLOR":  "#F9FAFB",
                    "FG_COLOR":  "#111827",
                    "CARD_BG":   "#FFFFFF",
                    "HEADER":    "#7A1E1E",
                    "ACCENT":    "#D32F2F",
                    "BTN_BG":    "#F3F4F6",
                    "FIELD_BG":  "#F3F4F6",
                    "ICON_COLOR": ft.colors.BLACK,

                    "DIVIDER_COLOR": ft.colors.RED_300,
                    "BORDER_COLOR":  ft.colors.with_opacity(0.12, ft.colors.BLACK),
                    "ROW_HOVER":     "rgba(211,47,47,0.06)",
                    "HOVER_BG":      ft.colors.with_opacity(0.06, ft.colors.RED_600),

                    "CHIP_OK_BG":    "#E8F5E9",
                    "CHIP_OK_TXT":   "#2E7D32",
                    "CHIP_OFF_BG":   "#FFF3E0",
                    "CHIP_OFF_TXT":  "#ED6C02",

                    "TYPE_TAG_BG":   "#FFECEE",
                    "TYPE_TAG_TXT":  "#B71C1C",

                    "PRICE_TXT":     "#1F2937",
                    "PRICE_BG":      "#FFF8F8",

                    "TABLE_HEADER_BG": "#FFF1F1",
                    "TABLE_HEADER_TXT":"#7A1E1E",

                    "BADGE_BG":  ft.colors.RED_50,
                    "BADGE_FG":  ft.colors.RED_700,
                },
                "dark": {
                    "BG_COLOR":  "#0F1115",
                    "FG_COLOR":  "#E5E7EB",
                    "CARD_BG":   "#1C1F26",
                    "HEADER":    "#FF8A80",
                    "ACCENT":    "#EF5350",
                    "BTN_BG":    ft.colors.GREY_800,
                    "FIELD_BG":  "#101318",
                    "ICON_COLOR": ft.colors.GREY_300,

                    "DIVIDER_COLOR": ft.colors.with_opacity(0.45, ft.colors.RED_ACCENT_200),
                    "BORDER_COLOR":  ft.colors.with_opacity(0.20, ft.colors.WHITE),
                    "ROW_HOVER":     "rgba(255,82,82,0.08)",
                    "HOVER_BG":      ft.colors.with_opacity(0.08, ft.colors.RED_ACCENT_200),

                    "CHIP_OK_BG":    "rgba(102,187,106,0.15)",
                    "CHIP_OK_TXT":   "#A5D6A7",
                    "CHIP_OFF_BG":   "rgba(255,160,0,0.15)",
                    "CHIP_OFF_TXT":  "#FFCC80",

                    "TYPE_TAG_BG":   "rgba(255,138,128,0.16)",
                    "TYPE_TAG_TXT":  "#FFCDD2",

                    "PRICE_TXT":     "#E5E7EB",
                    "PRICE_BG":      "rgba(255,255,255,0.04)",

                    "TABLE_HEADER_BG": "#1A1214",
                    "TABLE_HEADER_TXT":"#FFCDD2",

                    "BADGE_BG":  ft.colors.with_opacity(0.14, ft.colors.RED_ACCENT_100),
                    "BADGE_FG":  ft.colors.RED_ACCENT_200,
                },
            },

            # -------- NUEVO: cortes / pagos --------
            "cortes": {
                "light": {
                    "BG_COLOR":  "#F9FAFB",
                    "FG_COLOR":  "#111827",
                    "CARD_BG":   "#FFFFFF",
                    "HEADER":    "#7A1E1E",
                    "ACCENT":    "#D32F2F",
                    "BTN_BG":    "#F3F4F6",
                    "FIELD_BG":  "#F3F4F6",
                    "ICON_COLOR": ft.colors.BLACK,

                    "DIVIDER_COLOR": ft.colors.RED_300,
                    "BORDER_COLOR":  ft.colors.with_opacity(0.12, ft.colors.BLACK),
                    "ROW_HOVER":     "rgba(211,47,47,0.06)",
                    "HOVER_BG":      ft.colors.with_opacity(0.06, ft.colors.RED_600),

                    # Chips de estados / etiquetas
                    "CHIP_OK_BG":    "#E8F5E9",
                    "CHIP_OK_TXT":   "#2E7D32",
                    "CHIP_OFF_BG":   "#FFF3E0",
                    "CHIP_OFF_TXT":  "#ED6C02",

                    # Dinero / cálculo
                    "PRICE_TXT":     "#1F2937",
                    "PRICE_BG":      "#FFF8F8",
                    "PROMO_BADGE_BG": ft.colors.RED_50,
                    "PROMO_BADGE_FG": ft.colors.RED_700,

                    # Cabecera tabla
                    "TABLE_HEADER_BG": "#FFF1F1",
                    "TABLE_HEADER_TXT":"#7A1E1E",
                },
                "dark": {
                    "BG_COLOR":  "#0F1115",
                    "FG_COLOR":  "#E5E7EB",
                    "CARD_BG":   "#1C1F26",
                    "HEADER":    "#FF8A80",
                    "ACCENT":    "#EF5350",
                    "BTN_BG":    ft.colors.GREY_800,
                    "FIELD_BG":  "#101318",
                    "ICON_COLOR": ft.colors.GREY_300,

                    "DIVIDER_COLOR": ft.colors.with_opacity(0.45, ft.colors.RED_ACCENT_200),
                    "BORDER_COLOR":  ft.colors.with_opacity(0.20, ft.colors.WHITE),
                    "ROW_HOVER":     "rgba(255,82,82,0.08)",
                    "HOVER_BG":      ft.colors.with_opacity(0.08, ft.colors.RED_ACCENT_200),

                    "CHIP_OK_BG":    "rgba(102,187,106,0.15)",
                    "CHIP_OK_TXT":   "#A5D6A7",
                    "CHIP_OFF_BG":   "rgba(255,160,0,0.15)",
                    "CHIP_OFF_TXT":  "#FFCC80",

                    "PRICE_TXT":     "#E5E7EB",
                    "PRICE_BG":      "rgba(255,255,255,0.04)",
                    "PROMO_BADGE_BG": ft.colors.with_opacity(0.14, ft.colors.RED_ACCENT_100),
                    "PROMO_BADGE_FG": ft.colors.RED_ACCENT_200,

                    "TABLE_HEADER_BG": "#1A1214",
                    "TABLE_HEADER_TXT":"#FFCDD2",
                },
            },

            # -------- NUEVO: db-settings --------
            "db-settings": {
                "light": {
                    "BG_COLOR":  "#F9FAFB",
                    "FG_COLOR":  "#111827",
                    "CARD_BG":   "#FFFFFF",
                    "DIVIDER_COLOR": ft.colors.RED_300,
                    "BORDER_COLOR":  ft.colors.with_opacity(0.12, ft.colors.BLACK),
                    "BTN_BG":   ft.colors.GREY_100,
                    "HOVER_BG": ft.colors.with_opacity(0.06, ft.colors.RED_600),
                    "ACCENT":   ft.colors.RED_500,
                    "ICON_COLOR": ft.colors.BLACK,
                    "TITLE_BG": ft.colors.RED_600,
                    "TITLE_FG": ft.colors.WHITE,
                    "BADGE_BG": ft.colors.RED_50,
                    "BADGE_FG": ft.colors.RED_700,
                },
                "dark": {
                    "BG_COLOR":  "#0F1115",
                    "FG_COLOR":  "#E5E7EB",
                    "CARD_BG":   "#1C1F26",
                    "DIVIDER_COLOR": ft.colors.with_opacity(0.45, ft.colors.RED_ACCENT_200),
                    "BORDER_COLOR":  ft.colors.with_opacity(0.20, ft.colors.WHITE),
                    "BTN_BG":   ft.colors.GREY_800,
                    "HOVER_BG": ft.colors.with_opacity(0.08, ft.colors.RED_ACCENT_200),
                    "ACCENT":   ft.colors.RED_ACCENT_200,
                    "ICON_COLOR": ft.colors.GREY_300,
                    "TITLE_BG": ft.colors.RED_700,
                    "TITLE_FG": ft.colors.WHITE,
                    "BADGE_BG": ft.colors.with_opacity(0.14, ft.colors.RED_ACCENT_100),
                    "BADGE_FG": ft.colors.RED_ACCENT_200,
                },
            },

            # -------- ya existente: users-settings --------
            "users-settings": {
                "light": {
                    "BG_COLOR":  "#F9FAFB",
                    "CARD_BG":   "#FFFFFF",
                    "DIVIDER_COLOR": ft.colors.RED_300,
                    "BORDER_COLOR":  ft.colors.with_opacity(0.12, ft.colors.BLACK),
                    "BTN_BG":   ft.colors.GREY_100,
                    "HOVER_BG": ft.colors.with_opacity(0.06, ft.colors.RED_600),
                    "ACCENT":   ft.colors.RED_500,
                    "HEADER":    "#7A1E1E",
                    "ROW_HOVER": "rgba(211,47,47,0.05)",
                    "BADGE_BG":  ft.colors.RED_50,
                    "BADGE_FG":  ft.colors.RED_700,
                    "ICON_COLOR": ft.colors.BLACK,
                },
                "dark": {
                    "BG_COLOR":  "#0F1115",
                    "CARD_BG":   "#1C1F26",
                    "DIVIDER_COLOR": ft.colors.with_opacity(0.45, ft.colors.RED_ACCENT_200),
                    "BORDER_COLOR":  ft.colors.with_opacity(0.20, ft.colors.WHITE),
                    "BTN_BG":   ft.colors.GREY_800,
                    "HOVER_BG": ft.colors.with_opacity(0.08, ft.colors.RED_ACCENT_200),
                    "ACCENT":   ft.colors.RED_ACCENT_200,
                    "HEADER":    "#FF8A80",
                    "ROW_HOVER": "rgba(255,82,82,0.08)",
                    "BADGE_BG":  ft.colors.with_opacity(0.14, ft.colors.RED_ACCENT_100),
                    "BADGE_FG":  ft.colors.RED_ACCENT_200,
                    "ICON_COLOR": ft.colors.GREY_300,
                },
            },

            "login": {
                "light": {"BG_COLOR": "#FAFAFA", "CARD_BG": "#FFFFFF"},
                "dark":  {"BG_COLOR": "#0F1115", "CARD_BG": "#1C1F26"},
            },
            "content": {
                "light": {"BG_COLOR": "#FAFAFA", "CARD_BG": "#FFFFFF"},
                "dark":  {"BG_COLOR": "#0F1115", "CARD_BG": "#1C1F26"},
            },
            "appbar": {
                "light": {"BG_COLOR": "#FFF1F1"},
                "dark":  {"BG_COLOR": "#1A1214"},
            },
            "card": {
                "light": {"BG_COLOR": "#FFFFFF", "BORDER_COLOR": "rgba(17,24,39,0.12)"},
                "dark":  {"BG_COLOR": "#1C1F26", "BORDER_COLOR": "rgba(229,231,235,0.12)"},
            },
            "menu": {
                "light": {"BTN_BG": "#FFFFFF", "HOVER_BG": "rgba(211,47,47,0.08)", "ACTIVE_BG": "rgba(211,47,47,0.12)"},
                "dark":  {"BTN_BG": "rgba(255,255,255,0.04)", "HOVER_BG": "rgba(255,82,82,0.10)", "ACTIVE_BG": "rgba(255,82,82,0.14)"},
            },
            "control_bar": {
                "light": {"BTN_BG": "#F3F4F6"},
                "dark":  {"BTN_BG": "rgba(255,255,255,0.06)"},
            },
            "quick_nav": {
                "light": {"BTN_BG": "#FFFFFF", "HOVER_BG": "rgba(211,47,47,0.08)"},
                "dark":  {"BTN_BG": "rgba(255,255,255,0.04)", "HOVER_BG": "rgba(255,82,82,0.10)"},
            },
        }

        # ---- Aliases opcionales/áreas equivalentes ----
        self.register_area_palette(
            "usuarios-settings",
            light=self._areas["users-settings"]["light"],
            dark=self._areas["users-settings"]["dark"],
        )
        self.register_area_palette(
            "usuarios-ajustes",
            light=self._areas["users-settings"]["light"],
            dark=self._areas["users-settings"]["dark"],
        )

        # Aliases para db-settings
        for alias in ("settings-db", "database-settings", "ajustes-db", "ajustes-database", "settings"):
            self.register_area_palette(
                alias,
                light=self._areas["db-settings"]["light"],
                dark=self._areas["db-settings"]["dark"],
            )

        # Alias para servicios
        self.register_area_palette(
            "services",
            light=self._areas["servicios"]["light"],
            dark=self._areas["servicios"]["dark"],
        )

        # ✅ Aliases para cortes
        for alias in ("pagos", "cortes-pagos"):
            self.register_area_palette(
                alias,
                light=self._areas["cortes"]["light"],
                dark=self._areas["cortes"]["dark"],
            )

    # ---------- API ----------
    @staticmethod
    def _mode(dark: bool) -> str:
        return "dark" if dark else "light"

    def get_global_palette(self, dark: bool) -> Dict[str, str]:
        return dict(self._global_dark if dark else self._global_light)

    def get_area_palette(self, area: Optional[str], dark: bool) -> Dict[str, str]:
        if not area:
            return {}
        a = area.lower()
        if a not in self._areas:
            return {}
        return dict(self._areas[a][self._mode(dark)])

    def _apply_aliases(self, palette: Dict[str, str]) -> Dict[str, str]:
        p = dict(palette)
        p.setdefault("PRIMARY_COLOR", p.get("PRIMARY"))
        p.setdefault("PRIMARY", p.get("PRIMARY_COLOR"))
        p.setdefault("ON_PRIMARY_COLOR", p.get("ON_PRIMARY"))
        p.setdefault("ON_PRIMARY", p.get("ON_PRIMARY_COLOR"))
        if "BORDER" not in p and "BORDER_COLOR" in p:
            p["BORDER"] = p["BORDER_COLOR"]
        if "BORDER_COLOR" not in p and "BORDER" in p:
            p["BORDER_COLOR"] = p["BORDER"]
        if "DIVIDER" not in p and "DIVIDER_COLOR" in p:
            p["DIVIDER"] = p["DIVIDER_COLOR"]
        if "DIVIDER_COLOR" not in p and "DIVIDER" in p:
            p["DIVIDER_COLOR"] = p["DIVIDER"]
        if "HOVER" not in p and "HOVER_BG" in p:
            p["HOVER"] = p["HOVER_BG"]
        if "HOVER_BG" not in p and "HOVER" in p:
            p["HOVER_BG"] = p["HOVER"]
        if "BTN_BG" not in p and "ITEM_BG" in p:
            p["BTN_BG"] = p["ITEM_BG"]
        p.setdefault("FG_COLOR", "#111827")
        p.setdefault("CARD_BG", p.get("BG_COLOR"))
        return p

    def get_colors(self, area: Optional[str], dark: bool) -> Dict[str, str]:
        base = self.get_global_palette(dark)
        area_over = self.get_area_palette(area, dark)
        base.update(area_over)
        return self._apply_aliases(base)

    def color(self, key: str, *, area: Optional[str] = None, dark: bool = False, default: Optional[str] = None):
        return self.get_colors(area, dark).get(key, default)

    def register_area_palette(self, area: str, *, light: Optional[Dict[str, str]] = None, dark: Optional[Dict[str, str]] = None, overwrite: bool = False) -> None:
        area = area.lower()
        if area not in self._areas or overwrite:
            self._areas[area] = {"light": {}, "dark": {}}
        if light:
            self._areas[area]["light"].update(light)
        if dark:
            self._areas[area]["dark"].update(dark)

    def set_global_palettes(self, *, light: Optional[Dict[str, str]] = None, dark: Optional[Dict[str, str]] = None, merge: bool = True) -> None:
        if light:
            self._global_light = (self._global_light | light) if merge else dict(light)
        if dark:
            self._global_dark = (self._global_dark | dark) if merge else dict(dark)

    def list_areas(self) -> List[str]:
        return sorted(self._areas.keys())
