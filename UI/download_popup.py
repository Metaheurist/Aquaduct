from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from UI.title_bar_outline_button import styled_outline_button


class DownloadPopup(QDialog):
    """
    Small borderless popup showing download progress.
    """

    cancel_requested = pyqtSignal()
    pause_requested = pyqtSignal()

    def __init__(self, parent=None, *, title: str = "Downloading models") -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(720, 220)
        self._drag_pos: QPoint | None = None
        # Track why we're closing. closeEvent treats an "X" click as cancel, but
        # a deliberate Pause button should NOT also emit cancel.
        self._closing_action: str | None = None  # None | "pause" | "cancel"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size: 14px; font-weight: 800;")
        top.addWidget(self.title, 1)

        pause = styled_outline_button("⏸", "muted_icon", fixed=(44, 32))
        pause.setToolTip("Pause (you can resume later)")
        pause.clicked.connect(self._request_pause)
        top.addWidget(pause, 0, Qt.AlignmentFlag.AlignRight)

        close = styled_outline_button("✕", "danger", fixed=(44, 32))
        close.clicked.connect(self._request_cancel)
        top.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(top)

        self.status = QLabel("Starting…")
        self.status.setStyleSheet("color: #B7B7C2;")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        lay.addWidget(self.bar)

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

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class ImportPopup(QDialog):
    """Popup window showing the active import model and progress."""

    cancel_requested = pyqtSignal()

    def __init__(self, parent=None, *, title: str = "Importing models") -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(620, 220)
        self._drag_pos: QPoint | None = None
        self._closing_action: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size: 14px; font-weight: 800;")
        top.addWidget(self.title, 1)

        close = styled_outline_button("✕", "danger", fixed=(44, 32))
        close.clicked.connect(self._request_cancel)
        top.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(top)

        self.current_model = QLabel("Current model: —")
        self.current_model.setStyleSheet("font-size: 13px; font-weight: 700;")
        lay.addWidget(self.current_model)

        self.remaining = QLabel("Remaining: —")
        self.remaining.setStyleSheet("color: #B7B7C2;")
        lay.addWidget(self.remaining)

        self.status = QLabel("Preparing import…")
        self.status.setStyleSheet("color: #B7B7C2;")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        lay.addWidget(self.bar)

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

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

