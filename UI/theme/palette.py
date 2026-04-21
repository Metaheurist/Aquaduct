"""Qt stylesheet + palette resolution utilities."""

from __future__ import annotations

import re
from typing import TypedDict

from src.core.config import BrandingSettings


class Palette(TypedDict):
    bg: str
    panel: str
    surface: str
    card: str
    control_bg: str
    border: str
    text: str
    muted: str
    accent: str
    danger: str


QSS_TEMPLATE = r"""
QWidget {{ background: {bg}; color: {text}; font-family: "Segoe UI", "Arial"; font-size: 12px; }}
/* QLabel subclasses QWidget; the rule above would paint every label with {bg}, so text looks like black bars on
   section cards (card color is different). Keep labels visually transparent so the parent/card shows through. */
QLabel {{ background-color: transparent; }}
QDialog#FramelessDialogShell {{
  background: {panel};
  border: 1px solid {border};
  border-radius: 14px;
}}
QTabWidget::tab-bar {{
  /* Nudge tabs right so the first tab aligns with the pane below (avoids left overhang vs rounded content). */
  left: 10px;
}}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 14px; padding: 8px; background: {panel}; }}
QFrame#SettingsSectionCard {{
  background: {card};
  border: 1px solid {border};
  border-radius: 12px;
}}
/* Slightly lift inputs inside cards so nested controls don’t read as a second heavy slab on {card}. */
QFrame#SettingsSectionCard QComboBox,
QFrame#SettingsSectionCard QLineEdit,
QFrame#SettingsSectionCard QTextEdit,
QFrame#SettingsSectionCard QPlainTextEdit,
QFrame#SettingsSectionCard QAbstractSpinBox {{
  background-color: rgba(255, 255, 255, 0.06);
}}
QTabBar::tab {{ background: {control_bg}; color: {muted}; padding: 10px 14px; margin: 6px 6px 0 0;
               border-top-left-radius: 14px; border-top-right-radius: 14px; border: 1px solid {border}; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 3px solid {accent}; }}
QLineEdit, QTextEdit, QPlainTextEdit, QListWidget {{
  background: {control_bg}; border: 1px solid {border}; border-radius: 12px; padding: 8px; color: {text};
  min-height: 30px;
}}
QLineEdit::placeholder {{
  color: {muted};
}}
QAbstractSpinBox, QSpinBox {{
  background: {control_bg}; border: 1px solid {border}; border-radius: 12px; color: {text};
  min-height: 32px; padding: 4px 8px; padding-right: 22px;
}}
QSpinBox QLineEdit {{
  color: {text}; background: {control_bg}; border: none; padding: 2px 4px; min-height: 22px;
  selection-background-color: {accent}; selection-color: {panel};
}}
QSpinBox::up-button, QSpinBox::down-button {{
  width: 18px; border-left: 1px solid {border}; background: {control_bg};
  border-top-right-radius: 10px; border-bottom-right-radius: 10px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {panel}; }}
QComboBox {{
  background: {control_bg}; border: 1px solid {border}; border-radius: 12px; color: {text};
  min-height: 32px; padding: 6px 10px; padding-right: 28px;
}}
QComboBox QAbstractItemView {{
  background: {control_bg}; color: {text}; border: 1px solid {border}; border-radius: 10px;
  outline: none; padding: 4px; selection-background-color: {accent}; selection-color: {panel};
}}
QComboBox::drop-down {{
  border: none; width: 26px; background: transparent;
  border-top-right-radius: 12px; border-bottom-right-radius: 12px;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QListWidget:focus, QSpinBox:focus, QComboBox:focus {{
  border: 1px solid {accent};
}}
QPushButton {{
  background: {control_bg}; border: 1px solid {border}; border-radius: 12px; padding: 10px 12px; color: {text};
  font-weight: 600;
}}
QPushButton:hover {{ border: 1px solid {accent}; }}
QPushButton:pressed {{ border: 1px solid {danger}; }}
QPushButton[buttonRole="secondary"] {{
  background: {panel}; color: {text}; border: 1px solid {border}; border-radius: 10px;
  padding: 8px 14px; font-weight: 700; min-height: 26px;
}}
QPushButton[buttonRole="secondary"]:hover {{
  background: {control_bg}; border: 1px solid {accent};
}}
QPushButton[buttonRole="secondary"]:pressed {{ border: 1px solid {danger}; }}
QPushButton#primary {{ background: {accent}; color: {panel}; border: 1px solid {accent}; font-weight: 600; }}
QPushButton#danger {{ background: {danger}; color: {text}; border: 1px solid {danger}; font-weight: 600; }}
/* Frameless ✕, download popups, and main-window title pills use TitleBarOutlineButton (custom paint); strip QSS borders so Fusion does not rasterize dotted arcs. */
QPushButton[chrome="title_outline"] {{
  border: none;
  background: transparent;
  padding: 4px 10px;
  font-weight: 800;
}}
QCheckBox {{ spacing: 10px; color: {text}; font-weight: 600; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px; border: 1px solid {border}; background: {control_bg}; }}
QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}
""".lstrip()


