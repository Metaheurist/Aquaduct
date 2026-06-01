from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QProgressBar

from UI.dialogs.frameless_dialog import FramelessDialog
from UI.help.tutorial_links import help_tooltip_rich
from UI.theme import token
from UI.widgets.title_bar_outline_button import styled_outline_button


class DownloadPopup(FramelessDialog):
    """Small borderless popup showing download progress (shared Aquaduct dialog chrome)."""

    cancel_requested = pyqtSignal()
    pause_requested = pyqtSignal()

    def __init__(self, parent=None, *, title: str = "Downloading models") -> None:
        super().__init__(parent, title=title)
        self.setFixedSize(720, 220)
        # Track why we're closing. closeEvent treats an "X" click as cancel, but
        # a deliberate Pause button should NOT also emit cancel.
        self._closing_action: str | None = None  # None | "pause" | "cancel"
        self.title = self._title_lbl

        pause = styled_outline_button("", "muted_icon", fixed=(44, 32), icon_kind="pause")
        pause.setToolTip(
            help_tooltip_rich(
                "Pause the download queue (you can resume later from the Model tab).",
                "models",
                slide=2,
            )
        )
        pause.setAccessibleName("Pause download")
        pause.clicked.connect(self._request_pause)
        self.insert_title_bar_widget_before_close(pause)
        # The shared ✕ button rejects the dialog; route that through cancel via closeEvent.
        self._frameless_close_button.setAccessibleName("Cancel download")

        self.status = QLabel("Starting…")
        self.status.setStyleSheet(f"color: {token('muted', '#B7B7C2')};")
        self.status.setWordWrap(True)
        self.body_layout.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.body_layout.addWidget(self.bar)

    def _request_cancel(self) -> None:
        self._closing_action = "cancel"
        self.cancel_requested.emit()
        self.reject()

    def _request_pause(self) -> None:
        self._closing_action = "pause"
        self.pause_requested.emit()
        self.reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # Treat user window-close as cancel, unless the close was initiated by the Pause button.
        if self._closing_action != "pause":
            try:
                self.cancel_requested.emit()
            except Exception:
                pass
        return super().closeEvent(event)


class ImportPopup(FramelessDialog):
    """Popup window showing the active import model and progress (shared dialog chrome)."""

    cancel_requested = pyqtSignal()

    def __init__(self, parent=None, *, title: str = "Importing models") -> None:
        super().__init__(parent, title=title)
        self.setFixedSize(620, 220)
        self._closing_action: str | None = None
        self.title = self._title_lbl
        self._frameless_close_button.setAccessibleName("Cancel import")

        self.current_model = QLabel("Current model: -")
        self.current_model.setStyleSheet("font-size: 13px; font-weight: 700;")
        self.body_layout.addWidget(self.current_model)

        self.remaining = QLabel("Remaining: -")
        self.remaining.setStyleSheet(f"color: {token('muted', '#B7B7C2')};")
        self.body_layout.addWidget(self.remaining)

        self.status = QLabel("Preparing import…")
        self.status.setStyleSheet(f"color: {token('muted', '#B7B7C2')};")
        self.status.setWordWrap(True)
        self.body_layout.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.body_layout.addWidget(self.bar)

    def set_model_status(self, repo_id: str, index: int, total: int) -> None:
        self.current_model.setText(f"Importing {index} of {total}: {repo_id}")
        remaining = max(total - index, 0)
        self.remaining.setText(f"Remaining: {remaining} model(s)")
        self.status.setText("Copying files…")

    def set_progress(self, value: int) -> None:
        self.bar.setValue(max(0, min(100, value)))
        self.status.setText(f"Copy progress: {self.bar.value()}%")

    def _request_cancel(self) -> None:
        self._closing_action = "cancel"
        self.cancel_requested.emit()
        self.reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._closing_action != "cancel":
            try:
                self.cancel_requested.emit()
            except Exception:
                pass
        return super().closeEvent(event)
