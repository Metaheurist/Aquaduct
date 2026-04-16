from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def attach_api_tab(win) -> None:
    w = QWidget()
    root = QVBoxLayout(w)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setMinimumHeight(420)
    scroll.setMaximumHeight(620)

    inner = QWidget()
    scroll.setWidget(inner)
    il = QVBoxLayout(inner)
    il.setContentsMargins(0, 0, 0, 0)

    header = QLabel("API keys (Hugging Face + optional Firecrawl)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    il.addWidget(header)

    sub = QLabel(
        "Tokens are stored in ui_settings.json on this machine. "
        "You can also set HF_TOKEN / FIRECRAWL_API_KEY in the environment (env wins for Firecrawl when set)."
    )
    sub.setWordWrap(True)
    sub.setStyleSheet("color: #B7B7C2; font-size: 12px;")
    il.addWidget(sub)

    # ---- Hugging Face ----
    hf_box = QGroupBox("Hugging Face")
    hf_lay = QVBoxLayout(hf_box)

    win.api_hf_enabled_chk = QCheckBox("Use Hugging Face token for Hub (downloads + model checks)")
    win.api_hf_enabled_chk.setChecked(bool(getattr(win.settings, "hf_api_enabled", True)))
    hf_lay.addWidget(win.api_hf_enabled_chk)

    hf_hint = QLabel(
        "Create a read token at "
        '<a href="https://huggingface.co/settings/tokens">huggingface.co/settings/tokens</a>. '
        "Gated models and accurate remote size checks need a token."
    )
    hf_hint.setTextFormat(Qt.TextFormat.RichText)
    hf_hint.setOpenExternalLinks(True)
    hf_hint.setWordWrap(True)
    hf_hint.setStyleSheet(
        "QLabel { color: #9BB0C4; font-size: 12px; } "
        "QLabel a { color: #25F4EE; text-decoration: none; } "
        "QLabel a:hover { text-decoration: underline; }"
    )
    hf_lay.addWidget(hf_hint)

    form_hf = QFormLayout()
    win.api_hf_token_edit = QLineEdit()
    win.api_hf_token_edit.setPlaceholderText("hf_… (optional paste)")
    win.api_hf_token_edit.setText(str(getattr(win.settings, "hf_token", "") or ""))
    win.api_hf_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
    form_hf.addRow("Token", win.api_hf_token_edit)
    hf_lay.addLayout(form_hf)

    il.addWidget(hf_box)

    # ---- Firecrawl ----
    fc_box = QGroupBox("Firecrawl (optional)")
    fc_lay = QVBoxLayout(fc_box)

    win.api_fc_enabled_chk = QCheckBox("Use Firecrawl for headlines + article text (when a key is available)")
    win.api_fc_enabled_chk.setChecked(bool(getattr(win.settings, "firecrawl_enabled", False)))
    fc_lay.addWidget(win.api_fc_enabled_chk)

    fc_doc = QLabel(
        "Dashboard / docs: "
        '<a href="https://www.firecrawl.dev/">firecrawl.dev</a> — searches and scrapes use the HTTP API. '
        "If disabled or no key, Aquaduct uses the built-in free crawler (Google News RSS + fallbacks)."
    )
    fc_doc.setTextFormat(Qt.TextFormat.RichText)
    fc_doc.setOpenExternalLinks(True)
    fc_doc.setWordWrap(True)
    fc_doc.setStyleSheet(
        "QLabel { color: #9BB0C4; font-size: 12px; } "
        "QLabel a { color: #25F4EE; text-decoration: none; } "
        "QLabel a:hover { text-decoration: underline; }"
    )
    fc_lay.addWidget(fc_doc)

    form_fc = QFormLayout()
    win.api_fc_key_edit = QLineEdit()
    win.api_fc_key_edit.setPlaceholderText("fc-… or paste API key")
    win.api_fc_key_edit.setText(str(getattr(win.settings, "firecrawl_api_key", "") or ""))
    win.api_fc_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
    form_fc.addRow("API key", win.api_fc_key_edit)
    fc_lay.addLayout(form_fc)

    win.api_fc_key_hint = QLabel("")
    win.api_fc_key_hint.setWordWrap(True)
    win.api_fc_key_hint.setStyleSheet("color: #E8A040; font-size: 12px;")
    fc_lay.addWidget(win.api_fc_key_hint)

    il.addWidget(fc_box)
    il.addStretch(1)

    root.addWidget(scroll)

    def _refresh_fc_hint() -> None:
        en = bool(win.api_fc_enabled_chk.isChecked())
        key = str(win.api_fc_key_edit.text() or "").strip()
        if en and not key and not os.environ.get("FIRECRAWL_API_KEY"):
            win.api_fc_key_hint.setText(
                "Firecrawl is on but no key is set. Using the built-in free crawler until you save an API key "
                "or set FIRECRAWL_API_KEY."
            )
        else:
            win.api_fc_key_hint.setText("")

    win.api_fc_enabled_chk.toggled.connect(lambda _v: _refresh_fc_hint())
    win.api_fc_key_edit.textChanged.connect(lambda _v: _refresh_fc_hint())
    _refresh_fc_hint()
    if hasattr(win, "_update_hf_api_warnings"):
        win.api_hf_enabled_chk.toggled.connect(lambda _checked: win._update_hf_api_warnings())

    win.tabs.addTab(w, "API")
