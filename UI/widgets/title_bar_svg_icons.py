"""Vector icons for title-bar outline buttons (QSvgRenderer, theme-colored stroke)."""

from __future__ import annotations

import functools

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# Stroke color placeholder replaced per paint with the resolved foreground color.
_COLOR = "__COLOR__"

_SVGS: dict[str, str] = {
    "save": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
  <polyline points="17 21 17 13 7 13 7 21"/>
  <line x1="7" y1="3" x2="7" y2="8"/>
  <line x1="15" y1="3" x2="15" y2="8"/>
</svg>""",
    "graph": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="18" y1="20" x2="18" y2="10"/>
  <line x1="12" y1="20" x2="12" y2="4"/>
  <line x1="6" y1="20" x2="6" y2="14"/>
</svg>""",
    "help": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
  <line x1="12" y1="17" x2="12.01" y2="17"/>
</svg>""",
    "close": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="18" y1="6" x2="6" y2="18"/>
  <line x1="6" y1="6" x2="18" y2="18"/>
</svg>""",
    # Cylinder (VRAM heap) + sparkles — “purge / clear caches” (Resource usage dialog).
    "purge": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <ellipse cx="12" cy="7" rx="7" ry="3"/>
  <path d="M5 7v5c0 1.66 3.13 3 7 3s7-1.34 7-3V7"/>
  <path d="M5 12v1c0 1.66 3.13 3 7 3s7-1.34 7-3v-1"/>
  <path d="M17 2v2M18 3h-2"/>
  <path d="M19 5l1 1M20 4l-1 1"/>
  <path d="M15 3l1 1M16 2l-1 1"/>
</svg>""",
    # Outward corners — “expand resource charts” (shown in mini mode; click expands).
    "resource_expand": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="9,21 3,21 3,15"/>
  <polyline points="15,21 21,21 21,15"/>
  <polyline points="21,9 21,3 15,3"/>
  <polyline points="3,9 3,3 9,3"/>
</svg>""",
    # Inward corners — “compact resource charts” (shown in expanded mode; click goes mini).
    "resource_compress": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="15,21 21,21 21,15"/>
  <polyline points="9,21 3,21 3,15"/>
  <polyline points="3,9 3,3 9,3"/>
  <polyline points="21,9 21,3 15,3"/>
</svg>""",
}


@functools.lru_cache(maxsize=128)
def _render_pixmap_cached(kind: str, color_hex: str, size: int) -> QPixmap:
    svg = _SVGS[kind].replace(_COLOR, color_hex)
    renderer = QSvgRenderer(bytes(svg, "utf-8"))
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p)
    p.end()
    return pm


def pixmap_for_title_bar_icon(kind: str, fg: QColor, size: int) -> QPixmap:
    """Return a pixmap for the given icon kind, tinted to ``fg`` (typically outline pill foreground)."""
    if kind not in _SVGS:
        return QPixmap()
    hex_rgb = fg.name(QColor.NameFormat.HexRgb)
    return _render_pixmap_cached(kind, hex_rgb, int(size))
