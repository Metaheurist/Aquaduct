from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from UI.help.tutorial_links import help_tooltip_rich
from UI.widgets.no_wheel_controls import NoWheelComboBox, NoWheelSpinBox
from UI.widgets.themed_switch import ThemedSwitch
from UI.widgets.basic_advanced import register_advanced_sections
from UI.widgets.tab_scaffold import make_tab_root
from UI.widgets.tab_sections import add_section_spacing, section_card, section_title
from UI.widgets.visual_primitives import ProviderCard


def attach_api_tab(win) -> None:
    w = QWidget()
    root = QVBoxLayout(w)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))

    from UI.services.api_model_widgets import build_generation_api_panel

    win.generation_api_panel = build_generation_api_panel(win)
    _api_gen_strip = QWidget()
    win._api_gen_panel_parent_layout = QVBoxLayout(_api_gen_strip)
    win._api_gen_panel_parent_layout.setContentsMargins(0, 0, 0, 0)
    win._api_gen_panel_parent_layout.setSpacing(6)
    win.generation_api_panel.setToolTip(
        help_tooltip_rich(
            "Cloud generation providers. The same panel appears on the Model tab when it runs in API mode.",
            "api_social",
            slide=0,
        )
    )
    win._api_gen_panel_parent_layout.addWidget(win.generation_api_panel)

    inner_root, _, _, lay = make_tab_root(
        title="API",
        intro_text="Keys saved locally on this machine.",
        tab_id="api",
        win=win,
        basic_advanced=True,
        before_card=(_api_gen_strip,),
    )
    scroll.setWidget(inner_root)
    il = lay

    # ---- Hugging Face ----
    win.api_hf_enabled_chk = ThemedSwitch("Enabled")
    win.api_hf_enabled_chk.setChecked(bool(getattr(win.settings, "hf_api_enabled", True)))
    win.api_hf_token_edit = QLineEdit()
    win.api_hf_token_edit.setPlaceholderText("hf_… (optional paste)")
    win.api_hf_token_edit.setText(str(getattr(win.settings, "hf_token", "") or ""))
    win.api_hf_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
    hf_hint = QLabel("Token: huggingface.co/settings/tokens")
    hf_hint.setStyleSheet("color: #9BB0C4; font-size: 11px;")
    win._api_advanced_hf_hint = hf_hint
    hf_card = ProviderCard(
        "Hugging Face",
        switch=win.api_hf_enabled_chk,
        key_edit=win.api_hf_token_edit,
        status="Models & downloads",
    )
    hf_wrap = QWidget()
    hf_wrap_lay = QVBoxLayout(hf_wrap)
    hf_wrap_lay.setContentsMargins(0, 0, 0, 0)
    hf_wrap_lay.addWidget(hf_card)
    hf_wrap_lay.addWidget(hf_hint)
    il.addWidget(hf_wrap)
    add_section_spacing(il)

    # ---- Firecrawl ----
    win.api_fc_enabled_chk = ThemedSwitch("Enabled")
    win.api_fc_enabled_chk.setChecked(bool(getattr(win.settings, "firecrawl_enabled", False)))
    win.api_fc_key_edit = QLineEdit()
    win.api_fc_key_edit.setPlaceholderText("fc-… or paste API key")
    win.api_fc_key_edit.setText(str(getattr(win.settings, "firecrawl_api_key", "") or ""))
    win.api_fc_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
    fc_doc = QLabel("Optional — richer web search.")
    fc_doc.setStyleSheet("color: #9BB0C4; font-size: 11px;")
    fc_card = ProviderCard("Firecrawl", switch=win.api_fc_enabled_chk, key_edit=win.api_fc_key_edit, status="Web discover")
    fc_wrap = QWidget()
    fc_wrap_lay = QVBoxLayout(fc_wrap)
    fc_wrap_lay.setContentsMargins(0, 0, 0, 0)
    fc_wrap_lay.addWidget(fc_card)
    fc_wrap_lay.addWidget(fc_doc)
    win.api_fc_key_hint = QLabel("")
    win.api_fc_key_hint.setWordWrap(True)
    win.api_fc_key_hint.setStyleSheet("color: #E8A040; font-size: 12px;")
    fc_wrap_lay.addWidget(win.api_fc_key_hint)
    il.addWidget(fc_wrap)
    add_section_spacing(il)

    # ---- ElevenLabs (optional cloud TTS) ----
    win.api_el_enabled_chk = ThemedSwitch("Enabled")
    win.api_el_enabled_chk.setChecked(bool(getattr(win.settings, "elevenlabs_enabled", False)))
    win.api_el_key_edit = QLineEdit()
    win.api_el_key_edit.setPlaceholderText("xi-api-key (optional paste)")
    win.api_el_key_edit.setText(str(getattr(win.settings, "elevenlabs_api_key", "") or ""))
    win.api_el_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
    el_doc = QLabel("Cloud TTS — falls back to local voice.")
    el_doc.setStyleSheet("color: #9BB0C4; font-size: 11px;")
    el_card = ProviderCard("ElevenLabs", switch=win.api_el_enabled_chk, key_edit=win.api_el_key_edit, status="Cloud voice")
    el_wrap = QWidget()
    el_wrap_lay = QVBoxLayout(el_wrap)
    el_wrap_lay.setContentsMargins(0, 0, 0, 0)
    el_wrap_lay.addWidget(el_card)
    el_wrap_lay.addWidget(el_doc)
    il.addWidget(el_wrap)
    add_section_spacing(il)

    win._api_social_advanced = QWidget()
    social_lay = QVBoxLayout(win._api_social_advanced)
    social_lay.setContentsMargins(0, 0, 0, 0)
    social_lay.setSpacing(0)

    # ---- TikTok (optional upload) ----
    tt_card, tt_lay = section_card()
    tt_lay.addWidget(section_title("TikTok (Content Posting API)", emphasis=True))

    win.api_tt_enabled_chk = ThemedSwitch("TikTok upload")
    win.api_tt_enabled_chk.setChecked(bool(getattr(win.settings, "tiktok_enabled", False)))
    tt_lay.addWidget(win.api_tt_enabled_chk)

    tt_doc = QLabel("Finish posts in the TikTok app.")
    tt_doc.setStyleSheet("color: #9BB0C4; font-size: 11px;")
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

    win.api_tt_oauth_port = NoWheelSpinBox()
    win.api_tt_oauth_port.setRange(8000, 65535)
    win.api_tt_oauth_port.setValue(int(getattr(win.settings, "tiktok_oauth_port", 8765)))
    form_tt.addRow("OAuth port", win.api_tt_oauth_port)

    win.api_tt_pub_mode = NoWheelComboBox()
    win.api_tt_pub_mode.addItem("Inbox - finish in TikTok app (usual)", "inbox")
    win.api_tt_pub_mode.addItem("Direct post - needs TikTok app review", "direct")
    pm = str(getattr(win.settings, "tiktok_publishing_mode", "inbox") or "inbox")
    idxp = win.api_tt_pub_mode.findData(pm)
    win.api_tt_pub_mode.setCurrentIndex(idxp if idxp >= 0 else 0)
    form_tt.addRow("Publishing", win.api_tt_pub_mode)

    win.api_tt_auto_upload_chk = ThemedSwitch("Auto-upload TikTok")
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
        win.api_tt_status_lbl.setText("Status: tokens on file - connect again to refresh.")
    else:
        win.api_tt_status_lbl.setText("Status: not connected")
    tt_lay.addWidget(win.api_tt_status_lbl)

    social_lay.addWidget(tt_card)
    add_section_spacing(social_lay)

    # ---- YouTube (optional Shorts / uploads) ----
    yt_card, yt_lay = section_card()
    yt_lay.addWidget(section_title("YouTube (Data API v3)", emphasis=True))

    win.api_yt_enabled_chk = ThemedSwitch("YouTube upload")
    win.api_yt_enabled_chk.setChecked(bool(getattr(win.settings, "youtube_enabled", False)))
    yt_lay.addWidget(win.api_yt_enabled_chk)

    yt_doc = QLabel("OAuth desktop app in Google Cloud.")
    yt_doc.setStyleSheet("color: #9BB0C4; font-size: 11px;")
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

    win.api_yt_oauth_port = NoWheelSpinBox()
    win.api_yt_oauth_port.setRange(8000, 65535)
    win.api_yt_oauth_port.setValue(int(getattr(win.settings, "youtube_oauth_port", 8888)))
    form_yt.addRow("OAuth port", win.api_yt_oauth_port)

    win.api_yt_privacy = NoWheelComboBox()
    win.api_yt_privacy.addItem("Private (recommended for testing)", "private")
    win.api_yt_privacy.addItem("Unlisted", "unlisted")
    win.api_yt_privacy.addItem("Public", "public")
    pv = str(getattr(win.settings, "youtube_privacy_status", "private") or "private")
    iy = win.api_yt_privacy.findData(pv)
    win.api_yt_privacy.setCurrentIndex(iy if iy >= 0 else 0)
    form_yt.addRow("Default privacy", win.api_yt_privacy)

    win.api_yt_shorts_tag_chk = ThemedSwitch("Add #Shorts tag")
    win.api_yt_shorts_tag_chk.setChecked(bool(getattr(win.settings, "youtube_add_shorts_hashtag", True)))
    yt_lay.addWidget(win.api_yt_shorts_tag_chk)

    win.api_yt_auto_upload_chk = ThemedSwitch("Auto-upload YouTube")
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
        win.api_yt_status_lbl.setText("Status: tokens on file - connect again to refresh.")
    else:
        win.api_yt_status_lbl.setText("Status: not connected")
    yt_lay.addWidget(win.api_yt_status_lbl)

    social_lay.addWidget(yt_card)
    il.addWidget(win._api_social_advanced)

    il.addStretch(1)

    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    root.addWidget(scroll, 1)

    register_advanced_sections(
        win,
        "api",
        [
            win._api_advanced_hf_hint,
            fc_doc,
            el_doc,
            win._api_social_advanced,
        ],
    )

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

    def _sync_tasks_upload_visibility() -> None:
        if hasattr(win, "_sync_tasks_upload_buttons"):
            win._sync_tasks_upload_buttons()

    win.api_tt_enabled_chk.toggled.connect(lambda _v: _sync_tasks_upload_visibility())
    win.api_tt_client_key.textChanged.connect(_sync_tasks_upload_visibility)
    win.api_tt_client_secret.textChanged.connect(_sync_tasks_upload_visibility)
    win.api_tt_pub_mode.currentIndexChanged.connect(lambda _i: _sync_tasks_upload_visibility())
    win.api_yt_enabled_chk.toggled.connect(lambda _v: _sync_tasks_upload_visibility())
    win.api_yt_client_id.textChanged.connect(_sync_tasks_upload_visibility)
    win.api_yt_client_secret.textChanged.connect(_sync_tasks_upload_visibility)
    _sync_tasks_upload_visibility()

    win.tabs.addTab(w, "API")
