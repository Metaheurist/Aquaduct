"""
Borderless dialogs with a custom title bar and ✕ button (matches MainWindow / DownloadPopup).
Use these instead of QMessageBox / framed QDialog for a consistent Aquaduct look.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEvent, QPoint, QObject, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsBlurEffect,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from UI.widgets.title_bar_outline_button import styled_outline_button


class _DimRefitFilter(QObject):
    def __init__(self, host: QWidget, refit: Callable[[], None]) -> None:
        super().__init__(host)
        self._host = host
        self._refit = refit

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if obj is self._host and event.type() == QEvent.Type.Resize:
            self._refit()
        return False


class FramelessDialog(QDialog):
    """
    Modal frameless shell: title + ✕, optional body via ``body_layout``.
    Drag by the title bar only when ``title_bar_draggable=True`` (default).

    When ``modal=True``, a dim overlay + blur is applied to the parent
    :class:`QMainWindow` central widget while the dialog is visible (ref-counted
    for nested modals).
    """

    _blur_refcount: int = 0
    _blur_host: QWidget | None = None
    _blur_effect: QGraphicsBlurEffect | None = None
    _blur_dim: QWidget | None = None
    _blur_resize_filter: _DimRefitFilter | None = None
    _blur_applied_graphics_effect: bool = False

    def __init__(
        self,
        parent=None,
        *,
        title: str = "",
        close_button_visible: bool = True,
        modal: bool = True,
        enable_main_blur: bool = True,
        title_bar_draggable: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setModal(modal)
        self._enable_main_blur = bool(enable_main_blur)
        self._title_bar_draggable = bool(title_bar_draggable)
        flags = self.windowFlags()
        flags |= Qt.WindowType.FramelessWindowHint
        flags &= ~Qt.WindowType.WindowContextHelpButtonHint
        self.setWindowFlags(flags)
        self._drag_pos: QPoint | None = None
        self.setObjectName("FramelessDialogShell")
        self.setMinimumWidth(400)
        self._blur_had_acquired = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        self._title_bar = QWidget()
        self._title_bar_layout = QHBoxLayout(self._title_bar)
        self._title_bar_layout.setContentsMargins(0, 0, 0, 8)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF;")
        self._title_bar_layout.addWidget(self._title_lbl, 1)
        close_btn = styled_outline_button("✕", "danger", fixed=(44, 32))
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.reject)
        self._title_bar_layout.addWidget(close_btn)
        self._frameless_close_button = close_btn
        if not close_button_visible:
            close_btn.hide()
        outer.addWidget(self._title_bar)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        outer.addWidget(self.body, 1)

    def _resolve_blur_host(self) -> QWidget | None:
        w = self.parentWidget()
        while w is not None and not isinstance(w, QMainWindow):
            w = w.parentWidget()
        if isinstance(w, QMainWindow):
            return w.centralWidget()
        win = self.window()
        if isinstance(win, QMainWindow):
            return win.centralWidget()
        for top in QApplication.topLevelWidgets():
            if isinstance(top, QMainWindow) and top.isVisible():
                return top.centralWidget()
        return None

    @classmethod
    def _install_main_blur(cls, host: QWidget) -> None:
        if cls._blur_host is not None and cls._blur_host is not host:
            return
        cls._blur_host = host

        def _refit() -> None:
            if cls._blur_dim is not None and cls._blur_host is not None:
                cls._blur_dim.setGeometry(cls._blur_host.rect())

        skip_blur = False
        try:
            skip_blur = host.findChild(QGraphicsView) is not None
        except Exception:
            skip_blur = False

        if not skip_blur:
            if cls._blur_effect is None:
                cls._blur_effect = QGraphicsBlurEffect(host)
                cls._blur_effect.setBlurRadius(12)
            host.setGraphicsEffect(cls._blur_effect)
            cls._blur_applied_graphics_effect = True
        else:
            cls._blur_applied_graphics_effect = False

        if cls._blur_dim is None:
            dim = QWidget(host)
            dim.setObjectName("MainWindowModalDim")
            dim.setStyleSheet("#MainWindowModalDim { background-color: rgba(8, 10, 18, 110); }")
            cls._blur_dim = dim

        if cls._blur_resize_filter is None:
            cls._blur_resize_filter = _DimRefitFilter(host, _refit)
            host.installEventFilter(cls._blur_resize_filter)

        _refit()
        cls._blur_dim.show()
        cls._blur_dim.raise_()

    @classmethod
    def _clear_main_blur(cls) -> None:
        if cls._blur_host is not None and cls._blur_resize_filter is not None:
            try:
                cls._blur_host.removeEventFilter(cls._blur_resize_filter)
            except Exception:
                pass
        cls._blur_resize_filter = None

        if cls._blur_host is not None and cls._blur_applied_graphics_effect:
            try:
                cls._blur_host.setGraphicsEffect(None)
            except Exception:
                pass
        cls._blur_applied_graphics_effect = False

        if cls._blur_dim is not None:
            try:
                cls._blur_dim.hide()
                cls._blur_dim.deleteLater()
            except Exception:
                pass

        cls._blur_dim = None
        cls._blur_effect = None
        cls._blur_host = None
        cls._blur_refcount = 0

    @classmethod
    def _blur_acquire(cls, dlg: FramelessDialog) -> None:
        if not dlg.isModal() or not dlg._enable_main_blur:
            return
        host = dlg._resolve_blur_host()
        if host is None:
            dlg._blur_had_acquired = False
            return
        dlg._blur_had_acquired = True
        cls._blur_refcount += 1
        if cls._blur_refcount == 1:
            cls._install_main_blur(host)

    @classmethod
    def _blur_release(cls, dlg: FramelessDialog) -> None:
        if not getattr(dlg, "_blur_had_acquired", False):
            return
        dlg._blur_had_acquired = False
        cls._blur_refcount = max(0, cls._blur_refcount - 1)
        if cls._blur_refcount == 0:
            cls._clear_main_blur()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        FramelessDialog._blur_acquire(self)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        FramelessDialog._blur_release(self)
        super().hideEvent(event)

    def set_frameless_title(self, t: str) -> None:
        self._title_lbl.setText(t)

    def insert_title_bar_widget_before_close(self, w: QWidget) -> None:
        """Insert a control immediately left of the title-bar ✕ (last widget in the row)."""
        lay = self._title_bar_layout
        lay.insertWidget(lay.count() - 1, w)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if (
            self._title_bar_draggable
            and event.button() == Qt.MouseButton.LeftButton
            and self._title_bar.geometry().contains(event.pos())
        ):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if (
            self._title_bar_draggable
            and self._drag_pos is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


def _muted_label(text: str, *, rich: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #B7B7C2;")
    if rich:
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setOpenExternalLinks(True)
    return lab


def aquaduct_information(parent, title: str, text: str) -> None:
    """Single OK; plain summary text."""
    d = FramelessDialog(parent, title=title)
    d.setMinimumWidth(420)
    d.body_layout.addWidget(_muted_label(text))
    row = QHBoxLayout()
    ok = styled_outline_button("OK", "accent_icon", min_width=88)
    ok.clicked.connect(d.accept)
    row.addStretch(1)
    row.addWidget(ok)
    d.body_layout.addLayout(row)
    try:
        d.exec()
    finally:
        FramelessDialog._blur_release(d)


def aquaduct_warning(parent, title: str, text: str) -> None:
    aquaduct_information(parent, title, text)


def aquaduct_critical(parent, title: str, text: str) -> None:
    aquaduct_information(parent, title, text)


def aquaduct_question(parent, title: str, text: str, *, default_no: bool = True) -> bool:
    """Yes / No. Returns True if Yes."""
    d = FramelessDialog(parent, title=title)
    d.setMinimumWidth(480)
    d.body_layout.addWidget(_muted_label(text))
    row = QHBoxLayout()
    yes = styled_outline_button("Yes", "accent_icon", min_width=76)
    no = styled_outline_button("No", "danger", min_width=76)
    row.addStretch(1)
    row.addWidget(yes)
    row.addWidget(no)
    d.body_layout.addLayout(row)

    result = {"ok": False}

    def _yes() -> None:
        result["ok"] = True
        d.accept()

    def _no() -> None:
        result["ok"] = False
        d.reject()

    yes.clicked.connect(_yes)
    no.clicked.connect(_no)
    if default_no:
        no.setDefault(True)
        no.setAutoDefault(True)
    else:
        yes.setDefault(True)
        yes.setAutoDefault(True)
    try:
        d.exec()
    finally:
        FramelessDialog._blur_release(d)
    return bool(result["ok"])


def aquaduct_message_with_details(
    parent,
    title: str,
    main_text: str,
    informative_text: str = "",
    details_text: str = "",
    *,
    min_width: int = 520,
    min_height: int = 360,
) -> None:
    """OK only; optional scrollable details (e.g. integrity report)."""
    d = FramelessDialog(parent, title=title)
    d.setMinimumSize(min_width, min_height)
    d.body_layout.addWidget(_muted_label(main_text))

    if (informative_text or "").strip():
        sub = QLabel(informative_text)
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #B7B7C2; font-size: 12px;")
        d.body_layout.addWidget(sub)

    raw = (details_text or "").strip()
    if raw:
        det = QTextEdit()
        det.setReadOnly(True)
        det.setPlainText(raw)
        det.setMinimumHeight(200)
        d.body_layout.addWidget(det, 1)

    row = QHBoxLayout()
    ok = styled_outline_button("OK", "accent_icon", min_width=88)
    ok.clicked.connect(d.accept)
    row.addStretch(1)
    row.addWidget(ok)
    d.body_layout.addLayout(row)
    try:
        d.exec()
    finally:
        FramelessDialog._blur_release(d)


def show_hf_token_dialog(parent) -> tuple[bool, str]:
    """
    Borderless Hugging Face token prompt. Returns (accepted, token) - token may be empty if cancelled.
    """
    dlg = FramelessDialog(parent, title="Hugging Face token (recommended)")
    dlg.setMinimumWidth(520)

    _hf_tokens = "https://huggingface.co/settings/tokens"
    hint = QLabel(
        "Some models and size lookups require a Hugging Face access token.<br><br>"
        "<b>How to get one:</b><br>"
        f'- Go to <a href="{_hf_tokens}">{_hf_tokens}</a><br>'
        "- Create a token (a standard read-only token is enough)<br>"
        "- Paste it below<br><br>"
        "We will store it in ui_settings.json and use it for authenticated Hub requests."
    )
    hint.setTextFormat(Qt.TextFormat.RichText)
    hint.setOpenExternalLinks(True)
    hint.setWordWrap(True)
    hint.setStyleSheet(
        "QLabel { color: #B7B7C2; } "
        "QLabel a { color: #25F4EE; text-decoration: none; } "
        "QLabel a:hover { text-decoration: underline; }"
    )
    dlg.body_layout.addWidget(hint)

    inp = QLineEdit()
    inp.setPlaceholderText("hf_... (paste your token here)")
    inp.setEchoMode(QLineEdit.EchoMode.Password)
    dlg.body_layout.addWidget(inp)

    row = QHBoxLayout()
    cancel = styled_outline_button("Cancel", "muted_icon", min_width=96)
    cancel.clicked.connect(dlg.reject)
    ok = styled_outline_button("OK", "accent_icon", min_width=88)
    row.addStretch(1)
    row.addWidget(cancel)
    row.addWidget(ok)

    def _accept() -> None:
        dlg.accept()

    ok.clicked.connect(_accept)
    inp.returnPressed.connect(_accept)
    dlg.body_layout.addLayout(row)

    try:
        code = dlg.exec()
    finally:
        FramelessDialog._blur_release(dlg)
    return code == QDialog.DialogCode.Accepted, str(inp.text() or "").strip()
