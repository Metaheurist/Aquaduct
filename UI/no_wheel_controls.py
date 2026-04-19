"""Qt widgets that ignore the mouse wheel so page/scroll areas scroll instead of changing values."""

from __future__ import annotations

from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


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