PRESET_PALETTES: dict[str, Palette] = {
    "default": {
        "bg": "#0F0F10",
        "panel": "#0B0B0F",
        "surface": "#1A1A22",
        "card": "#1E1E28",
        "control_bg": "#15151B",
        "border": "#23232B",
        "text": "#FFFFFF",
        "muted": "#B7B7C2",
        "accent": "#25F4EE",
        "danger": "#FE2C55",
    },
    # Alias for compatibility / user expectations
    "tiktok": {
        "bg": "#0F0F10",
        "panel": "#0B0B0F",
        "surface": "#1A1A22",
        "card": "#1E1E28",
        "control_bg": "#15151B",
        "border": "#23232B",
        "text": "#FFFFFF",
        "muted": "#B7B7C2",
        "accent": "#25F4EE",
        "danger": "#FE2C55",
    },
    "ocean": {
        "bg": "#07161C",
        "panel": "#061016",
        "surface": "#0F2832",
        "card": "#12313D",
        "control_bg": "#0D2029",
        "border": "#143541",
        "text": "#EAFBFF",
        "muted": "#A6C8D3",
        "accent": "#2BE6FF",
        "danger": "#FF4D6D",
    },
    "sunset": {
        "bg": "#140B10",
        "panel": "#10070C",
        "surface": "#2A1420",
        "card": "#311726",
        "control_bg": "#221018",
        "border": "#3A1A2A",
        "text": "#FFF0F3",
        "muted": "#D9B8C2",
        "accent": "#FFB703",
        "danger": "#FF006E",
    },
    "mono": {
        "bg": "#0D0D0D",
        "panel": "#0A0A0A",
        "surface": "#181818",
        "card": "#1D1D1D",
        "control_bg": "#141414",
        "border": "#2A2A2A",
        "text": "#FFFFFF",
        "muted": "#C7C7C7",
        "accent": "#FFFFFF",
        "danger": "#FF4D4D",
    },
    "forest": {
        "bg": "#0A120E",
        "panel": "#0C1610",
        "surface": "#142A1E",
        "card": "#1A3328",
        "control_bg": "#121F18",
        "border": "#2A4A38",
        "text": "#F0FFF4",
        "muted": "#9CB8A8",
        "accent": "#6EE7B7",
        "danger": "#F87171",
    },
    "lavender": {
        "bg": "#0E0A14",
        "panel": "#0C0812",
        "surface": "#1A1424",
        "card": "#221A2E",
        "control_bg": "#151020",
        "border": "#2D2440",
        "text": "#F5F0FF",
        "muted": "#B8A8C8",
        "accent": "#C4B5FD",
        "danger": "#FB7185",
    },
    "ember": {
        "bg": "#0F0A08",
        "panel": "#0C0706",
        "surface": "#261A14",
        "card": "#301F18",
        "control_bg": "#1A1210",
        "border": "#403028",
        "text": "#FFF5F0",
        "muted": "#C9A89A",
        "accent": "#FF6B35",
        "danger": "#E11D48",
    },
    "slate": {
        "bg": "#0C0E12",
        "panel": "#0A0C10",
        "surface": "#161B22",
        "card": "#1C232D",
        "control_bg": "#131820",
        "border": "#2D3748",
        "text": "#F1F5F9",
        "muted": "#94A3B8",
        "accent": "#38BDF8",
        "danger": "#F43F5E",
    },
    "rose": {
        "bg": "#10080C",
        "panel": "#0C0608",
        "surface": "#24141C",
        "card": "#2E1822",
        "control_bg": "#1A1012",
        "border": "#3D243A",
        "text": "#FFF1F5",
        "muted": "#D4A5B0",
        "accent": "#FB7185",
        "danger": "#E11D48",
    },
    "amber": {
        "bg": "#0F0A08",
        "panel": "#0C0808",
        "surface": "#221A08",
        "card": "#2A200C",
        "control_bg": "#181008",
        "border": "#3D3418",
        "text": "#FFFBF0",
        "muted": "#C4B59A",
        "accent": "#FBBF24",
        "danger": "#EF4444",
    },
    "nord": {
        "bg": "#0D1117",
        "panel": "#0C1018",
        "surface": "#1A222E",
        "card": "#1E2632",
        "control_bg": "#151B24",
        "border": "#2E3440",
        "text": "#ECEFF4",
        "muted": "#9CA8B8",
        "accent": "#88C0D0",
        "danger": "#BF616A",
    },
    "dracula": {
        "bg": "#0E0E12",
        "panel": "#0A0A0E",
        "surface": "#1A1A22",
        "card": "#22222E",
        "control_bg": "#18181E",
        "border": "#2E2E3A",
        "text": "#F8F8F2",
        "muted": "#B8B8C8",
        "accent": "#BD93F9",
        "danger": "#FF5555",
    },
}


