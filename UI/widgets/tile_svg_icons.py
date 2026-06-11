"""SVG icons for option tiles, preset cards, and other visual pickers."""

from __future__ import annotations

import functools
from typing import Literal

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from UI.widgets.toolbar_svg_icons import _SVGS as _TOOLBAR_SVGS
from UI.widgets.toolbar_svg_icons import _pixmap_cached as _toolbar_pixmap_cached

_COLOR = "__COLOR__"

TileIconKind = Literal[
    "news",
    "cartoon",
    "explainer",
    "unhinged",
    "horror",
    "health",
    "nsfw",
    "poster",
    "newspaper",
    "comic",
    "star",
    "phone_vertical",
    "square",
    "landscape",
    "image",
    "images",
    "layout",
    "cloud",
    "cpu",
    "layers",
    "wallet",
    "more",
    "minus",
    "plus",
]

_TILE_SVGS: dict[str, str] = {
    "news": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 5h16v14H4z"/><path d="M8 9h8"/><path d="M8 13h5"/><path d="M8 17h8"/>
</svg>""",
    "cartoon": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="13.5" cy="6.5" r="2.5"/><path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
</svg>""",
    "explainer": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/>
</svg>""",
    "unhinged": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
</svg>""",
    "horror": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/><path d="M8 15s1.5 2 4 2 4-2 4-2"/><path d="M12 2a8 8 0 0 0-8 8v4l2 2h12l2-2v-4a8 8 0 0 0-8-8z"/>
</svg>""",
    "health": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>
</svg>""",
    "nsfw": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
</svg>""",
    "poster": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>
</svg>""",
    "newspaper": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 4h16v16H4z"/><path d="M8 8h8"/><path d="M8 12h8"/><path d="M8 16h5"/>
</svg>""",
    "comic": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
</svg>""",
    "star": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{_COLOR}" stroke="{_COLOR}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
</svg>""",
    "phone_vertical": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="7" y="2" width="10" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>
</svg>""",
    "square": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="4" y="4" width="16" height="16" rx="2"/>
</svg>""",
    "landscape": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2" y="7" width="20" height="10" rx="2"/>
</svg>""",
    "image": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
</svg>""",
    "images": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18 22H4a2 2 0 0 1-2-2V6"/><path d="m22 13-1.296-1.296a2.4 2.4 0 0 0-3.408 0L11 18"/><rect x="6" y="2" width="16" height="16" rx="2"/>
</svg>""",
    "layout": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>
</svg>""",
    "cloud": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>
</svg>""",
    "cpu": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/>
</svg>""",
    "layers": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>
</svg>""",
    "wallet": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15v-7"/>
</svg>""",
    "more": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{_COLOR}">
  <circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>
</svg>""",
    "minus": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2.5" stroke-linecap="round">
  <line x1="5" y1="12" x2="19" y2="12"/>
</svg>""",
    "plus": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{_COLOR}" stroke-width="2.5" stroke-linecap="round">
  <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
</svg>""",
}

_ALL_SVGS = {**_TOOLBAR_SVGS, **_TILE_SVGS}


@functools.lru_cache(maxsize=256)
def _pixmap_cached(kind: str, color_hex: str, size: int) -> QPixmap:
    if kind not in _ALL_SVGS:
        return QPixmap()
    svg = _ALL_SVGS[kind].replace(_COLOR, color_hex)
    renderer = QSvgRenderer(bytes(svg, "utf-8"))
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p)
    p.end()
    return pm


def pixmap_tile(kind: str, color_hex: str, size: int = 28) -> QPixmap:
    """Render a tile/card SVG icon at the given size and color."""
    return _pixmap_cached(kind, color_hex, int(size))


def qicon_tile(kind: str, color_hex: str, size: int = 22) -> QIcon:
    pm = _pixmap_cached(kind, color_hex, int(size))
    return QIcon() if pm.isNull() else QIcon(pm)
