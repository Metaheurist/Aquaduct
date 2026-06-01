"""Small vector icons for compact toolbar ``QPushButton``s (QSvgRenderer, single stroke color)."""

from __future__ import annotations

import functools
from typing import Literal

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_COLOR = "__COLOR__"

ToolbarIconKind = Literal[
    "folder_plus",
    "duplicate",
    "trash",
    "refresh",
    "pause",
    "play",
    "stop",
    "check",
    "cross",
    "dot",
    "half",
    "warning",
    "info",
    "chevron_right",
    "chevron_down",
    "arrow_left",
    "arrow_right",
    "sparkles",
]

_SVGS: dict[str, str] = {
    "folder_plus": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 10v6"/>
  <path d="M9 13h6"/>
  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
</svg>""",
    "duplicate": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
</svg>""",
    "trash": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="3 6 5 6 21 6"/>
  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
  <line x1="10" y1="11" x2="10" y2="17"/>
  <line x1="14" y1="11" x2="14" y2="17"/>
</svg>""",
    "refresh": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
  <path d="M21 3v5h-5"/>
  <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
  <path d="M3 21v-5h5"/>
</svg>""",
    "pause": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="10" y1="5" x2="10" y2="19"/>
  <line x1="14" y1="5" x2="14" y2="19"/>
</svg>""",
    "play": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="5 3 19 12 5 21 5 3"/>
</svg>""",
    "stop": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="5" y="5" width="14" height="14" rx="3" ry="3"/>
</svg>""",
    "check": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="20 6 9 17 4 12"/>
</svg>""",
    "cross": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <line x1="18" y1="6" x2="6" y2="18"/>
  <line x1="6" y1="6" x2="18" y2="18"/>
</svg>""",
    "dot": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{_COLOR}">
  <circle cx="12" cy="12" r="5"/>
</svg>""",
    "half": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2">
  <circle cx="12" cy="12" r="9"/>
  <path d="M12 3v18" stroke="{_COLOR}" stroke-width="2"/>
  <path d="M12 3a9 9 0 0 1 0 18" fill="{_COLOR}" stroke="none"/>
</svg>""",
    "warning": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
  <line x1="12" y1="9" x2="12" y2="13"/>
  <line x1="12" y1="17" x2="12.01" y2="17"/>
</svg>""",
    "info": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <line x1="12" y1="16" x2="12" y2="12"/>
  <line x1="12" y1="8" x2="12.01" y2="8"/>
</svg>""",
    "chevron_right": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="9 18 15 12 9 6"/>
</svg>""",
    "chevron_down": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="6 9 12 15 18 9"/>
</svg>""",
    "arrow_left": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <line x1="19" y1="12" x2="5" y2="12"/>
  <polyline points="12 19 5 12 12 5"/>
</svg>""",
    "arrow_right": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <line x1="5" y1="12" x2="19" y2="12"/>
  <polyline points="12 5 19 12 12 19"/>
</svg>""",
    "sparkles": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/>
  <path d="M19 14l.75 2.25L22 17l-2.25.75L19 20l-.75-2.25L16 17l2.25-.75L19 14z"/>
</svg>""",
}


def pixmap_toolbar(kind: ToolbarIconKind, color_hex: str, size: int = 16) -> QPixmap:
    """Return a toolbar SVG as a ``QPixmap`` (for labels and inline glyphs)."""
    if kind not in _SVGS:
        return QPixmap()
    return _pixmap_cached(kind, color_hex, int(size))


@functools.lru_cache(maxsize=128)
def _pixmap_cached(kind: str, color_hex: str, size: int) -> QPixmap:
    svg = _SVGS[kind].replace(_COLOR, color_hex)
    renderer = QSvgRenderer(bytes(svg, "utf-8"))
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p)
    p.end()
    return pm


def qicon_toolbar(kind: ToolbarIconKind, color_hex: str, size: int = 22) -> QIcon:
    """Build a ``QIcon`` from a single stroke/fill color (palette accent, muted, text, danger, …)."""
    if kind not in _SVGS:
        return QIcon()
    return QIcon(_pixmap_cached(kind, color_hex, int(size)))
