from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout


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
        self.setFixedSize(720, 165)
        self._drag_pos: QPoint | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size: 14px; font-weight: 800;")
        top.addWidget(self.title, 1)

        pause = QPushButton("⏸")
        pause.setObjectName("pauseBtn")
        pause.setFixedSize(44, 32)
        pause.setToolTip("Pause (you can resume later)")
        pause.clicked.connect(self._request_pause)
        top.addWidget(pause, 0, Qt.AlignmentFlag.AlignRight)

        close = QPushButton("✕")
        close.setObjectName("closeBtn")
        close.setFixedSize(44, 32)
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
        self.cancel_requested.emit()
        self.reject()

    def _request_pause(self) -> None:
        self.pause_requested.emit()
        self.reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # Treat window-close as cancel, too.
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

