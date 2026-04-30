"""Two-segment Photo | Video toggle (centered in the custom title bar)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QToolButton, QWidget

from UI.help.tutorial_links import help_tooltip_rich


class MediaModeToggle(QWidget):
    """
    Segmented control with **Photo** and **Video** labels.

    Mimics the small part of ``QComboBox`` used by settings/main:
    ``currentData()``, ``setCurrentIndex()``, ``currentIndexChanged``.
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mediaModeToggleRoot")
        self.setAccessibleName("Media mode")
        self.setToolTip(
            help_tooltip_rich(
                "Video: render MP4 shorts. Photo: generate still images and layouts (Picture tab).",
                "run",
                slide=2,
            )
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._shell = QFrame(self)
        self._shell.setObjectName("mediaModeToggleShell")
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(3, 3, 3, 3)
        shell_lay.setSpacing(0)

        self._photo = QToolButton(self._shell)
        self._video = QToolButton(self._shell)
        self._photo.setObjectName("modeSegPhoto")
        self._video.setObjectName("modeSegVideo")

        for b, label, acc in (
            (self._photo, "Photo", "Photo mode"),
            (self._video, "Video", "Video mode"),
        ):
            b.setText(label)
            b.setCheckable(True)
            b.setAutoExclusive(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(32)
            b.setMinimumWidth(80)
            b.setAccessibleName(acc)

        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        self._grp.addButton(self._photo, 0)
        self._grp.addButton(self._video, 1)
        self._grp.idClicked.connect(self._on_segment_clicked)

        shell_lay.addWidget(self._photo, 1)
        shell_lay.addWidget(self._video, 1)
        root.addWidget(self._shell)

        self._shell.setStyleSheet(
            "QFrame#mediaModeToggleShell {"
            "  background-color: #121218;"
            "  border: 1px solid #2E2E38;"
            "  border-radius: 12px;"
            "}"
        )

        # Default to Video (existing app behavior)
        self._photo.setChecked(False)
        self._video.setChecked(True)
        self._restyle_segments()

    def _on_segment_clicked(self, index: int) -> None:
        self._restyle_segments()
        self.currentIndexChanged.emit(int(index))

    def _restyle_segments(self) -> None:
        accent = "rgba(37, 244, 238, 0.22)"
        accent_border = "rgba(37, 244, 238, 0.55)"
        self._photo.setStyleSheet(
            self._segment_qss(left=True, checked=self._photo.isChecked(), accent=accent, accent_border=accent_border)
        )
        self._video.setStyleSheet(
            self._segment_qss(left=False, checked=self._video.isChecked(), accent=accent, accent_border=accent_border)
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
        # 0 = photo, 1 = video
        return 0 if self._photo.isChecked() else 1

    def setCurrentIndex(self, index: int) -> None:
        want = 0 if int(index) == 0 else 1
        prev = self.currentIndex()
        btn = self._photo if want == 0 else self._video
        btn.setChecked(True)
        self._restyle_segments()
        if want != prev:
            self.currentIndexChanged.emit(want)

    def currentData(self, role: int | None = None) -> str:  # noqa: ARG002 — match QComboBox signature
        return "photo" if self._photo.isChecked() else "video"

