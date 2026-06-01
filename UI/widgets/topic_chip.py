"""Removable topic tag chips for the Topics tab."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QToolButton, QWidget

from UI.theme import token
from UI.widgets.toolbar_svg_icons import qicon_toolbar


class TopicChip(QWidget):
    """Pill tag with select + remove actions."""

    selected = pyqtSignal(str)
    removed = pyqtSignal(str)

    def __init__(self, tag: str, *, is_selected: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tag = str(tag).strip()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        accent = token("accent", "#25F4EE")
        border = token("border", "#23232B")
        muted = token("muted", "#B7B7C2")
        text_c = token("text", "#FFFFFF")

        self._pill = QPushButton(self._tag)
        self._pill.setCheckable(True)
        self._pill.setChecked(bool(is_selected))
        self._pill.setProperty("shape", "pill")
        self._pill.setCursor(Qt.CursorShape.PointingHandCursor)
        sel = (
            f"QPushButton {{ background: rgba(37,244,238,0.12); border: 1px solid {accent}; "
            f"color: {text_c}; font-weight: 600; }}"
        )
        base = (
            f"QPushButton {{ background: rgba(255,255,255,0.04); border: 1px solid {border}; "
            f"color: {muted}; font-weight: 600; }}"
            f"QPushButton:hover {{ border: 1px solid {accent}; color: {text_c}; }}"
        )
        self._pill.setStyleSheet(sel if is_selected else base)
        self._pill.clicked.connect(lambda: self.selected.emit(self._tag))
        lay.addWidget(self._pill)

        rm = QToolButton()
        rm.setIcon(qicon_toolbar("cross", token("muted", "#B7B7C2"), 14))
        rm.setIconSize(rm.iconSize())
        from PyQt6.QtCore import QSize

        rm.setIconSize(QSize(14, 14))
        rm.setAutoRaise(True)
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.setToolTip("Remove tag")
        rm.setAccessibleName(f"Remove tag {self._tag}")
        rm.clicked.connect(lambda: self.removed.emit(self._tag))
        lay.addWidget(rm)

    @property
    def tag(self) -> str:
        return self._tag

    def set_selected(self, on: bool) -> None:
        accent = token("accent", "#25F4EE")
        border = token("border", "#23232B")
        muted = token("muted", "#B7B7C2")
        text_c = token("text", "#FFFFFF")
        self._pill.setChecked(bool(on))
        if on:
            self._pill.setStyleSheet(
                f"QPushButton {{ background: rgba(37,244,238,0.12); border: 1px solid {accent}; "
                f"color: {text_c}; font-weight: 600; }}"
            )
        else:
            self._pill.setStyleSheet(
                f"QPushButton {{ background: rgba(255,255,255,0.04); border: 1px solid {border}; "
                f"color: {muted}; font-weight: 600; }}"
                f"QPushButton:hover {{ border: 1px solid {accent}; color: {text_c}; }}"
            )
