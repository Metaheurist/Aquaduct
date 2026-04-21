"""Title-bar icon buttons with smooth rounded outlines.

Qt Fusion + stylesheet ``border`` + ``border-radius`` on small widgets is rasterized
with visible segmentation at common Windows DPI scales. Painting with
``QPainter.Antialiasing`` and round pen caps yields a continuous stroke.
"""

from __future__ import annotations

from typing import Literal

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QPushButton

Variant = Literal["accent_icon", "muted_icon", "danger"]


class TitleBarOutlineButton(QPushButton):
    def __init__(self, text: str, *, variant: Variant, parent=None) -> None:
        super().__init__(text, parent)
        self._variant: Variant = variant
        self._accent = QColor("#25F4EE")
        self._danger = QColor("#FE2C55")
        self._muted = QColor("#B7B7C2")
        self._text = QColor("#FFFFFF")
        self.setProperty("chrome", "title_outline")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_chrome_colors(self, accent_hex: str, danger_hex: str, muted_hex: str, text_hex: str) -> None:
        self._accent = QColor(accent_hex)
        if not self._accent.isValid():
            self._accent = QColor("#25F4EE")
        self._danger = QColor(danger_hex)
        if not self._danger.isValid():
            self._danger = QColor("#FE2C55")
        self._muted = QColor(muted_hex)
        if not self._muted.isValid():
            self._muted = QColor("#B7B7C2")
        self._text = QColor(text_hex)
        if not self._text.isValid():
            self._text = QColor("#FFFFFF")
        self.update()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        enabled = self.isEnabled()
        painter.save()
        if not enabled:
            painter.setOpacity(0.42)

        full = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 10.0
        path = QPainterPath()
        path.addRoundedRect(full, radius, radius)

        hover = self.underMouse() and enabled
        down = self.isDown() and enabled
        accent, danger = self._accent, self._danger
        muted, text = self._muted, self._text

        if self._variant == "danger":
            core = danger
            fill_a = 0.28 if down else (0.18 if hover else 0.0)
            stroke_a = 0.65 if down else (0.55 if hover else 0.40)
            fg = text if (hover or down) else _soft_danger_fg(danger)
        else:
            core = accent
            fill_a = 0.22 if down else (0.12 if hover else 0.0)
            stroke_a = 0.65 if down else (0.55 if hover else 0.40)
            if self._variant == "muted_icon":
                fg = text if (hover or down) else muted
            else:
                fg = text if (hover or down) else accent

        if fill_a > 0.0:
            fill_c = QColor(core)
            fill_c.setAlphaF(fill_a)
            painter.fillPath(path, fill_c)

        stroke_c = QColor(core)
        stroke_c.setAlphaF(stroke_a)
        pen = QPen(stroke_c)
        pen.setWidthF(1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.strokePath(path, pen)

        painter.setPen(fg)
        painter.setFont(self.font())
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self.text())
        painter.restore()


def _soft_danger_fg(danger: QColor) -> QColor:
    w = QColor("#FFFFFF")
    return QColor(
        int(danger.red() * 0.55 + w.red() * 0.45),
        int(danger.green() * 0.55 + w.green() * 0.45),
        int(danger.blue() * 0.55 + w.blue() * 0.45),
    )


def styled_outline_button(
    text: str,
    variant: Variant,
    *,
    fixed: tuple[int, int] | None = None,
    min_width: int = 96,
    min_height: int = 32,
    branding=None,
) -> TitleBarOutlineButton:
    """Rounded-outline button with theme palette (for dialogs and footers)."""
    from UI.theme import resolve_palette

    b = TitleBarOutlineButton(text, variant=variant)
    if fixed is not None:
        b.setFixedSize(fixed[0], fixed[1])
    else:
        b.setMinimumSize(min_width, min_height)
    pal = resolve_palette(branding)
    b.set_chrome_colors(pal["accent"], pal["danger"], pal["muted"], pal["text"])
    return b


def refresh_open_main_window_title_chrome() -> None:
    """After a live theme QSS refresh, repaint title-bar pills with resolved palette colors."""
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        fn = getattr(w, "_sync_title_bar_outline_colors", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
            return