_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _normalize_hex(value: str, fallback: str) -> str:
    s = str(value or "").strip()
    if not s:
        return fallback
    if not _HEX_RE.match(s):
        return fallback
    if not s.startswith("#"):
        s = "#" + s
    return s.upper()


def resolve_palette(branding: BrandingSettings | None) -> Palette:
    """
    Returns a concrete palette. If branding is None or theme is disabled, uses defaults.
    """
    base = dict(PRESET_PALETTES.get("default", PRESET_PALETTES["tiktok"]))
    if not branding or not getattr(branding, "theme_enabled", False):
        return base  # type: ignore[return-value]

    preset_id = str(getattr(branding, "palette_id", "default") or "default").strip().lower()
    preset = PRESET_PALETTES.get(preset_id, PRESET_PALETTES["default"])
    base.update(preset)

    def apply_if(enabled: bool, key: str, value: str) -> None:
        if enabled:
            base[key] = _normalize_hex(value, base[key])

    apply_if(bool(getattr(branding, "bg_enabled", False)), "bg", str(getattr(branding, "bg_hex", "")))
    apply_if(bool(getattr(branding, "panel_enabled", False)), "panel", str(getattr(branding, "panel_hex", "")))
    apply_if(bool(getattr(branding, "text_enabled", False)), "text", str(getattr(branding, "text_hex", "")))
    apply_if(bool(getattr(branding, "muted_enabled", False)), "muted", str(getattr(branding, "muted_hex", "")))
    apply_if(bool(getattr(branding, "accent_enabled", False)), "accent", str(getattr(branding, "accent_hex", "")))
    apply_if(bool(getattr(branding, "danger_enabled", False)), "danger", str(getattr(branding, "danger_hex", "")))

    # Keep control_bg/border consistent-ish with bg/panel if user overrides heavily.
    # If user customizes bg/panel but not control_bg, keep preset control_bg.
    return base  # type: ignore[return-value]


def build_qss(palette: Palette) -> str:
    return QSS_TEMPLATE.format(**palette)


# Back-compat constant used by existing code.
TIKTOK_QSS = build_qss(resolve_palette(None))
