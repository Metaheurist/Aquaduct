from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.config import MAX_CUSTOM_VIDEO_INSTRUCTIONS, VIDEO_FORMATS
from src.content.characters_store import load_all
from src.content.personalities import get_personality_presets
from src.settings.art_style_presets import ART_STYLE_PRESETS
def attach_run_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Run Aquaduct (one-shot)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    qty_row = QHBoxLayout()
    qty_lbl = QLabel("Videos to generate")
    qty_lbl.setStyleSheet("color: #B7B7C2;")
    qty_row.addWidget(qty_lbl)
    win.run_qty_spin = QSpinBox()
    win.run_qty_spin.setRange(1, 50)
    win.run_qty_spin.setValue(1)
    qty_row.addWidget(win.run_qty_spin)
    qty_row.addStretch(1)
    lay.addLayout(qty_row)

    fmt_row = QHBoxLayout()
    fmt_lbl = QLabel("Video format")
    fmt_lbl.setStyleSheet("color: #B7B7C2;")
    fmt_row.addWidget(fmt_lbl)
    win.video_format_combo = QComboBox()
    win.video_format_combo.addItem("News (headlines)", "news")
    win.video_format_combo.addItem("Cartoon", "cartoon")
    win.video_format_combo.addItem("Explainer", "explainer")
    win.video_format_combo.addItem("Cartoon (unhinged)", "unhinged")
    cur_vf = str(getattr(win.settings, "video_format", "news") or "news")
    if cur_vf not in VIDEO_FORMATS:
        cur_vf = "news"
    idx_vf = win.video_format_combo.findData(cur_vf)
    win.video_format_combo.setCurrentIndex(idx_vf if idx_vf >= 0 else 0)
    fmt_row.addWidget(win.video_format_combo, 1)
    fmt_row.addStretch(1)
    lay.addLayout(fmt_row)

    style_row = QHBoxLayout()
    style_lbl = QLabel("Art style (visual continuity)")
    style_lbl.setStyleSheet("color: #B7B7C2;")
    style_row.addWidget(style_lbl)
    win.art_style_preset_combo = QComboBox()
    win.art_style_preset_combo.setToolTip(
        "Biases diffusion toward a consistent look; after the first image, later frames use the last "
        "up to three renders as a style reference (img2img). Strong no-text negatives are always applied."
    )
    for asp in ART_STYLE_PRESETS:
        win.art_style_preset_combo.addItem(asp.label, asp.id)
    cur_as = str(getattr(win.settings, "art_style_preset_id", "balanced") or "balanced")
    ix_as = win.art_style_preset_combo.findData(cur_as)
    win.art_style_preset_combo.setCurrentIndex(ix_as if ix_as >= 0 else 0)
    style_row.addWidget(win.art_style_preset_combo, 1)
    style_row.addStretch(1)
    lay.addLayout(style_row)

    mode_row = QHBoxLayout()
    mode_lbl = QLabel("Content source")
    mode_lbl.setStyleSheet("color: #B7B7C2;")
    mode_row.addWidget(mode_lbl)
    win.run_content_preset_radio = QRadioButton("Preset")
    win.run_content_custom_radio = QRadioButton("Custom (your instructions)")
    win.run_content_mode_group = QButtonGroup(w)
    win.run_content_mode_group.addButton(win.run_content_preset_radio)
    win.run_content_mode_group.addButton(win.run_content_custom_radio)
    if str(getattr(win.settings, "run_content_mode", "preset") or "preset") == "custom":
        win.run_content_custom_radio.setChecked(True)
    else:
        win.run_content_preset_radio.setChecked(True)
    mode_row.addWidget(win.run_content_preset_radio)
    mode_row.addWidget(win.run_content_custom_radio)
    mode_row.addStretch(1)
    lay.addLayout(mode_row)

    win.custom_instructions_edit = QTextEdit()
    win.custom_instructions_edit.setAcceptRichText(False)
    win.custom_instructions_edit.setPlaceholderText(
        "Describe the video: topic, angle, tone, structure, visual vibe, CTA… "
        f"(max {MAX_CUSTOM_VIDEO_INSTRUCTIONS} characters stored.)"
    )
    win.custom_instructions_edit.setPlainText(str(getattr(win.settings, "custom_video_instructions", "") or "")[:MAX_CUSTOM_VIDEO_INSTRUCTIONS])
    win.custom_instructions_edit.setMinimumHeight(72)
    win.custom_instructions_edit.setMaximumHeight(160)
    lay.addWidget(win.custom_instructions_edit)

    vf_hint = QLabel("")
    vf_hint.setWordWrap(True)
    vf_hint.setStyleSheet("color: #8A96A3; font-size: 11px;")

    def _preset_mode_caption(vf: str) -> str:
        """Preset row explains how headlines are sourced (matches pipeline behavior)."""
        if vf == "unhinged":
            return "Preset (topics + fresh headlines)"
        if vf == "news":
            return "Preset (news cache + topics)"
        # cartoon / explainer: per-format URL cache under data/news_cache/, not the news bucket
        return "Preset (topics + headlines)"

    def _sync_content_mode_ui() -> None:
        custom = win.run_content_custom_radio.isChecked()
        win.custom_instructions_edit.setVisible(custom)
        vf = str(win.video_format_combo.currentData() or "news")
        win.run_content_preset_radio.setText(_preset_mode_caption(vf))
        if custom:
            extra = ""
            if vf == "unhinged":
                extra = (
                    " Cartoon (unhinged) targets adult-animation satire (absurdist / shock-cartoon energy); "
                    "local TTS rotates voices per beat (single cloud voice if your character uses ElevenLabs)."
                )
            vf_hint.setText(
                "Custom mode does not pick headlines from the news cache. The LLM expands your notes into a brief, "
                "then writes the script (two passes — slower than Preset). Topic tags from the Topics tab still bias "
                "hashtags when relevant."
                + extra
            )
        elif vf == "unhinged":
            vf_hint.setText(
                "Cartoon (unhinged): Preset pulls comedy/absurdist headlines using your Topics tags (no local seen-URL cache). "
                "Adult-animation satire tone. Local TTS rotates one system voice per script beat; "
                "when a character uses ElevenLabs, one voice is used for the full track."
            )
        else:
            vf_hint.setText("Tags for the run come from the Topics tab list for this format.")

    win.run_content_preset_radio.toggled.connect(lambda _c: _sync_content_mode_ui())
    win.run_content_custom_radio.toggled.connect(lambda _c: _sync_content_mode_ui())
    win.video_format_combo.currentIndexChanged.connect(lambda _i: _sync_content_mode_ui())
    _sync_content_mode_ui()
    lay.addWidget(vf_hint)

    # Personality selection
    p_row = QHBoxLayout()
    p_lbl = QLabel("Personality")
    p_lbl.setStyleSheet("color: #B7B7C2;")
    p_row.addWidget(p_lbl)

    win.personality_combo = QComboBox()
    win.personality_combo.addItem("Auto (recommended)", "auto")
    for p in get_personality_presets():
        win.personality_combo.addItem(p.label, p.id)

    # Restore selection if present
    current = getattr(win.settings, "personality_id", "auto") or "auto"
    idx = win.personality_combo.findData(current)
    if idx >= 0:
        win.personality_combo.setCurrentIndex(idx)
    p_row.addWidget(win.personality_combo, 1)
    p_row.addStretch(1)
    lay.addLayout(p_row)

    win.personality_hint = QLabel("")
    win.personality_hint.setStyleSheet("color: #B7B7C2;")
    win.personality_hint.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    lay.addWidget(win.personality_hint)

    c_row = QHBoxLayout()
    c_lbl = QLabel("Character")
    c_lbl.setStyleSheet("color: #B7B7C2;")
    c_row.addWidget(c_lbl)
    win.character_combo = QComboBox()
    win.character_combo.addItem("(None)", "")
    try:
        for ch in load_all():
            win.character_combo.addItem(ch.name, ch.id)
    except Exception:
        pass
    cur_cid = str(getattr(win.settings, "active_character_id", "") or "").strip()
    if cur_cid:
        idx_c = win.character_combo.findData(cur_cid)
        if idx_c >= 0:
            win.character_combo.setCurrentIndex(idx_c)
    c_row.addWidget(win.character_combo, 1)
    c_row.addStretch(1)
    lay.addLayout(c_row)

    run_hint = QLabel("While a job runs, live status appears as the top row on the **Tasks** tab.")
    run_hint.setWordWrap(True)
    run_hint.setStyleSheet("color: #8A96A3; font-size: 11px;")
    lay.addWidget(run_hint)

    row = QHBoxLayout()
    win.run_btn = QPushButton("Run")
    win.run_btn.setObjectName("primary")
    win.run_btn.clicked.connect(win._on_run)
    row.addWidget(win.run_btn)

    win.preview_btn = QPushButton("Preview")
    win.preview_btn.clicked.connect(win._on_preview)
    row.addWidget(win.preview_btn)

    win.storyboard_btn = QPushButton("Storyboard Preview")
    win.storyboard_btn.clicked.connect(win._on_storyboard_preview)
    row.addWidget(win.storyboard_btn)

    win.open_videos_btn = QPushButton("Open videos folder")
    win.open_videos_btn.clicked.connect(win._open_videos)
    row.addWidget(win.open_videos_btn)

    win.save_btn = QPushButton("Save settings")
    win.save_btn.clicked.connect(win._save_settings)
    row.addWidget(win.save_btn)

    row.addStretch(1)
    lay.addLayout(row)

    win.tabs.addTab(w, "Run")
