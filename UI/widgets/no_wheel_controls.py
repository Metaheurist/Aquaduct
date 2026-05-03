"""Qt widgets that ignore the mouse wheel so page/scroll areas scroll instead of changing values."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QSlider, QSpinBox

# Horizontal sliders with this object name get high-contrast “filled track” styling (Model tab quant).
QUANT_ACCENT_SLIDER_OBJECT_NAME = "QuantAccentSlider"

_QUANT_ACCENT_SLIDER_QSS = """
QSlider#QuantAccentSlider::groove:horizontal {
    border: 1px solid rgba(100, 120, 145, 0.85);
    height: 10px;
    background: rgba(22, 28, 38, 0.98);
    border-radius: 5px;
    margin: 4px 0;
}
/* Left of thumb: grows with value - brighter/more saturated as more track is “filled”. */
QSlider#QuantAccentSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(37, 244, 238, 0.45),
        stop:0.55 rgba(37, 244, 238, 0.82),
        stop:1 rgba(120, 250, 240, 0.98));
    border: 1px solid rgba(37, 244, 238, 0.65);
    border-radius: 5px;
}
QSlider#QuantAccentSlider::add-page:horizontal {
    background: rgba(38, 46, 58, 0.95);
    border-radius: 5px;
}
QSlider#QuantAccentSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #f0fffe,
        stop:1 #5eead4);
    border: 2px solid #25F4EE;
    width: 14px;
    height: 18px;
    margin: -8px 0;
    border-radius: 4px;
}
QSlider#QuantAccentSlider::handle:horizontal:hover {
    background: #ffffff;
    border-color: #a5f3fc;
}
QSlider#QuantAccentSlider::handle:horizontal:pressed {
    background: #ccfbf1;
    border-color: #22d3ee;
}
QSlider#QuantAccentSlider:disabled {
    opacity: 0.5;
}
"""


def style_quant_accent_slider(slider: QSlider) -> None:
    """Strong track + fill + thumb for quantization sliders (sub-page grows with value)."""
    slider.setObjectName(QUANT_ACCENT_SLIDER_OBJECT_NAME)
    slider.setStyleSheet(_QUANT_ACCENT_SLIDER_QSS)


class NoWheelComboBox(QComboBox):
    """QComboBox that does not change the current item when the user scrolls the wheel over it."""

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None:
            event.ignore()


class NoWheelSpinBox(QSpinBox):
    """QSpinBox that ignores wheel deltas (avoids accidental value changes while scrolling the window)."""

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None:
            event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that ignores wheel deltas."""

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None:
            event.ignore()


class NoWheelSlider(QSlider):
    """QSlider that ignores wheel deltas (scroll the parent instead of stepping the slider)."""

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None:
            event.ignore()


class QuantAccentSlider(NoWheelSlider):
    """NoWheelSlider pre-styled for Model-tab quantization (accented track + fill grows with value)."""

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent=None) -> None:
        super().__init__(orientation, parent)
        style_quant_accent_slider(self)
