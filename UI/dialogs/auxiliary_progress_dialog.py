"""
Modal progress for short off-pipeline jobs (brain expand, character LLM, portrait, topic grounding).

Frameless, fixed-size shell aligned with MainWindow / :class:`FramelessDialog`.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QLabel, QProgressBar, QWidget

from UI.dialogs.frameless_dialog import FramelessDialog


def map_llm_on_task_to_overall(task: str, stage_pct: int) -> int:
    """
    Map brain ``on_llm_task(task, pct, msg)`` to a single 0–100 bar.

    Uses a 40% band for tokenizer/model load (``llm_load``) and 60% for decode (``llm_generate``).
    Unknown task names fall through to clamped ``stage_pct``.
    """
    sp = max(0, min(100, int(stage_pct)))
    t = (task or "").strip().lower()
    if t == "llm_load":
        return int(40 * sp / 100)
    if t == "llm_generate":
        return 40 + int(60 * sp / 100)
    return sp


class _AuxiliaryProgressShell(FramelessDialog):
    """Borderless modal; no ✕ — job has no cancel. Ignore Escape while work runs. Not draggable."""

    def __init__(self, parent: QWidget | None, *, title: str) -> None:
        super().__init__(parent, title=title, close_button_visible=False, title_bar_draggable=False)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)


class AuxiliaryProgressDialog:
    """
    Fixed-size frameless modal — matches app chrome; worker ``progress(int, str)`` updates safely.
    """

    def __init__(self, parent: QWidget | None, *, window_title: str, initial_message: str = "Starting…") -> None:
        ttl = str(window_title or "Working").strip() or "Working"
        self._dlg = _AuxiliaryProgressShell(parent, title=ttl)
        self._dlg.setFixedSize(520, 128)
        try:
            self._dlg.setWindowModality(Qt.WindowModality.WindowModal)
            self._dlg.setModal(True)
        except Exception:
            pass

        self._lbl = QLabel(str(initial_message or "…").strip() or "…")
        self._lbl.setWordWrap(True)
        self._lbl.setStyleSheet("color: #B7B7C2;")

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)

        lay = self._dlg.body_layout
        lay.addWidget(self._lbl)
        lay.addWidget(self._bar)

    def show(self) -> None:
        self._dlg.show()

    def set_indeterminate(self, message: str) -> None:
        self._bar.setRange(0, 0)
        self._lbl.setText(str(message or "").strip() or "…")

    def set_determinate(self) -> None:
        if self._bar.minimum() == 0 and self._bar.maximum() == 0:
            self._bar.setRange(0, 100)

    def slot_update(self, overall_pct: int, message: str) -> None:
        """Connected to worker ``progress`` signal."""
        self.set_determinate()
        pct = max(0, min(100, int(overall_pct)))
        try:
            self._bar.setValue(pct)
        except Exception:
            pass
        try:
            msg = str(message or "").strip()
            if msg:
                self._lbl.setText(msg[:2000])
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._dlg.close()
        except Exception:
            pass


def schedule_auxiliary_job_memory_purge() -> None:
    """After an auxiliary worker finishes — flush CUDA cache / GC from the GUI thread."""

    def _purge() -> None:
        try:
            from src.util.utils_vram import purge_process_memory_aggressive

            purge_process_memory_aggressive()
        except Exception:
            pass

    QTimer.singleShot(0, _purge)
