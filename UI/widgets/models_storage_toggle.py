"""Two-segment Default | External toggle for where Hugging Face model snapshots live."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QToolButton, QWidget

from UI.help.tutorial_links import help_tooltip_rich


class ModelsStorageModeToggle(QWidget):
    """
    Segmented control: **Default** (``.Aquaduct_data/models``) vs **External** (custom folder).
    Matches ``ModelExecutionModeToggle`` API: ``currentIndexChanged``, ``currentData()``, ``setCurrentIndex``.
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modelsStorageModeToggleRoot")
        self.setAccessibleName("Models storage location")
        self.setToolTip(
            help_tooltip_rich(
                "Default: project .Aquaduct_data/models. External: another drive or shared cache.",
                "models",
                slide=3,
            )
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._shell = QFrame(self)
        self._shell.setObjectName("modelsStorageModeToggleShell")
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(3, 3, 3, 3)
        shell_lay.setSpacing(0)

        self._default = QToolButton(self._shell)
        self._external = QToolButton(self._shell)
        self._default.setObjectName("modeSegDefault")
        self._external.setObjectName("modeSegExternal")

        for b, label, acc in (
            (self._default, "Default", "Use project .Aquaduct_data/models"),
            (self._external, "External", "Use a custom folder for model snapshots"),
        ):
            b.setText(label)
            b.setCheckable(True)
            b.setAutoExclusive(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(32)
            b.setMinimumWidth(88)
            b.setAccessibleName(acc)

        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        self._grp.addButton(self._default, 0)
        self._grp.addButton(self._external, 1)
        self._grp.idClicked.connect(self._on_segment_clicked)

        shell_lay.addWidget(self._default, 1)
        shell_lay.addWidget(self._external, 1)
        root.addWidget(self._shell)

        self._shell.setStyleSheet(
            "QFrame#modelsStorageModeToggleShell {"
            "  background-color: #121218;"
            "  border: 1px solid #2E2E38;"
            "  border-radius: 12px;"
            "}"
        )
        self._default.setChecked(True)
        self._external.setChecked(False)
        self._restyle_segments()

    def _on_segment_clicked(self, index: int) -> None:
        self._restyle_segments()
        self.currentIndexChanged.emit(int(index))

    def _restyle_segments(self) -> None:
        accent = "rgba(37, 244, 238, 0.22)"
        accent_border = "rgba(37, 244, 238, 0.55)"
        self._default.setStyleSheet(
            self._segment_qss(left=True, checked=self._default.isChecked(), accent=accent, accent_border=accent_border)
        )
        self._external.setStyleSheet(
            self._segment_qss(left=False, checked=self._external.isChecked(), accent=accent, accent_border=accent_border)
        )

    @staticmethod
    def _segment_qss(*, left: bool, checked: bool, accent: str, accent_border: str) -> str:
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
                + "  font-size: 13px;"
                + f"  border: 1px solid {accent_border};"
                + "  padding: 6px 14px;"
                + "}"
            )
        return (
            "QToolButton {"
            + r
            + "  background-color: transparent;"
            + "  color: #8A8A96;"
            + "  font-weight: 600;"
            + "  font-size: 13px;"
            + "  border: 1px solid transparent;"
            + "  padding: 6px 14px;"
            + "}"
            + "QToolButton:hover { color: #E6E6F0; background-color: rgba(255,255,255,0.05); }"
        )

    def currentIndex(self) -> int:
        return 1 if self._external.isChecked() else 0

    def setCurrentIndex(self, index: int) -> None:
        want = 1 if int(index) == 1 else 0
        prev = self.currentIndex()
        btn = self._external if want == 1 else self._default
        btn.setChecked(True)
        self._restyle_segments()
        if want != prev:
            self.currentIndexChanged.emit(want)

    def currentData(self, role: int | None = None) -> str:  # noqa: ARG002
        return "external" if self._external.isChecked() else "default"
