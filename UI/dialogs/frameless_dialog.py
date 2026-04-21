"""
Borderless dialogs with a custom title bar and ✕ button (matches MainWindow / DownloadPopup).
Use these instead of QMessageBox / framed QDialog for a consistent Aquaduct look.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from UI.widgets.title_bar_outline_button import styled_outline_button


class FramelessDialog(QDialog):
    """
    Modal frameless shell: title + ✕, optional body via ``body_layout``.
    Drag by the title bar only.
    """

    def __init__(self, parent=None, *, title: str = "") -> None:
        super().__init__(parent)
        self.setModal(True)
        flags = self.windowFlags()
        flags |= Qt.WindowType.FramelessWindowHint
        flags &= ~Qt.WindowType.WindowContextHelpButtonHint
        self.setWindowFlags(flags)
        self._drag_pos: QPoint | None = None
        self.setObjectName("FramelessDialogShell")
        self.setMinimumWidth(400)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        self._title_bar = QWidget()
        tb = QHBoxLayout(self._title_bar)
        tb.setContentsMargins(0, 0, 0, 8)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF;")
        tb.addWidget(self._title_lbl, 1)
        close_btn = styled_outline_button("✕", "danger", fixed=(44, 32))
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.reject)
        tb.addWidget(close_btn)
        self._frameless_close_button = close_btn
        outer.addWidget(self._title_bar)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        outer.addWidget(self.body, 1)

    def set_frameless_title(self, t: str) -> None:
        self._title_lbl.setText(t)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            if self._title_bar.geometry().contains(event.pos()):
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
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
    d.exec()


def aquaduct_warning(parent, title: str, text: str) -> None:
    aquaduct_information(parent, title, text)  # same chrome; copy uses neutral label


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
    d.exec()
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
    d.exec()


def show_hf_token_dialog(parent) -> tuple[bool, str]:
    """
    Borderless Hugging Face token prompt. Returns (accepted, token) — token may be empty if cancelled.
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

    code = dlg.exec()
    return code == QDialog.DialogCode.Accepted, str(inp.text() or "").strip()
