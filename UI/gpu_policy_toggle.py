"""Two-segment Auto | Select GPU toggle (My PC tab)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QToolButton, QWidget


class GpuPolicyToggle(QWidget):
    """
    Segmented control: **Auto** vs **Select GPU** (pins one CUDA device).

    Mirrors :class:`UI.media_mode_toggle.MediaModeToggle` API shape:
    ``currentIndex()``, ``setCurrentIndex()``, ``currentIndexChanged``, ``currentData()``.
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gpuPolicyToggleRoot")
        self.setAccessibleName("GPU policy")
        self.setToolTip(
            "Auto: multi-GPU stage routing (script vs diffusion may use different devices; VRAM is not pooled). "
            "Select GPU: pin all local stages to the device below. "
            "If AQUADUCT_CUDA_DEVICE is set in the environment, it overrides the saved policy (see docs/hardware.md)."
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._shell = QFrame(self)
        self._shell.setObjectName("gpuPolicyToggleShell")
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(3, 3, 3, 3)
        shell_lay.setSpacing(0)

        self._auto = QToolButton(self._shell)
        self._single = QToolButton(self._shell)
        self._auto.setObjectName("gpuSegAuto")
        self._single.setObjectName("gpuSegSingle")

        for b, label, acc in (
            (self._auto, "Auto", "Automatic GPU policy"),
            (self._single, "Select GPU", "Pin all stages to one GPU"),
        ):
            b.setText(label)
            b.setCheckable(True)
            b.setAutoExclusive(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(30)
            b.setMinimumWidth(88)
            b.setAccessibleName(acc)

        self._auto.setToolTip(
            "LLM tends toward the compute-heuristic CUDA device; image/video diffusion uses the max-VRAM GPU. "
            "VRAM is not merged across GPUs."
        )
        self._single.setToolTip("All local pipeline stages use the CUDA index chosen in Device.")

        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        self._grp.addButton(self._auto, 0)
        self._grp.addButton(self._single, 1)
        self._grp.idClicked.connect(self._on_segment_clicked)

        shell_lay.addWidget(self._auto, 1)
        shell_lay.addWidget(self._single, 1)
        root.addWidget(self._shell)

        self._shell.setStyleSheet(
            "QFrame#gpuPolicyToggleShell {"
            "  background-color: #121218;"
            "  border: 1px solid #2E2E38;"
            "  border-radius: 12px;"
            "}"
        )

        self._auto.setChecked(True)
        self._single.setChecked(False)
        self._restyle_segments()

    def _on_segment_clicked(self, index: int) -> None:
        self._restyle_segments()
        self.currentIndexChanged.emit(int(index))

    def _restyle_segments(self) -> None:
        accent = "rgba(37, 244, 238, 0.22)"
        accent_border = "rgba(37, 244, 238, 0.55)"
        self._auto.setStyleSheet(
            self._segment_qss(left=True, checked=self._auto.isChecked(), accent=accent, accent_border=accent_border)
        )
        self._single.setStyleSheet(
            self._segment_qss(left=False, checked=self._single.isChecked(), accent=accent, accent_border=accent_border)
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
                + "  font-size: 12px;"
                + f"  border: 1px solid {accent_border};"
                + "  padding: 5px 10px;"
                + "}"
            )
        return (
            "QToolButton {"
            + r
            + "  background-color: transparent;"
            + "  color: #8A8A96;"
            + "  font-weight: 600;"
            + "  font-size: 12px;"
            + "  border: 1px solid transparent;"
            + "  padding: 5px 10px;"
            + "}"
            + "QToolButton:hover { color: #E6E6F0; background-color: rgba(255,255,255,0.05); }"
        )

    def currentIndex(self) -> int:
        return 0 if self._auto.isChecked() else 1

    def setCurrentIndex(self, index: int) -> None:
        want = 0 if int(index) == 0 else 1
        prev = self.currentIndex()
        btn = self._auto if want == 0 else self._single
        btn.setChecked(True)
        self._restyle_segments()
        if want != prev:
            self.currentIndexChanged.emit(want)

    def currentData(self, role: int | None = None) -> str:  # noqa: ARG002 — match QComboBox
        return "auto" if self._auto.isChecked() else "single"
