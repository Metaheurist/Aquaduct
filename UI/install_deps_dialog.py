"""Modal progress UI for Model tab → Install dependencies (streaming pip output)."""

from __future__ import annotations

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
)

from UI.frameless_dialog import FramelessDialog

from src.models.torch_install import (
    PipSubprocessRef,
    install_pytorch_for_hardware,
    install_requirements_runtime,
    pip_download_percent,
    pip_line_hint,
)

# Large PyTorch/CUDA wheels may not print a new log line for several minutes.
_PIP_ACK_WARN_AFTER_MS = 120_000


class DepsInstallWorker(QThread):
    """Runs PyTorch pip step then requirements.txt in a background thread."""

    phase = pyqtSignal(str)
    hint = pyqtSignal(str)
    line = pyqtSignal(str)
    progress_pct = pyqtSignal(int)
    pip_ack = pyqtSignal(str)
    finished_ex = pyqtSignal(int, str)

    def __init__(self, pip_ref: PipSubprocessRef) -> None:
        super().__init__()
        self._pip_ref = pip_ref

    def run(self) -> None:
        def on_line(line: str) -> None:
            self.line.emit(line)
            h = pip_line_hint(line)
            if h:
                self.hint.emit(h)
            pct = pip_download_percent(line)
            if pct is not None:
                self.progress_pct.emit(pct)

        def on_first_pip_output(seg: str) -> None:
            self.pip_ack.emit(seg[:400])

        try:
            self.phase.emit("Step 1/2 — PyTorch (torch, torchvision, torchaudio)")
            c1, o1 = install_pytorch_for_hardware(
                upgrade=True,
                force_cuda_if_applicable=True,
                on_line=on_line,
                on_first_pip_output=on_first_pip_output,
                subprocess_ref=self._pip_ref,
            )
            if c1 != 0:
                self.finished_ex.emit(c1, o1)
                return

            self.phase.emit("Step 2/2 — requirements.txt (transformers, accelerate, …)")
            c2, o2 = install_requirements_runtime(
                on_line=on_line,
                on_first_pip_output=on_first_pip_output,
                subprocess_ref=self._pip_ref,
            )
            self.finished_ex.emit(c2, o1 + "\n\n" + o2)
        except Exception as e:
            self.finished_ex.emit(1, f"Install worker error: {e!s}")


