"""Lightweight startup window: progress + status while heavy modules load (frozen EXE cold start)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QElapsedTimer, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget


class StartupSplash(QWidget):
    """
    Frameless splash with determinate 0–100% progress and optional indeterminate phase
    (``setRange(0,0)`` on the bar) for long single-threaded imports.
    """

    def __init__(self, app: QApplication) -> None:
        super().__init__(None)
        self._app = app
        self.setObjectName("StartupSplash")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.SplashScreen
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(420, 140)
        self.setStyleSheet(
            "#StartupSplash { background-color: #0F0F10; border: 1px solid #25F4EE; border-radius: 12px; }"
            "#StartupSplash QLabel { color: #E8E8EE; }"
            "#splashTitle { color: #25F4EE; font-weight: 800; font-size: 18px; }"
            "#splashElapsed { color: #8A96A3; font-size: 11px; }"
            "#StartupSplash QProgressBar { border: 1px solid #2A2A34; border-radius: 6px; background: #15151B; height: 14px; text-align: center; color: #E8E8EE; }"
            "#StartupSplash QProgressBar::chunk { background: #25F4EE; border-radius: 5px; }"
        )

        title = QLabel("Aquaduct")
        title.setObjectName("splashTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._message = QLabel("Starting…")
        self._message.setWordWrap(True)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._elapsed_lbl = QLabel("")
        self._elapsed_lbl.setObjectName("splashElapsed")
        self._elapsed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%p%")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(title)
        lay.addWidget(self._message)
        lay.addWidget(self._bar)
        lay.addWidget(self._elapsed_lbl)

        self._timer = QElapsedTimer()
        self._timer.start()
        self._elapsed_updater = QTimer(self)
        self._elapsed_updater.timeout.connect(self._refresh_elapsed)
        self._elapsed_updater.start(500)

        self._center_on_primary()
        self.raise_()

    def _center_on_primary(self) -> None:
        screen = self._app.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        fr = self.frameGeometry()
        fr.moveCenter(geo.center())
        self.move(fr.topLeft())

    def _refresh_elapsed(self) -> None:
        s = self._timer.elapsed() // 1000
        self._elapsed_lbl.setText(f"Elapsed: {s}s")

    def set_progress(self, value: int, message: str) -> None:
        """Determinate 0–100 with status text."""
        self._bar.setRange(0, 100)
        self._bar.setFormat("%p%")
        self._bar.setValue(max(0, min(100, value)))
        self._message.setText(message)
        self._app.processEvents()

    def set_indeterminate(self, message: str) -> None:
        """Busy bar while a blocking import runs (cannot report real %)."""
        self._bar.setRange(0, 0)
        self._message.setText(message)
        self._app.processEvents()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            self._elapsed_updater.stop()
        except Exception:
            pass
        super().closeEvent(event)
