"""Lightweight non-modal toast notifications (auto-dismissing) for routine feedback.

The app has no QStatusBar/snackbar; routine confirmations ("Settings saved", "Queued N
videos", "Cache cleared") previously went only to a modal or the (invisible) activity log.
``show_toast`` renders a small palette-styled pill in the bottom-center of a host window that
fades out on its own, so feedback is visible without interrupting the user.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from UI.theme import token

_KIND_ACCENT = {
    "info": "accent",
    "success": "accent",
    "warning": "danger",
    "error": "danger",
}


class _Toast(QFrame):
    def __init__(self, host: QWidget, message: str, kind: str) -> None:
        super().__init__(host)
        self.setObjectName("ToastPill")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        accent = token(_KIND_ACCENT.get(kind, "accent"), "#25F4EE")
        panel = token("panel", "#0B0B0F")
        text_c = token("text", "#FFFFFF")
        self.setStyleSheet(
            "QFrame#ToastPill { background: %s; border: 1px solid %s; border-radius: 12px; }"
            % (panel, accent)
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lab = QLabel(message)
        lab.setStyleSheet(f"color: {text_c}; font-size: 12px; font-weight: 600; background: transparent;")
        lay.addWidget(lab)
        self.adjustSize()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)


def show_toast(host: QWidget | None, message: str, *, kind: str = "info", msec: int = 2600) -> None:
    """Show an auto-dismissing toast pill near the bottom of ``host``.

    ``kind`` is one of info/success/warning/error (controls border accent). Safe no-op when
    ``host`` is None. Multiple toasts stack from the bottom up.
    """
    if host is None or not message:
        return
    try:
        toast = _Toast(host, message, kind)
    except Exception:
        return

    existing = [c for c in host.children() if isinstance(c, _Toast) and c is not toast and c.isVisible()]
    margin = 24
    spacing = 8
    y = host.height() - margin - toast.height()
    for w in reversed(existing):
        y -= w.height() + spacing
    x = max(margin, (host.width() - toast.width()) // 2)
    toast.move(x, y)
    toast.show()
    toast.raise_()

    fade_in = QPropertyAnimation(toast._effect, b"opacity", toast)
    fade_in.setDuration(180)
    fade_in.setStartValue(0.0)
    fade_in.setEndValue(1.0)
    fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
    fade_in.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _begin_fade_out() -> None:
        fade_out = QPropertyAnimation(toast._effect, b"opacity", toast)
        fade_out.setDuration(320)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        fade_out.finished.connect(toast.deleteLater)
        fade_out.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        # Keep a reference on the toast so it is not GC'd mid-animation.
        toast._fade_out = fade_out  # type: ignore[attr-defined]

    QTimer.singleShot(max(600, int(msec)), _begin_fade_out)
