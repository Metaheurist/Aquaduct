"""Pill on/off switch — drop-in QCheckBox replacement with custom paint."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QCheckBox, QSizePolicy, QStyle, QStyleOptionButton

from UI.theme import token


def _color_alpha(hex_color: str, alpha: float) -> QColor:
    c = QColor(hex_color)
    if not c.isValid():
        c = QColor("#25F4EE")
    c.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return c


class ThemedSwitch(QCheckBox):
    """
    Animated pill switch. API-compatible with ``QCheckBox`` (``isChecked``, ``setChecked``,
    ``toggled``, ``stateChanged``, ``setToolTip``, ``setEnabled``).
    """

    _TRACK_W = 44
    _TRACK_H = 24
    _KNOB_MARGIN = 3
    _KNOB_D = _TRACK_H - 2 * _KNOB_MARGIN

    def __init__(self, text: str = "", *, parent=None) -> None:
        super().__init__(text, parent)
        self._knob_x = float(self._KNOB_MARGIN)
        self._anim: QPropertyAnimation | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            "QCheckBox { spacing: 8px; color: #E8E8EE; font-size: 13px; }"
            "QCheckBox::indicator { width: 0px; height: 0px; border: none; }"
        )

    def _target_knob_x(self) -> float:
        if self.isChecked():
            return float(self._TRACK_W - self._KNOB_MARGIN - self._KNOB_D)
        return float(self._KNOB_MARGIN)

    def _animate_to(self, checked: bool) -> None:
        target = self._target_knob_x() if checked else float(self._KNOB_MARGIN)
        if self._anim is not None:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"knobX")
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(target)
        self._anim.valueChanged.connect(lambda _: self.update())
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # noqa: FBT001
        was = self.isChecked()
        super().setChecked(checked)
        if was != checked:
            self._animate_to(checked)
        else:
            self._knob_x = self._target_knob_x()
            self.update()

    def nextCheckState(self) -> None:
        super().nextCheckState()
        self._animate_to(self.isChecked())

    def get_knob_x(self) -> float:
        return self._knob_x

    def set_knob_x(self, value: float) -> None:
        self._knob_x = float(value)
        self.update()

    knobX = pyqtProperty(float, get_knob_x, set_knob_x)

    def sizeHint(self):  # noqa: ANN201
        from PyQt6.QtCore import QSize

        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        h = max(self._TRACK_H, fm.height())
        w = self._TRACK_W + (8 + text_w if text_w else 0)
        return QSize(w, h)

    def paintEvent(self, event) -> None:  # noqa: ANN001, ARG002
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        accent = token("accent", "#25F4EE")
        off_bg = token("control_bg", "#121218")
        checked = self.isChecked()
        enabled = self.isEnabled()

        track_x = 0
        track_y = (self.height() - self._TRACK_H) // 2
        if self.text():
            track_x = 0
            text_x = self._TRACK_W + 8
            text_y = (self.height() + fm_ascent_descent(self)) // 2
            color = "#E8E8EE" if enabled else "#6A6A78"
            painter.setPen(QPen(QColor(color)))
            painter.drawText(text_x, text_y, self.text())
        else:
            track_x = max(0, (self.width() - self._TRACK_W) // 2)

        track_rect = QRectF(
            float(track_x),
            float(track_y),
            float(self._TRACK_W),
            float(self._TRACK_H),
        )
        if checked and enabled:
            painter.setBrush(_color_alpha(accent, 0.36))
        elif enabled:
            painter.setBrush(QColor(off_bg))
        else:
            painter.setBrush(_color_alpha(off_bg, 0.65))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track_rect, 12.0, 12.0)

        knob_x = track_x + self._knob_x
        knob_y = track_y + self._KNOB_MARGIN
        knob_color = "#FFFFFF" if enabled else "#9A9AA8"
        painter.setBrush(QColor(knob_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QRectF(knob_x, float(knob_y), float(self._KNOB_D), float(self._KNOB_D))
        )

    def hitButton(self, pos) -> bool:  # noqa: ANN001
        """Whole widget is clickable (indicator is hidden)."""
        return self.rect().contains(pos)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self._knob_x = self._target_knob_x()


def fm_ascent_descent(widget: QCheckBox) -> int:
    fm = QFontMetrics(widget.font())
    return fm.ascent() - fm.descent() // 2
