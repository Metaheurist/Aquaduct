"""N-segment pill picker — combo-subset API for small enum choices."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QToolButton, QWidget

from UI.theme import token


@dataclass(frozen=True)
class SegmentOption:
    label: str
    value: str
    tooltip: str = ""
    accessible_name: str = ""


def _rgba(hex_color: str, alpha: float) -> str:
    """Qt stylesheets require rgba alpha as 0–255, not 0.0–1.0."""
    c = QColor(hex_color)
    if not c.isValid():
        c = QColor("#25F4EE")
    a = max(0, min(255, int(round(float(alpha) * 255))))
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class SegmentedPicker(QWidget):
    """
    Horizontal pill segments. Subset of ``QComboBox`` API:
    ``currentData()``, ``setCurrentIndex()``, ``currentIndexChanged``, ``findData()``.
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(
        self,
        options: list[SegmentOption],
        *,
        accessible_name: str = "Segmented picker",
        tooltip: str = "",
        object_name_root: str = "SegmentedPicker",
        object_name_shell: str = "SegmentedPickerShell",
        min_button_width: int = 64,
        min_button_height: int = 32,
        font_size_px: int = 13,
        default_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._options = list(options)
        self._values = [o.value for o in self._options]
        self._min_h = min_button_height
        self._font_px = font_size_px
        self._min_w = min_button_width

        self.setObjectName(object_name_root)
        self.setAccessibleName(accessible_name)
        if tooltip:
            self.setToolTip(tooltip)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._shell = QFrame(self)
        self._shell.setObjectName(object_name_shell)
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(3, 3, 3, 3)
        shell_lay.setSpacing(0)

        self._buttons: list[QToolButton] = []
        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        n = len(self._options)
        for i, opt in enumerate(self._options):
            btn = QToolButton(self._shell)
            btn.setText(opt.label)
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            btn.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumHeight(self._min_h)
            btn.setMinimumWidth(self._min_w)
            btn.setAccessibleName(opt.accessible_name or opt.label)
            if opt.tooltip:
                btn.setToolTip(opt.tooltip)
            self._grp.addButton(btn, i)
            self._buttons.append(btn)
            shell_lay.addWidget(btn, 1)

        self._grp.idClicked.connect(self._on_segment_clicked)
        root.addWidget(self._shell)
        shell_border = _rgba(token("border", "#2E2E38"), 0.45)
        self._shell.setStyleSheet(
            f"QFrame#{object_name_shell} {{"
            f"  background-color: {token('control_bg', '#121218')};"
            f"  border: 1px solid {shell_border};"
            "  border-radius: 12px;"
            "}"
        )

        di = max(0, min(int(default_index), n - 1)) if n else 0
        if n:
            self._buttons[di].setChecked(True)
        self._restyle_segments()

    def _on_segment_clicked(self, index: int) -> None:
        self._restyle_segments()
        self.currentIndexChanged.emit(int(index))

    def _segment_qss(self, *, left: bool, right: bool, checked: bool, accent: str) -> str:
        fs = self._font_px
        pad = "6px 12px"
        radius = ""
        if left and right:
            radius = "border-radius: 9px;"
        elif left:
            radius = "border-top-left-radius: 9px; border-bottom-left-radius: 9px;"
        elif right:
            radius = "border-top-right-radius: 9px; border-bottom-right-radius: 9px;"
        if checked:
            return (
                "QToolButton {"
                + radius
                + f"  background-color: {accent};"
                + "  color: #FFFFFF;"
                + "  font-weight: 700;"
                + f"  font-size: {fs}px;"
                + "  border: none;"
                + f"  padding: {pad};"
                + "}"
            )
        return (
            "QToolButton {"
            + radius
            + "  background-color: transparent;"
            + "  color: #8A8A96;"
            + "  font-weight: 600;"
            + f"  font-size: {fs}px;"
            + "  border: none;"
            + f"  padding: {pad};"
            + "}"
            + "QToolButton:hover { color: #E6E6F0; background-color: rgba(255,255,255,13); }"
        )

    def _restyle_segments(self) -> None:
        accent_hex = token("accent", "#25F4EE")
        accent = _rgba(accent_hex, 0.30)
        n = len(self._buttons)
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(
                self._segment_qss(
                    left=(i == 0),
                    right=(i == n - 1),
                    checked=btn.isChecked(),
                    accent=accent,
                )
            )

    def currentIndex(self) -> int:
        for i, btn in enumerate(self._buttons):
            if btn.isChecked():
                return i
        return 0

    def setCurrentIndex(self, index: int) -> None:
        if not self._buttons:
            return
        want = max(0, min(int(index), len(self._buttons) - 1))
        prev = self.currentIndex()
        self._buttons[want].setChecked(True)
        self._restyle_segments()
        if want != prev:
            self.currentIndexChanged.emit(want)

    def currentData(self, role: int | None = None) -> str:  # noqa: ARG002
        idx = self.currentIndex()
        if 0 <= idx < len(self._values):
            return self._values[idx]
        return ""

    def findData(self, value: str) -> int:
        try:
            return self._values.index(str(value))
        except ValueError:
            return -1

    def count(self) -> int:
        return len(self._options)

    def setItemText(self, index: int, text: str) -> None:
        """Compat shim for code that updates combo item labels dynamically."""
        if 0 <= index < len(self._buttons):
            self._buttons[index].setText(text)
