"""Modal progress UI for Model tab → Install dependencies (streaming pip output)."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
)

from UI.frameless_dialog import FramelessDialog

from src.torch_install import (
    install_pytorch_for_hardware,
    install_requirements_runtime,
    pip_download_percent,
    pip_line_hint,
)


class DepsInstallWorker(QThread):
    """Runs PyTorch pip step then requirements.txt in a background thread."""

    phase = pyqtSignal(str)
    hint = pyqtSignal(str)
    line = pyqtSignal(str)
    progress_pct = pyqtSignal(int)
    finished_ex = pyqtSignal(int, str)

    def run(self) -> None:
        def on_line(line: str) -> None:
            self.line.emit(line)
            h = pip_line_hint(line)
            if h:
                self.hint.emit(h)
            pct = pip_download_percent(line)
            if pct is not None:
                self.progress_pct.emit(pct)

        try:
            self.phase.emit("Step 1/2 — PyTorch (torch, torchvision, torchaudio)")
            c1, o1 = install_pytorch_for_hardware(
                upgrade=True,
                force_cuda_if_applicable=True,
                on_line=on_line,
            )
            if c1 != 0:
                self.finished_ex.emit(c1, o1)
                return

            self.phase.emit("Step 2/2 — requirements.txt (transformers, accelerate, …)")
            c2, o2 = install_requirements_runtime(on_line=on_line)
            self.finished_ex.emit(c2, o1 + "\n\n" + o2)
        except Exception as e:
            self.finished_ex.emit(1, f"Install worker error: {e!s}")


class InstallDepsDialog(FramelessDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Installing dependencies")
        self.setMinimumSize(560, 420)
        self._worker: DepsInstallWorker | None = None
        self._last_exit_code = 1
        self._last_full_log = ""

        intro = QLabel(
            "PyTorch is installed first (CUDA wheels if an NVIDIA GPU is detected, otherwise CPU), "
            "then every package in requirements.txt. This can take several minutes."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #B7B7C2; font-size: 12px;")
        self.body_layout.addWidget(intro)

        self._phase_lbl = QLabel("Starting…")
        self._phase_lbl.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 13px;")
        self.body_layout.addWidget(self._phase_lbl)

        self._hint_lbl = QLabel("—")
        self._hint_lbl.setWordWrap(True)
        self._hint_lbl.setStyleSheet("color: #25F4EE; font-size: 12px;")
        self.body_layout.addWidget(self._hint_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%p%")
        self._bar.setMinimumHeight(14)
        self.body_layout.addWidget(self._bar)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("pip output will appear here…")
        self._log.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; color: #D0D0D8;")
        self._log.setMinimumHeight(200)
        self.body_layout.addWidget(self._log, 1)

        row = QHBoxLayout()
        self._ok = QPushButton("Close")
        self._ok.setObjectName("primary")
        self._ok.setEnabled(False)
        self._ok.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(self._ok)
        self.body_layout.addLayout(row)

        self._close_btn = self.findChild(QPushButton, "closeBtn")

    def reject(self) -> None:  # type: ignore[override]
        if self._worker is not None and self._worker.isRunning():
            return
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    def _set_close_enabled(self, on: bool) -> None:
        if self._close_btn is not None:
            try:
                self._close_btn.setEnabled(on)
            except Exception:
                pass

    def start_install(self) -> None:
        self._worker = DepsInstallWorker()
        self._worker.phase.connect(self._on_phase)
        self._worker.hint.connect(self._hint_lbl.setText)
        self._worker.line.connect(self._append_log_line)
        self._worker.progress_pct.connect(self._on_download_percent)
        self._worker.finished_ex.connect(self._on_finished)
        self._set_close_enabled(False)
        self._worker.start()

    def _on_phase(self, text: str) -> None:
        self._phase_lbl.setText(text)
        self._bar.setRange(0, 0)

    def _on_download_percent(self, pct: int) -> None:
        self._bar.setRange(0, 100)
        self._bar.setValue(int(pct))

    def _append_log_line(self, line: str) -> None:
        c = self._log.textCursor()
        c.movePosition(QTextCursor.MoveOperation.End)
        self._log.setTextCursor(c)
        self._log.insertPlainText(line + "\n")
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
        # Cap memory: trim if huge
        t = self._log.toPlainText()
        if len(t) > 900_000:
            self._log.setPlainText(t[-800_000:])

    def _on_finished(self, code: int, full_log: str) -> None:
        self._bar.setRange(0, 100)
        self._bar.setValue(100 if code == 0 else 0)
        self._phase_lbl.setText("Done" if code == 0 else "Finished with errors")
        if code != 0:
            self._hint_lbl.setStyleSheet("color: #FFB0A0; font-size: 12px;")
            self._hint_lbl.setText(f"Exit code {code}. See log below.")
        else:
            self._hint_lbl.setStyleSheet("color: #5DFFB0; font-size: 12px;")
            self._hint_lbl.setText("All dependency steps completed.")
        self._ok.setEnabled(True)
        self._set_close_enabled(True)
        self._worker = None
        self._last_full_log = full_log
        self._last_exit_code = int(code)

    def result_payload(self) -> tuple[int, str]:
        return int(getattr(self, "_last_exit_code", 1)), str(getattr(self, "_last_full_log", ""))


def install_dependencies_with_dialog(parent) -> tuple[int, str]:
    """
    Show modal install progress; returns (exit_code, full pip log text).
    """
    d = InstallDepsDialog(parent)
    d._last_full_log = ""
    d._last_exit_code = 1
    d.start_install()
    d.exec()
    return d.result_payload()
