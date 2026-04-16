from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
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

    # ---- TikTok (optional upload) ----
    tt_box = QGroupBox("TikTok (Content Posting API)")
    tt_lay = QVBoxLayout(tt_box)

    win.api_tt_enabled_chk = QCheckBox("Enable TikTok upload from the Tasks tab")
    win.api_tt_enabled_chk.setChecked(bool(getattr(win.settings, "tiktok_enabled", False)))
    tt_lay.addWidget(win.api_tt_enabled_chk)

    tt_doc = QLabel(
        "Register an app at "
        '<a href="https://developers.tiktok.com/">developers.tiktok.com</a>, add this redirect URI to Login Kit, '
        "then connect. Uses OAuth + inbox upload (open TikTok app to finish posting). See docs/tiktok.md."
    )
    tt_doc.setTextFormat(Qt.TextFormat.RichText)
    tt_doc.setOpenExternalLinks(True)
    tt_doc.setWordWrap(True)
    tt_doc.setStyleSheet(
        "QLabel { color: #9BB0C4; font-size: 12px; } "
        "QLabel a { color: #25F4EE; text-decoration: none; } "
        "QLabel a:hover { text-decoration: underline; }"
    )
    tt_lay.addWidget(tt_doc)

    form_tt = QFormLayout()
    win.api_tt_client_key = QLineEdit()
    win.api_tt_client_key.setPlaceholderText("Client key from TikTok developer portal")
    win.api_tt_client_key.setText(str(getattr(win.settings, "tiktok_client_key", "") or ""))
    form_tt.addRow("Client key", win.api_tt_client_key)

    win.api_tt_client_secret = QLineEdit()
    win.api_tt_client_secret.setPlaceholderText("Client secret")
    win.api_tt_client_secret.setText(str(getattr(win.settings, "tiktok_client_secret", "") or ""))
    win.api_tt_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
    form_tt.addRow("Client secret", win.api_tt_client_secret)

    win.api_tt_redirect_uri = QLineEdit()
    win.api_tt_redirect_uri.setText(
        str(getattr(win.settings, "tiktok_redirect_uri", "") or "http://127.0.0.1:8765/callback/")
    )
    win.api_tt_redirect_uri.setPlaceholderText("http://127.0.0.1:8765/callback/")
    form_tt.addRow("Redirect URI", win.api_tt_redirect_uri)

    win.api_tt_oauth_port = QSpinBox()
    win.api_tt_oauth_port.setRange(8000, 65535)
    win.api_tt_oauth_port.setValue(int(getattr(win.settings, "tiktok_oauth_port", 8765)))
    form_tt.addRow("OAuth port", win.api_tt_oauth_port)

    win.api_tt_pub_mode = QComboBox()
    win.api_tt_pub_mode.addItem("Inbox (finish in TikTok app) — video.upload", "inbox")
    win.api_tt_pub_mode.addItem("Direct post (video.publish — needs app review)", "direct")
    pm = str(getattr(win.settings, "tiktok_publishing_mode", "inbox") or "inbox")
    idxp = win.api_tt_pub_mode.findData(pm)
    win.api_tt_pub_mode.setCurrentIndex(idxp if idxp >= 0 else 0)
    form_tt.addRow("Publishing", win.api_tt_pub_mode)

    win.api_tt_auto_upload_chk = QCheckBox("Auto-start TikTok upload when a render finishes (Tasks)")
    win.api_tt_auto_upload_chk.setChecked(bool(getattr(win.settings, "tiktok_auto_upload_after_render", False)))
    tt_lay.addWidget(win.api_tt_auto_upload_chk)

    tt_lay.addLayout(form_tt)

    row_tt = QHBoxLayout()
    win.api_tt_connect_btn = QPushButton("Connect TikTok account")
    win.api_tt_connect_btn.setObjectName("primary")
    win.api_tt_connect_btn.clicked.connect(win._tiktok_connect_clicked)
    row_tt.addWidget(win.api_tt_connect_btn)
    row_tt.addStretch(1)
    tt_lay.addLayout(row_tt)

    win.api_tt_status_lbl = QLabel("")
    win.api_tt_status_lbl.setWordWrap(True)
    win.api_tt_status_lbl.setStyleSheet("color: #8A96A3; font-size: 12px;")
    if str(getattr(win.settings, "tiktok_refresh_token", "") or "").strip():
        win.api_tt_status_lbl.setText("Status: tokens on file — connect again to refresh.")
    else:
        win.api_tt_status_lbl.setText("Status: not connected")
    tt_lay.addWidget(win.api_tt_status_lbl)

    il.addWidget(tt_box)

    # ---- YouTube (optional Shorts / uploads) ----
    yt_box = QGroupBox("YouTube (Data API v3)")
    yt_lay = QVBoxLayout(yt_box)

    win.api_yt_enabled_chk = QCheckBox("Enable YouTube upload from the Tasks tab")
    win.api_yt_enabled_chk.setChecked(bool(getattr(win.settings, "youtube_enabled", False)))
    yt_lay.addWidget(win.api_yt_enabled_chk)

    yt_doc = QLabel(
        "Create OAuth credentials (Desktop) in Google Cloud, enable YouTube Data API v3, "
        "and add the redirect URI to the client. "
        'Guide: <a href="https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps">Google OAuth</a> — '
        "see docs/youtube.md in this repo."
    )
    yt_doc.setTextFormat(Qt.TextFormat.RichText)
    yt_doc.setOpenExternalLinks(True)
    yt_doc.setWordWrap(True)
    yt_doc.setStyleSheet(
        "QLabel { color: #9BB0C4; font-size: 12px; } "
        "QLabel a { color: #25F4EE; text-decoration: none; } "
        "QLabel a:hover { text-decoration: underline; }"
    )
    yt_lay.addWidget(yt_doc)

    form_yt = QFormLayout()
    win.api_yt_client_id = QLineEdit()
    win.api_yt_client_id.setPlaceholderText("OAuth client ID (.apps.googleusercontent.com)")
    win.api_yt_client_id.setText(str(getattr(win.settings, "youtube_client_id", "") or ""))
    form_yt.addRow("Client ID", win.api_yt_client_id)

    win.api_yt_client_secret = QLineEdit()
    win.api_yt_client_secret.setPlaceholderText("OAuth client secret")
    win.api_yt_client_secret.setText(str(getattr(win.settings, "youtube_client_secret", "") or ""))
    win.api_yt_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
    form_yt.addRow("Client secret", win.api_yt_client_secret)

    win.api_yt_redirect_uri = QLineEdit()
    win.api_yt_redirect_uri.setText(
        str(getattr(win.settings, "youtube_redirect_uri", "") or "http://127.0.0.1:8888/callback/")
    )
    win.api_yt_redirect_uri.setPlaceholderText("http://127.0.0.1:8888/callback/")
    form_yt.addRow("Redirect URI", win.api_yt_redirect_uri)

    win.api_yt_oauth_port = QSpinBox()
    win.api_yt_oauth_port.setRange(8000, 65535)
    win.api_yt_oauth_port.setValue(int(getattr(win.settings, "youtube_oauth_port", 8888)))
    form_yt.addRow("OAuth port", win.api_yt_oauth_port)

    win.api_yt_privacy = QComboBox()
    win.api_yt_privacy.addItem("Private (recommended for testing)", "private")
    win.api_yt_privacy.addItem("Unlisted", "unlisted")
    win.api_yt_privacy.addItem("Public", "public")
    pv = str(getattr(win.settings, "youtube_privacy_status", "private") or "private")
    iy = win.api_yt_privacy.findData(pv)
    win.api_yt_privacy.setCurrentIndex(iy if iy >= 0 else 0)
    form_yt.addRow("Default privacy", win.api_yt_privacy)

    win.api_yt_shorts_tag_chk = QCheckBox('Add #Shorts to title/description when missing (helps Shorts discovery)')
    win.api_yt_shorts_tag_chk.setChecked(bool(getattr(win.settings, "youtube_add_shorts_hashtag", True)))
    yt_lay.addWidget(win.api_yt_shorts_tag_chk)

    win.api_yt_auto_upload_chk = QCheckBox("Auto-start YouTube upload when a render finishes (Tasks)")
    win.api_yt_auto_upload_chk.setChecked(bool(getattr(win.settings, "youtube_auto_upload_after_render", False)))
    yt_lay.addWidget(win.api_yt_auto_upload_chk)

    yt_lay.addLayout(form_yt)

    row_yt = QHBoxLayout()
    win.api_yt_connect_btn = QPushButton("Connect YouTube account")
    win.api_yt_connect_btn.setObjectName("primary")
    win.api_yt_connect_btn.clicked.connect(win._youtube_connect_clicked)
    row_yt.addWidget(win.api_yt_connect_btn)
    row_yt.addStretch(1)
    yt_lay.addLayout(row_yt)

    win.api_yt_status_lbl = QLabel("")
    win.api_yt_status_lbl.setWordWrap(True)
    win.api_yt_status_lbl.setStyleSheet("color: #8A96A3; font-size: 12px;")
    if str(getattr(win.settings, "youtube_refresh_token", "") or "").strip():
        win.api_yt_status_lbl.setText("Status: tokens on file — connect again to refresh.")
    else:
        win.api_yt_status_lbl.setText("Status: not connected")
    yt_lay.addWidget(win.api_yt_status_lbl)

    il.addWidget(yt_box)

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
