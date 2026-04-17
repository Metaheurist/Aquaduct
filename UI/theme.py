"""Qt stylesheet + palette resolution utilities."""

from __future__ import annotations

import re
from typing import TypedDict

from src.config import BrandingSettings


class Palette(TypedDict):
    bg: str
    panel: str
    control_bg: str
    border: str
    text: str
    muted: str
    accent: str
    danger: str


QSS_TEMPLATE = r"""
QWidget {{ background: {bg}; color: {text}; font-family: "Segoe UI", "Arial"; font-size: 12px; }}
QDialog#FramelessDialogShell {{
  background: {panel};
  border: 1px solid {border};
  border-radius: 14px;
}}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 14px; padding: 8px; background: {panel}; }}
QTabBar::tab {{ background: {control_bg}; color: {muted}; padding: 10px 14px; margin: 6px 6px 0 0;
               border-top-left-radius: 14px; border-top-right-radius: 14px; border: 1px solid {border}; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 3px solid {accent}; }}
QLineEdit, QTextEdit, QPlainTextEdit, QListWidget {{
  background: {control_bg}; border: 1px solid {border}; border-radius: 12px; padding: 8px; color: {text};
  min-height: 30px;
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
}}
QPushButton:hover {{ border: 1px solid {accent}; }}
QPushButton:pressed {{ border: 1px solid {danger}; }}
QPushButton#primary {{ background: {accent}; color: {panel}; border: 1px solid {accent}; font-weight: 600; }}
QPushButton#danger {{ background: {danger}; color: {text}; border: 1px solid {danger}; font-weight: 600; }}
QPushButton#closeBtn {{
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;
  color: #FF6B8A;
  font-weight: 800;
  padding: 4px 10px;
}}
QPushButton#closeBtn:hover {{ background: rgba(254, 44, 85, 0.18); border: 1px solid rgba(254, 44, 85, 0.35); color: {text}; }}
QPushButton#closeBtn:pressed {{ background: rgba(254, 44, 85, 0.28); }}
QPushButton#saveBtn {{
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;
  color: {accent};
  font-weight: 800;
  padding: 4px 10px;
}}
QPushButton#saveBtn:hover {{ background: rgba(37, 244, 238, 0.12); border: 1px solid rgba(37, 244, 238, 0.30); color: {text}; }}
QPushButton#saveBtn:pressed {{ background: rgba(37, 244, 238, 0.22); }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px; border: 1px solid {border}; background: {control_bg}; }}
QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}
""".lstrip()


PRESET_PALETTES: dict[str, Palette] = {
    "default": {
        "bg": "#0F0F10",
        "panel": "#0B0B0F",
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
        "control_bg": "#141414",
        "border": "#2A2A2A",
        "text": "#FFFFFF",
        "muted": "#C7C7C7",
        "accent": "#FFFFFF",
        "danger": "#FF4D4D",
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