class InstallDepsDialog(FramelessDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Installing dependencies")
        self.setMinimumSize(560, 420)
        self._worker: DepsInstallWorker | None = None
        self._pip_ref = PipSubprocessRef()
        self._cancel_requested = False
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

        self._pip_ack_lbl = QLabel()
        self._pip_ack_lbl.setWordWrap(True)
        self._pip_ack_received = False
        self._ack_timer = QTimer(self)
        self._ack_timer.setSingleShot(True)
        self._ack_timer.timeout.connect(self._on_pip_ack_timeout)
        self._reset_pip_ack_ui()
        self.body_layout.addWidget(self._pip_ack_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(True)
        # Indeterminate mode: %p% is meaningless; show a label so the bar does not look "empty".
        self._bar.setFormat("Working…")
        self._bar.setMinimumHeight(16)
        self._bar.setStyleSheet(
            "QProgressBar { border: 1px solid #3A3A44; border-radius: 6px; background: #1e1e24; color: #B7B7C2; }"
            "QProgressBar::chunk { background: #25F4EE; border-radius: 5px; }"
        )
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
        self._ok.setEnabled(True)
        self._ok.clicked.connect(self._on_close_clicked)
        row.addStretch(1)
        row.addWidget(self._ok)
        self.body_layout.addLayout(row)

        self._close_btn = self.findChild(QPushButton, "closeBtn")

    def reject(self) -> None:  # type: ignore[override]
        if self._worker is not None and self._worker.isRunning():
            self._request_cancel()
            return
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._worker is not None and self._worker.isRunning():
            self._request_cancel()
            event.ignore()
            return
        super().closeEvent(event)

    def _set_close_enabled(self, on: bool) -> None:
        if self._close_btn is not None:
            try:
                self._close_btn.setEnabled(on)
            except Exception:
                pass

    def _on_close_clicked(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.reject()
        else:
            self.accept()

    def _request_cancel(self) -> None:
        if self._cancel_requested:
            return
        self._cancel_requested = True
        self._ack_timer.stop()
        self._pip_ref.kill()
        self._phase_lbl.setText("Cancelling…")
        self._hint_lbl.setText("Stopping pip…")
        self._ok.setEnabled(False)
        self._set_close_enabled(False)

    def start_install(self) -> None:
        self._cancel_requested = False
        self._reset_pip_ack_ui()
        self._worker = DepsInstallWorker(self._pip_ref)
        self._worker.phase.connect(self._on_phase)
        self._worker.hint.connect(self._hint_lbl.setText)
        self._worker.line.connect(self._append_log_line)
        self._worker.progress_pct.connect(self._on_download_percent)
        self._worker.pip_ack.connect(self._on_pip_ack)
        self._worker.finished_ex.connect(self._on_finished)
        self._ok.setText("Cancel")
        self._ok.setEnabled(True)
        self._set_close_enabled(True)
        self._worker.start()

    def _reset_pip_ack_ui(self) -> None:
        self._pip_ack_received = False
        self._pip_ack_lbl.setText(
            "Waiting for pip’s first log line (below). Until then, if Task Manager shows network or disk "
            "activity on the pip worker (on Windows: aquaduct-pip-*.exe), the download is usually still running — it can be slow."
        )
        self._pip_ack_lbl.setStyleSheet("color: #E7C86B; font-size: 12px; font-weight: 600;")
        self._pip_ack_lbl.setToolTip("")
        self._ack_timer.stop()
        self._ack_timer.start(_PIP_ACK_WARN_AFTER_MS)

    def _on_pip_ack(self, snippet: str) -> None:
        self._pip_ack_received = True
        self._ack_timer.stop()
        self._pip_ack_lbl.setText("✓ Pip confirmed — first output received. Download/install is active.")
        self._pip_ack_lbl.setStyleSheet("color: #5DFFB0; font-size: 12px; font-weight: 600;")
        self._pip_ack_lbl.setToolTip(snippet.strip())

    def _on_pip_ack_timeout(self) -> None:
        if self._pip_ack_received:
            return
        self._pip_ack_lbl.setText(
            "⚠ Still no new lines in the log after 2 minutes. That can be normal for huge wheels — "
            "if Task Manager still shows network or disk on aquaduct-pip-*.exe (or python.exe), pip is probably still downloading. "
            "Worry if both stay at 0 for a long time, or use Cancel and run pip in a terminal to see errors."
        )
        self._pip_ack_lbl.setStyleSheet("color: #E7C86B; font-size: 12px; font-weight: 600;")

    def _on_phase(self, text: str) -> None:
        self._phase_lbl.setText(text)
        self._bar.setRange(0, 0)
        self._bar.setFormat("Working…")
        self._reset_pip_ack_ui()

    def _on_download_percent(self, pct: int) -> None:
        self._bar.setRange(0, 100)
        self._bar.setFormat("%p%")
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
        self._ack_timer.stop()
        cancelled = self._cancel_requested
        self._cancel_requested = False
        self._worker = None
        if cancelled:
            self._bar.setRange(0, 100)
            self._bar.setFormat("%p%")
            self._bar.setValue(0)
            self._phase_lbl.setText("Cancelled")
            self._hint_lbl.setStyleSheet("color: #FFB0A0; font-size: 12px;")
            self._hint_lbl.setText("Installation was cancelled.")
            self._ok.setText("Close")
            self._ok.setEnabled(True)
            self._set_close_enabled(True)
            self._last_exit_code = 1
            self._last_full_log = (full_log or "").strip() + "\n\nInstall cancelled by user."
            super().reject()
            return
        self._bar.setRange(0, 100)
        self._bar.setFormat("%p%")
        self._bar.setValue(100 if code == 0 else 0)
        self._phase_lbl.setText("Done" if code == 0 else "Finished with errors")
        if code != 0:
            self._hint_lbl.setStyleSheet("color: #FFB0A0; font-size: 12px;")
            self._hint_lbl.setText(f"Exit code {code}. See log below.")
        else:
            self._hint_lbl.setStyleSheet("color: #5DFFB0; font-size: 12px;")
            self._hint_lbl.setText("All dependency steps completed.")
        self._ok.setText("Close")
        self._ok.setEnabled(True)
        self._set_close_enabled(True)
        self._last_full_log = full_log
        self._last_exit_code = int(code)

    def result_payload(self) -> tuple[int, str]:
        return int(getattr(self, "_last_exit_code", 1)), str(getattr(self, "_last_full_log", ""))


def install_dependencies_with_dialog(parent) -> tuple[int, str]:
    """
    Show modal install progress; returns (exit_code, full pip log text).
    Writes a copy under ``logs/install-dependencies-<timestamp>.log``.
    """
    d = InstallDepsDialog(parent)
    d._last_full_log = ""
    d._last_exit_code = 1
    d.start_install()
    d.exec()
    code, log = d.result_payload()
    try:
        from src.util.repo_logs import write_install_dependencies_log

        write_install_dependencies_log(log)
    except Exception:
        pass
    return code, log
