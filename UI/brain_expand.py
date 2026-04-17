"""
Float a small brain control on custom text fields to expand/improve text via the local LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit, QTextEdit, QToolButton, QWidget

from UI.frameless_dialog import aquaduct_warning

from src.config import get_models

if TYPE_CHECKING:
    pass


def resolve_llm_model_id(win) -> str:
    models = get_models()
    mid = str(getattr(getattr(win, "settings", None), "llm_model_id", "") or "").strip()
    return mid or models.llm_id


class BrainAugmentedEditor(QWidget):
    """
    Paints a QTextEdit or QLineEdit full-frame with a brain button in the top-right corner.
    """

    def __init__(self, editor: QTextEdit | QLineEdit, field_label: str, win) -> None:
        super().__init__(win if isinstance(win, QWidget) else None)
        self._ed = editor
        self._field_label = field_label
        self._win = win
        self._worker = None

        editor.setParent(self)
        if isinstance(editor, QTextEdit):
            try:
                editor.setViewportMargins(0, 0, 36, 0)
            except Exception:
                pass
        else:
            prev = (editor.styleSheet() or "").strip()
            if "padding-right" not in prev.lower():
                editor.setStyleSheet((prev + "; " if prev else "") + "padding-right: 34px;")

        self._btn = QToolButton(self)
        self._btn.setObjectName("brainExpandBtn")
        self._btn.setText("\u2009🧠")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setToolTip(f"Expand / improve with LLM — {field_label}")
        self._btn.setAutoRaise(True)
        self._btn.setStyleSheet(
            "QToolButton#brainExpandBtn {"
            " background: rgba(34,36,42,0.94);"
            " border: 1px solid #5A5F70;"
            " border-radius: 7px;"
            " font-size: 13px;"
            " padding: 1px 5px;"
            "}"
            "QToolButton#brainExpandBtn:hover { background: rgba(48,52,62,0.96); border-color: #7A8194; }"
            "QToolButton#brainExpandBtn:disabled { color: #666; border-color: #444; }"
        )
        self._btn.clicked.connect(self._on_brain_clicked)

    def resizeEvent(self, e) -> None:  # type: ignore[override]
        super().resizeEvent(e)
        self._ed.setGeometry(0, 0, self.width(), self.height())
        m = 6
        self._btn.move(self.width() - self._btn.width() - m, m)
        self._btn.raise_()

    def minimumSizeHint(self):  # type: ignore[no-untyped-def]
        return self._ed.minimumSizeHint()

    def sizeHint(self):  # type: ignore[no-untyped-def]
        return self._ed.sizeHint()

    def _seed_text(self) -> str:
        if isinstance(self._ed, QTextEdit):
            return self._ed.toPlainText()
        return self._ed.text()

    def _apply_result(self, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        if isinstance(self._ed, QTextEdit):
            self._ed.setPlainText(t)
        else:
            self._ed.setText(t)

    def _on_brain_clicked(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        from UI.workers import TextExpandWorker

        mid = resolve_llm_model_id(self._win)
        self._btn.setEnabled(False)
        self._btn.setToolTip("Working… (loading model may take a while)")
        self._worker = TextExpandWorker(
            model_id=mid,
            field_label=self._field_label,
            seed=self._seed_text(),
        )

        def _ok(out: str) -> None:
            self._btn.setEnabled(True)
            self._btn.setToolTip(f"Expand / improve with LLM — {self._field_label}")
            self._apply_result(out)
            self._worker = None
            if hasattr(self._win, "_append_log"):
                try:
                    self._win._append_log(f"LLM expanded: {self._field_label}")
                except Exception:
                    pass

        def _fail(err: str) -> None:
            self._btn.setEnabled(True)
            self._btn.setToolTip(f"Expand / improve with LLM — {self._field_label}")
            self._worker = None
            if hasattr(self._win, "_append_log"):
                self._win._append_log(f"LLM expand failed ({self._field_label}):\n{err}")
            short = (err or "")[:1800]
            try:
                aquaduct_warning(
                    self._win if isinstance(self._win, QWidget) else None,
                    "LLM expand failed",
                    short,
                )
            except Exception:
                pass

        self._worker.done.connect(_ok)
        self._worker.failed.connect(_fail)
        self._worker.start()


def wrap_editor_with_brain(editor: QTextEdit | QLineEdit, field_label: str, win) -> BrainAugmentedEditor:
    """
    Return a container widget that shows ``editor`` with a brain button. Keep using ``editor``
    for reads/writes (same object as before).
    """
    return BrainAugmentedEditor(editor, field_label, win)
