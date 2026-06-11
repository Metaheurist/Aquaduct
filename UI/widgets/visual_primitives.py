"""Visual-first controls for Basic mode: step cards, steppers, previews, provider cards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from UI.theme import token
from UI.widgets.no_wheel_controls import NoWheelSpinBox
from UI.widgets.option_tiles import _VisualCardButton
from UI.widgets.themed_switch import ThemedSwitch
from UI.widgets.tile_svg_icons import qicon_tile


def _qss_color(hex_color: str, fallback: str = "#2E2E38") -> str:
    c = QColor(str(hex_color or fallback))
    return c.name() if c.isValid() else fallback


def _rgba(hex_color: str, alpha: float) -> str:
    """Qt stylesheets require rgba alpha as 0–255, not 0.0–1.0."""
    c = QColor(hex_color)
    if not c.isValid():
        c = QColor("#25F4EE")
    a = max(0, min(255, int(round(float(alpha) * 255))))
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class StepCard(QFrame):
    """Numbered step container for guided Basic layouts."""

    def __init__(
        self,
        step: int,
        title: str,
        *,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StepCard")
        self.setStyleSheet("QFrame#StepCard { background: transparent; border: none; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        head = QHBoxLayout()
        num = QLabel(str(int(step)))
        num.setFixedSize(22, 22)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        accent = _qss_color(token("accent", "#25F4EE"))
        num.setStyleSheet(
            f"background-color: {_rgba(accent, 0.25)}; color: #FFF; font-weight: 800; "
            "border-radius: 11px; font-size: 11px;"
        )
        head.addWidget(num, 0)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #E8E8EE; font-size: 13px; font-weight: 700;")
        head.addWidget(title_lbl, 1)
        lay.addLayout(head)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet("color: #8A96A3; font-size: 11px;")
            lay.addWidget(sub)
        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        lay.addLayout(self.body_layout)

    def addWidget(self, w: QWidget) -> None:
        self.body_layout.addWidget(w)

    def addLayout(self, layout) -> None:
        self.body_layout.addLayout(layout)


class CoachStrip(QLabel):
    """Single-line contextual coach message."""

    def __init__(self, text: str = "", *, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("CoachStrip")
        accent = _qss_color(token("accent", "#25F4EE"))
        self.setStyleSheet(
            f"color: {accent}; font-size: 11px; padding: 6px 10px; "
            f"border-left: 3px solid {accent}; background-color: {_rgba('#FFFFFF', 0.03)};"
        )
        self.setWordWrap(True)

    def set_message(self, text: str) -> None:
        self.setText(text)
        self.setVisible(bool(str(text or "").strip()))


class PreviewStrip(QFrame):
    """Aspect-ratio preview mock (9:16 default)."""

    def __init__(self, *, aspect: str = "9:16", label: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PreviewStrip")
        self._aspect = aspect
        border = _qss_color(token("border", "#2E2E38"))
        self.setStyleSheet(
            f"QFrame#PreviewStrip {{ border: 1px dashed {border}; border-radius: 8px; "
            f"background-color: {_rgba('#FFFFFF', 0.04)}; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self._inner = QLabel(label or aspect)
        self._inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._inner.setStyleSheet("color: #9BA6B8; font-size: 10px;")
        if aspect == "9:16":
            self._inner.setMinimumSize(54, 96)
        elif aspect == "1:1":
            self._inner.setMinimumSize(72, 72)
        else:
            self._inner.setMinimumSize(96, 54)
        lay.addWidget(self._inner, 0, Qt.AlignmentFlag.AlignCenter)

    def set_caption(self, text: str) -> None:
        self._inner.setText(text)


class QuantityStepper(QWidget):
    """Large +/- stepper wrapping a hidden spin (harvest-compatible)."""

    valueChanged = pyqtSignal(int)

    _BTN = 34

    def __init__(
        self,
        *,
        minimum: int = 1,
        maximum: int = 50,
        value: int = 1,
        presets: tuple[int, ...] = (1, 3, 5),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("QuantityStepper")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._spin = NoWheelSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setValue(value)
        self._spin.setVisible(False)
        self._spin.valueChanged.connect(self._sync_display)
        self._spin.valueChanged.connect(self.valueChanged.emit)

        border = _qss_color(token("border", "#2E2E38"))
        panel = _qss_color(token("panel", "#0B0B0F"))
        accent = _qss_color(token("accent", "#25F4EE"))
        sz = self._BTN
        self.setStyleSheet(
            f"QWidget#QuantityStepper QPushButton {{"
            f"  background-color: {panel};"
            f"  color: #E8E8EE;"
            f"  border: 1px solid {border};"
            f"  border-radius: {sz // 2}px;"
            f"  padding: 0px;"
            f"  min-width: {sz}px;"
            f"  max-width: {sz}px;"
            f"  min-height: {sz}px;"
            f"  max-height: {sz}px;"
            f"  font-weight: 700;"
            f"  font-size: 12px;"
            f"}}"
            f"QWidget#QuantityStepper QPushButton:hover {{"
            f"  border-color: {accent};"
            f"}}"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._minus = QPushButton()
        self._minus.setFixedSize(sz, sz)
        self._minus.setIcon(qicon_tile("minus", "#E8E8EE", 16))
        self._minus.setIconSize(QSize(16, 16))
        self._minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self._minus.clicked.connect(self._dec)
        root.addWidget(self._minus)

        self._val_lbl = QLabel()
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val_lbl.setFixedWidth(40)
        self._val_lbl.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: 700; background: transparent; border: none;")
        root.addWidget(self._val_lbl)

        self._plus = QPushButton()
        self._plus.setFixedSize(sz, sz)
        self._plus.setIcon(qicon_tile("plus", "#E8E8EE", 16))
        self._plus.setIconSize(QSize(16, 16))
        self._plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus.clicked.connect(self._inc)
        root.addWidget(self._plus)

        for p in presets:
            chip = QPushButton(str(p))
            chip.setFixedSize(sz, sz)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _c=False, v=p: self.setValue(v))
            root.addWidget(chip)

        self._sync_display()

    def _sync_display(self) -> None:
        self._val_lbl.setText(str(self._spin.value()))

    def _dec(self) -> None:
        self._spin.setValue(max(self._spin.minimum(), self._spin.value() - 1))

    def _inc(self) -> None:
        self._spin.setValue(min(self._spin.maximum(), self._spin.value() + 1))

    def value(self) -> int:
        return int(self._spin.value())

    def setValue(self, v: int) -> None:
        self._spin.setValue(int(v))

    def setRange(self, lo: int, hi: int) -> None:
        self._spin.setRange(lo, hi)

    def spin(self) -> NoWheelSpinBox:
        """Underlying spin for harvest attribute compatibility."""
        return self._spin


@dataclass(frozen=True)
class PresetCard:
    id: str
    title: str
    subtitle: str = ""
    icon: str = ""
    recommended: bool = False


class PresetCardGrid(QWidget):
    """Checkable preset cards. Combo-subset API on string ids."""

    currentIndexChanged = pyqtSignal(int)

    def __init__(
        self,
        cards: list[PresetCard],
        *,
        columns: int = 3,
        object_name: str = "PresetCardGrid",
        default_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cards = list(cards)
        self._ids = [c.id for c in cards]
        self._buttons: list[_VisualCardButton] = []

        grid = QGridLayout(self)
        grid.setSpacing(8)
        cols = max(1, columns)
        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)

        for i, card in enumerate(cards):
            btn = _VisualCardButton(
                label=card.title,
                subtitle=card.subtitle,
                icon=card.icon or card.id,
                recommended=card.recommended,
                icon_size=36,
            )
            btn.setObjectName(object_name)
            btn.setProperty("preset_id", card.id)
            self._grp.addButton(btn, i)
            self._buttons.append(btn)
            grid.addWidget(btn, i // cols, i % cols)

        self._grp.idClicked.connect(self._on_clicked)

        if default_id and default_id in self._ids:
            self.setCurrentData(default_id)
        elif self._buttons:
            self._buttons[0].setChecked(True)
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
        i = max(0, min(int(index), len(self._buttons) - 1))
        prev = self.currentIndex()
        self._buttons[i].setChecked(True)
        self._restyle()
        if i != prev:
            self.currentIndexChanged.emit(i)

    def currentData(self, role=None):  # noqa: ANN001, ARG002
        i = self.currentIndex()
        return self._ids[i] if 0 <= i < len(self._ids) else ""

    def findData(self, value: str) -> int:
        try:
            return self._ids.index(str(value))
        except ValueError:
            return -1

    def setCurrentData(self, value: str) -> None:
        idx = self.findData(value)
        if idx >= 0:
            self.setCurrentIndex(idx)


@dataclass(frozen=True)
class SwatchOption:
    id: str
    label: str
    color_hex: str


def _swatch_chip_icon(color_hex: str, *, width: int = 64, height: int = 28) -> QIcon:
    """Rounded accent chip for theme swatch cards."""
    c = QColor(str(color_hex or "#25F4EE"))
    if not c.isValid():
        c = QColor("#25F4EE")
    pm = QPixmap(int(width), int(height))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(c)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, width, height, 8.0, 8.0)
    painter.end()
    return QIcon(pm)


class SwatchGrid(QWidget):
    """Palette swatch picker — color chip above readable label, expands to fill width."""

    currentIndexChanged = pyqtSignal(int)

    def __init__(
        self,
        options: list[SwatchOption],
        *,
        columns: int = 3,
        default_id: str = "default",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._options = list(options)
        self._ids = [o.id for o in options]
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        cols = max(1, int(columns))
        self._buttons: list[QToolButton] = []
        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)

        for i, opt in enumerate(options):
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIcon(_swatch_chip_icon(opt.color_hex))
            btn.setIconSize(QSize(64, 28))
            btn.setText(opt.label)
            btn.setToolTip(opt.label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumHeight(88)
            btn.setMinimumWidth(96)
            self._grp.addButton(btn, i)
            self._buttons.append(btn)
            grid.addWidget(btn, i // cols, i % cols)

        for col in range(cols):
            grid.setColumnStretch(col, 1)

        self._grp.idClicked.connect(self._on_clicked)
        self.setCurrentData(default_id)
        self._restyle()

    def _on_clicked(self, index: int) -> None:
        self._restyle()
        self.currentIndexChanged.emit(int(index))

    def _restyle(self) -> None:
        accent_hex = token("accent", "#25F4EE")
        accent_bg = _rgba(accent_hex, 0.16)
        accent_border = _rgba(accent_hex, 0.55)
        border = token("border", "#2E2E38")
        control_bg = token("control_bg", "#121218")
        for btn in self._buttons:
            if btn.isChecked():
                btn.setStyleSheet(
                    "QToolButton {"
                    f"  background-color: {accent_bg};"
                    f"  border: 2px solid {accent_border};"
                    "  border-radius: 10px;"
                    "  color: #FFFFFF;"
                    "  font-size: 12px;"
                    "  font-weight: 700;"
                    "  padding: 10px 8px 8px 8px;"
                    "}"
                )
            else:
                btn.setStyleSheet(
                    "QToolButton {"
                    f"  background-color: {control_bg};"
                    f"  border: 1px solid {border};"
                    "  border-radius: 10px;"
                    "  color: #E8E8EE;"
                    "  font-size: 12px;"
                    "  font-weight: 600;"
                    "  padding: 10px 8px 8px 8px;"
                    "}"
                    "QToolButton:hover {"
                    f"  border-color: {accent_border};"
                    "  color: #FFFFFF;"
                    "}"
                )

    def _pick(self, btn: QToolButton) -> None:
        for b in self._buttons:
            b.setChecked(b is btn)
        self._restyle()
        self.currentIndexChanged.emit(self.currentIndex())

    def currentIndex(self) -> int:
        for i, b in enumerate(self._buttons):
            if b.isChecked():
                return i
        return 0

    def currentData(self, role=None):  # noqa: ANN001, ARG002
        i = self.currentIndex()
        return self._ids[i] if 0 <= i < len(self._ids) else ""

    def findData(self, value: str) -> int:
        try:
            return self._ids.index(str(value))
        except ValueError:
            return -1

    def setCurrentIndex(self, index: int) -> None:
        if self._buttons and 0 <= index < len(self._buttons):
            self._pick(self._buttons[index])

    def setCurrentData(self, value: str) -> None:
        idx = self.findData(value)
        if idx >= 0:
            self.setCurrentIndex(idx)


class ProviderCard(QFrame):
    """API provider row: title, switch, optional key field, status dot."""

    def __init__(
        self,
        title: str,
        *,
        switch: ThemedSwitch,
        key_edit: QLineEdit | None = None,
        status: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProviderCard")
        self.setStyleSheet("QFrame#ProviderCard { background: transparent; border: none; padding: 0; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        self._dot.setStyleSheet("border-radius: 4px; background-color: #6A6A78;")
        head.addWidget(self._dot, 0)
        name = QLabel(title)
        name.setStyleSheet("color: #E8E8EE; font-weight: 600;")
        head.addWidget(name, 1)
        head.addWidget(switch, 0)
        lay.addLayout(head)
        self._key_wrap = QWidget()
        key_lay = QVBoxLayout(self._key_wrap)
        key_lay.setContentsMargins(0, 0, 0, 0)
        if key_edit is not None:
            key_lay.addWidget(key_edit)
        lay.addWidget(self._key_wrap)
        self._key_wrap.setVisible(False)
        switch.toggled.connect(self._key_wrap.setVisible)
        if status:
            st = QLabel(status)
            st.setStyleSheet("color: #8A96A3; font-size: 10px;")
            lay.addWidget(st)

    def set_connected(self, on: bool) -> None:
        color = _qss_color(token("accent", "#25F4EE")) if on else "#6A6A78"
        self._dot.setStyleSheet(f"border-radius: 4px; background-color: {color};")


class PromptChips(QWidget):
    """Quick-fill chips for text areas."""

    def __init__(
        self,
        chips: list[str],
        *,
        on_apply: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for text in chips:
            b = QPushButton(text[:28] + ("…" if len(text) > 28 else ""))
            b.setProperty("buttonRole", "secondary")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(text)
            b.clicked.connect(lambda _c=False, t=text: on_apply(t))
            row.addWidget(b)
        row.addStretch(1)
