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
}


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
