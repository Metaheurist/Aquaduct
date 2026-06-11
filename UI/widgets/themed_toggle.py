"""Shared two-segment (pill) toggle styling for title bar / settings toggles."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QToolButton, QWidget

from UI.help.tutorial_links import help_tooltip_rich
from UI.theme import token


def _rgba(hex_color: str, alpha: float) -> str:
    """Qt stylesheets require rgba alpha as 0–255, not 0.0–1.0."""
    c = QColor(hex_color)
    if not c.isValid():
        c = QColor("#25F4EE")
    a = max(0, min(255, int(round(float(alpha) * 255))))
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class ThemedToggle(QWidget):
    """
    Two-segment control matching ``QComboBox``-subset API used in main/settings:
    ``currentData()``, ``setCurrentIndex()``, ``currentIndexChanged``.
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(
        self,
        *,
        left_label: str,
        right_label: str,
        left_value: str,
        right_value: str,
        left_acc: str,
        right_acc: str,
        accessible_name: str,
        tooltip_body: str,
        tooltip_topic: str | None = None,
        tooltip_slide: int | None = None,
        object_name_root: str,
        object_name_shell: str,
        object_name_left: str,
        object_name_right: str,
        default_index: int = 0,
        min_button_width: int = 80,
        min_button_height: int = 32,
        font_size_px: int = 13,
        button_padding_css: str = "6px 14px",
        left_tooltip: str | None = None,
        right_tooltip: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._left_value = left_value
        self._right_value = right_value
        self._min_h = min_button_height
        self._font_px = font_size_px
        self._pad = button_padding_css

        self.setObjectName(object_name_root)
        self.setAccessibleName(accessible_name)
        tt = (
            help_tooltip_rich(tooltip_body, tooltip_topic, slide=tooltip_slide)
            if tooltip_topic is not None and tooltip_slide is not None
            else tooltip_body
        )
        self.setToolTip(tt)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._shell = QFrame(self)
        self._shell.setObjectName(object_name_shell)
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(3, 3, 3, 3)
        shell_lay.setSpacing(0)

        self._left_btn = QToolButton(self._shell)
        self._right_btn = QToolButton(self._shell)
        self._left_btn.setObjectName(object_name_left)
        self._right_btn.setObjectName(object_name_right)

        for b, label, acc, seg_tt in (
            (self._left_btn, left_label, left_acc, left_tooltip),
            (self._right_btn, right_label, right_acc, right_tooltip),
        ):
            b.setText(label)
            b.setCheckable(True)
            b.setAutoExclusive(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(self._min_h)
            b.setMinimumWidth(min_button_width)
            b.setAccessibleName(acc)
            if seg_tt:
                b.setToolTip(seg_tt)

        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        self._grp.addButton(self._left_btn, 0)
        self._grp.addButton(self._right_btn, 1)
        self._grp.idClicked.connect(self._on_segment_clicked)

        shell_lay.addWidget(self._left_btn, 1)
        shell_lay.addWidget(self._right_btn, 1)
        root.addWidget(self._shell)

        shell_border = _rgba(token("border", "#2E2E38"), 0.45)
        self._shell.setStyleSheet(
            f"QFrame#{object_name_shell} {{"
            f"  background-color: {token('control_bg', '#121218')};"
            f"  border: 1px solid {shell_border};"
            "  border-radius: 12px;"
            "}"
        )

        di = 0 if int(default_index) == 0 else 1
        self._left_btn.setChecked(di == 0)
        self._right_btn.setChecked(di == 1)
        self._restyle_segments()

    def _on_segment_clicked(self, index: int) -> None:
        self._restyle_segments()
        self.currentIndexChanged.emit(int(index))

    def _restyle_segments(self) -> None:
        accent_hex = token("accent", "#25F4EE")
        accent = _rgba(accent_hex, 0.30)
        self._left_btn.setStyleSheet(
            self._segment_qss(left=True, checked=self._left_btn.isChecked(), accent=accent)
        )
        self._right_btn.setStyleSheet(
            self._segment_qss(left=False, checked=self._right_btn.isChecked(), accent=accent)
        )

    def _segment_qss(self, *, left: bool, checked: bool, accent: str) -> str:
        fs = self._font_px
        pad = self._pad
        if left:
            r = "border-top-left-radius: 9px; border-bottom-left-radius: 9px;"
        else:
            r = "border-top-right-radius: 9px; border-bottom-right-radius: 9px;"
        if checked:
            return (
                "QToolButton {"
                + r
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
            + r
            + "  background-color: transparent;"
            + "  color: #8A8A96;"
            + "  font-weight: 600;"
            + f"  font-size: {fs}px;"
            + "  border: none;"
            + f"  padding: {pad};"
            + "}"
            + "QToolButton:hover { color: #E6E6F0; background-color: rgba(255,255,255,13); }"
        )

    def currentIndex(self) -> int:
        return 0 if self._left_btn.isChecked() else 1

    def setCurrentIndex(self, index: int) -> None:
        want = 0 if int(index) == 0 else 1
        prev = self.currentIndex()
        btn = self._left_btn if want == 0 else self._right_btn
        btn.setChecked(True)
        self._restyle_segments()
        if want != prev:
            self.currentIndexChanged.emit(want)

    def currentData(self, role: int | None = None) -> str:  # noqa: ARG002
        return self._left_value if self._left_btn.isChecked() else self._right_value
