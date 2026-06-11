"""Visual tile grid for small enum choices (format pickers, etc.)."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from UI.theme import token
from UI.widgets.tile_svg_icons import pixmap_tile, qicon_tile


@dataclass(frozen=True)
class TileOption:
    label: str
    value: str
    icon: str = ""
    subtitle: str = ""
    tooltip: str = ""
    recommended: bool = False


def _rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    if not c.isValid():
        c = QColor("#25F4EE")
    a = max(0, min(255, int(round(float(alpha) * 255))))
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class _VisualCardButton(QToolButton):
    """Checkable card: SVG icon above title/subtitle (QToolButton — layouts on QPushButton overlap)."""

    def __init__(
        self,
        *,
        label: str,
        subtitle: str = "",
        icon: str = "",
        recommended: bool = False,
        tooltip: str = "",
        icon_size: int = 32,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(96 if str(subtitle or "").strip() else 84)
        self.setMinimumWidth(72)
        self._icon_size = max(20, int(icon_size))
        self._label = str(label)
        self._subtitle = str(subtitle or "")
        self._icon_kind = str(icon or "image")
        self._recommended = bool(recommended)
        self._sync_caption()
        if tooltip:
            self.setToolTip(tooltip)

        self._star_lbl = QLabel(self)
        self._star_lbl.setFixedSize(14, 14)
        self._star_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._star_lbl.setVisible(self._recommended)
        self._star_lbl.raise_()

    def _sync_caption(self) -> None:
        if self._subtitle.strip():
            self.setText(f"{self._label}\n{self._subtitle}")
        else:
            self.setText(self._label)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        if self._recommended:
            self._star_lbl.move(max(4, self.width() - 20), 6)
            self._star_lbl.raise_()

    def apply_palette(self, *, checked: bool) -> None:
        accent_hex = token("accent", "#25F4EE")
        accent_bg = _rgba(accent_hex, 0.18)
        accent_border = _rgba(accent_hex, 0.55)
        border = token("border", "#2E2E38")
        icon_color = "#FFFFFF" if checked else token("muted", "#B7B7C2")
        title_color = "#FFFFFF" if checked else "#E8E8EE"

        self.setIcon(qicon_tile(self._icon_kind, icon_color, self._icon_size))
        self.setIconSize(QSize(self._icon_size, self._icon_size))

        if checked:
            self.setStyleSheet(
                "QToolButton {"
                f"  background-color: {accent_bg};"
                f"  border: 1px solid {accent_border};"
                "  border-radius: 10px;"
                f"  color: {title_color};"
                "  font-weight: 700;"
                "  font-size: 11px;"
                "  padding: 8px 6px 6px 6px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QToolButton {"
                f"  background-color: {token('control_bg', '#121218')};"
                f"  border: 1px solid {border};"
                "  border-radius: 10px;"
                f"  color: {title_color};"
                "  font-weight: 700;"
                "  font-size: 11px;"
                "  padding: 8px 6px 6px 6px;"
                "}"
                "QToolButton:hover {"
                f"  border-color: {accent_border};"
                f"  color: {title_color};"
                "}"
            )
        if self._recommended:
            star_pm = pixmap_tile("star", accent_hex if checked else "#8A96A3", 12)
            if not star_pm.isNull():
                self._star_lbl.setPixmap(star_pm)


class OptionTiles(QWidget):
    """
    Clickable card grid. Combo-subset API: ``currentData()``, ``setCurrentIndex()``,
    ``currentIndexChanged``, ``findData()``.
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(
        self,
        options: list[TileOption],
        *,
        columns: int = 4,
        accessible_name: str = "Option tiles",
        default_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._options = list(options)
        self._values = [o.value for o in self._options]
        self.setAccessibleName(accessible_name)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        self._buttons: list[_VisualCardButton] = []
        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)

        cols = max(1, int(columns))
        for i, opt in enumerate(self._options):
            btn = _VisualCardButton(
                label=opt.label,
                subtitle=opt.subtitle,
                icon=opt.icon or opt.value,
                recommended=opt.recommended,
                tooltip=opt.tooltip,
            )
            btn.setAccessibleName(opt.label)
            self._grp.addButton(btn, i)
            self._buttons.append(btn)
            grid.addWidget(btn, i // cols, i % cols)

        self._grp.idClicked.connect(self._on_clicked)
        di = max(0, min(int(default_index), len(self._buttons) - 1)) if self._buttons else 0
        if self._buttons:
            self._buttons[di].setChecked(True)
        self._restyle()

    def _on_clicked(self, index: int) -> None:
        self._restyle()
        self.currentIndexChanged.emit(int(index))

    def _restyle(self) -> None:
        for btn in self._buttons:
            btn.apply_palette(checked=btn.isChecked())

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
        self._restyle()
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
