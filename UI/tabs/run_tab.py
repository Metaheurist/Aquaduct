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
from UI.widgets.no_wheel_controls import NoWheelComboBox, NoWheelSpinBox
from UI.widgets.tab_sections import add_section_spacing, section_card, section_title
from UI.help.tutorial_links import help_tooltip_rich


def attach_run_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Run Aquaduct (one-shot)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    out_card, out_lay = section_card()
    out_lay.addWidget(section_title("Output", emphasis=True))
    qty_row = QHBoxLayout()
    qty_lbl = QLabel("Videos to generate")
    qty_lbl.setStyleSheet("color: #B7B7C2;")
    win._run_qty_label = qty_lbl
    qty_row.addWidget(qty_lbl)
    win.run_qty_spin = NoWheelSpinBox()
    win.run_qty_spin.setRange(1, 50)
    win.run_qty_spin.setValue(1)
    win.run_qty_spin.setToolTip(
        help_tooltip_rich(
            "Each count is one full pipeline run (one video). "
            "Runs after the first are queued and start automatically when the previous run finishes.",
            "run",
            slide=0,
        )
    )
    qty_row.addWidget(win.run_qty_spin)
    qty_row.addStretch(1)
    out_lay.addLayout(qty_row)

    fmt_row = QHBoxLayout()
    win._video_format_label = QLabel("Video format")
    win._video_format_label.setStyleSheet("color: #B7B7C2;")
    fmt_row.addWidget(win._video_format_label)
    win.video_format_combo = NoWheelComboBox()
    win.video_format_combo.addItem("News (headlines)", "news")
    win.video_format_combo.addItem("Cartoon", "cartoon")
    win.video_format_combo.addItem("Explainer", "explainer")
    win.video_format_combo.addItem("Cartoon (unhinged)", "unhinged")
    win.video_format_combo.addItem("Creepypasta (web horror)", "creepypasta")
    win.video_format_combo.addItem("Health advice (wellness tips)", "health_advice")
    cur_vf = str(getattr(win.settings, "video_format", "news") or "news")
    if cur_vf not in VIDEO_FORMATS:
        cur_vf = "news"
    idx_vf = win.video_format_combo.findData(cur_vf)
    win.video_format_combo.setCurrentIndex(idx_vf if idx_vf >= 0 else 0)
    fmt_row.addWidget(win.video_format_combo, 1)
    fmt_row.addStretch(1)
    out_lay.addLayout(fmt_row)

    pic_row = QHBoxLayout()
    win._picture_format_label = QLabel("Picture format")
    win._picture_format_label.setStyleSheet("color: #B7B7C2;")
    pic_row.addWidget(win._picture_format_label)
    win.picture_format_run_combo = NoWheelComboBox()
    win.picture_format_run_combo.addItem("Poster", "poster")
    win.picture_format_run_combo.addItem("Newspaper", "newspaper")
    win.picture_format_run_combo.addItem("Comic", "comic")
    win.picture_format_run_combo.setCurrentIndex(0)
    pic_row.addWidget(win.picture_format_run_combo, 1)
    pic_row.addStretch(1)
    out_lay.addLayout(pic_row)

    # Initial mode visibility (title-bar toggle updates via main_window._apply_media_mode_ui).
    try:
        mm = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
        is_photo = mm == "photo"
        win._picture_format_label.setVisible(is_photo)
        win.picture_format_run_combo.setVisible(is_photo)
    except Exception:
        pass

    style_row = QHBoxLayout()
    style_lbl = QLabel("Art style (visual continuity)")
    style_lbl.setStyleSheet("color: #B7B7C2;")
    style_row.addWidget(style_lbl)
    win.art_style_preset_combo = NoWheelComboBox()
    win.art_style_preset_combo.setToolTip(
        help_tooltip_rich(
            "Biases diffusion toward a consistent look; after the first image, later frames use the last "
            "up to three renders as a style reference (img2img). Strong no-text negatives are always applied.",
            "run",
            slide=2,
        )
    )
    for asp in ART_STYLE_PRESETS:
        win.art_style_preset_combo.addItem(asp.label, asp.id)
    cur_as = str(getattr(win.settings, "art_style_preset_id", "balanced") or "balanced")
    ix_as = win.art_style_preset_combo.findData(cur_as)
    win.art_style_preset_combo.setCurrentIndex(ix_as if ix_as >= 0 else 0)
    style_row.addWidget(win.art_style_preset_combo, 1)
    style_row.addStretch(1)
    out_lay.addLayout(style_row)
    lay.addWidget(out_card)

    add_section_spacing(lay)
    sc_card, sc_lay = section_card()
    sc_lay.addWidget(section_title("Script & content", emphasis=True))
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
    sc_lay.addLayout(mode_row)

    win.custom_instructions_edit = QTextEdit()
    win.custom_instructions_edit.setAcceptRichText(False)
    win.custom_instructions_edit.setPlaceholderText(
        "Describe the video: topic, angle, tone, structure, visual vibe, CTA… "
        f"(max {MAX_CUSTOM_VIDEO_INSTRUCTIONS} characters stored.)"
    )
    win.custom_instructions_edit.setPlainText(str(getattr(win.settings, "custom_video_instructions", "") or "")[:MAX_CUSTOM_VIDEO_INSTRUCTIONS])
    win.custom_instructions_edit.setMinimumHeight(72)
    win.custom_instructions_edit.setMaximumHeight(160)
    sc_lay.addWidget(win.custom_instructions_edit)

    vf_hint = QLabel("")
    vf_hint.setWordWrap(True)
    vf_hint.setStyleSheet("color: #8A96A3; font-size: 11px;")

    def _preset_mode_caption(vf: str) -> str:
        """Preset row explains how headlines are sourced (matches pipeline behavior)."""
        if vf == "unhinged":
            return "Preset (topics + fresh headlines)"
        if vf == "creepypasta":
            return "Preset (topics + web horror fiction)"
        if vf == "news":
            return "Preset (news cache + topics)"
        # cartoon / explainer: per-format URL cache under data/news_cache/, not the news bucket
        return "Preset (topics + headlines)"

    def _sync_content_mode_ui() -> None:
        custom = win.run_content_custom_radio.isChecked()
        win.custom_instructions_edit.setVisible(custom)
        mm = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
        vf = str(win.video_format_combo.currentData() or "news")
        if mm == "photo":
            win.run_content_preset_radio.setText("Preset (topics + headlines for prompts)")
            if custom:
                vf_hint.setText(
                    "Custom mode: your instructions drive the still / layout brief (no headline crawl). "
                    "Use the Picture tab for template size, output type, and poster/newspaper/comic format. "
                    f"Topic tags from the Topics tab (for the selected source mode below) still bias prompts when relevant. "
                    f"(max {MAX_CUSTOM_VIDEO_INSTRUCTIONS} characters.)"
                )
            else:
                vf_hint.setText(
                    "**Preset** uses the **source mode** below and your **Topics** tab to pick ideas — same flow as making a video, "
                    "except this run creates still images or a layout instead of an MP4.\n\n"
                    "Choose template, how many images, output type, and picture format on the **Picture** tab."
                )
            return
        win.run_content_preset_radio.setText(_preset_mode_caption(vf))
        if custom:
            extra = ""
            if vf == "unhinged":
                extra = (
                    " Cartoon (unhinged) targets adult-animation satire (absurdist / shock-cartoon energy); "
                    "local TTS rotates voices per beat (single cloud voice if your character uses ElevenLabs)."
                )
            elif vf == "creepypasta":
                extra = (
                    " Creepypasta mode writes fictional horror from web-sourced story pages (Firecrawl). "
                    "Stay fiction-only — no true-crime framing."
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
        elif vf == "creepypasta":
            vf_hint.setText(
                "Creepypasta: Preset crawls the open web for short horror / creepypasta fiction (Firecrawl search + optional RSS fallback). "
                "Uses your Topics tags to steer queries; no local seen-URL cache. Enable Firecrawl on the API tab for best results."
            )
        else:
            vf_hint.setText("Tags for the run come from the Topics tab list for this format.")

    win.run_content_preset_radio.toggled.connect(lambda _c: _sync_content_mode_ui())
    win.run_content_custom_radio.toggled.connect(lambda _c: _sync_content_mode_ui())
    win.video_format_combo.currentIndexChanged.connect(lambda _i: _sync_content_mode_ui())
    win._sync_run_content_hints = _sync_content_mode_ui
    _sync_content_mode_ui()
    # Keep this as a short, low-density hint; put details in the tooltip.
    vf_hint.setStyleSheet("color: #8A96A3; font-size: 11px;")
    vf_hint.setText("Tip: hover the Content source controls for details.")
    vf_hint.setToolTip(
        help_tooltip_rich(
            "Preset uses Topics for the selected format. Custom expands your notes into a brief, then writes the script (two passes). "
            "In Photo mode, Preset still steers prompts and headline picks; Custom drives the still/layout brief.",
            "run",
            slide=1,
        )
    )
    win.vf_hint_label = vf_hint
    sc_lay.addWidget(vf_hint)

    # Personality selection
    p_row = QHBoxLayout()
    p_lbl = QLabel("Personality")
    p_lbl.setStyleSheet("color: #B7B7C2;")
    p_row.addWidget(p_lbl)

    win.personality_combo = NoWheelComboBox()
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
    sc_lay.addLayout(p_row)

    win.personality_hint = QLabel("")
    win.personality_hint.setStyleSheet("color: #B7B7C2;")
    win.personality_hint.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    sc_lay.addWidget(win.personality_hint)

    c_row = QHBoxLayout()
    c_lbl = QLabel("Character")
    c_lbl.setStyleSheet("color: #B7B7C2;")
    c_row.addWidget(c_lbl)
    win.character_combo = NoWheelComboBox()
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
    sc_lay.addLayout(c_row)
    lay.addWidget(sc_card)

    add_section_spacing(lay)
    act_card, act_lay = section_card()
    act_lay.addWidget(section_title("Actions", emphasis=True))

    row = QHBoxLayout()
    win.run_btn = QPushButton("Run")
    win.run_btn.setObjectName("primary")
    win.run_btn.setToolTip(
        help_tooltip_rich(
            "While a job runs, live stage + percent appear as the top row on the Tasks tab.",
            "run",
            slide=0,
        )
    )
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
    act_lay.addLayout(row)
    lay.addWidget(act_card)

    win.tabs.addTab(w, "Run")


def refresh_run_tab_for_media_mode(win) -> None:
    """Keep Run tab labels and actions aligned with Video vs Photo mode."""
    from UI.help.tutorial_links import help_tooltip_rich

    mm = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
    is_photo = mm == "photo"
    if hasattr(win, "_run_qty_label"):
        win._run_qty_label.setText("Runs to generate" if is_photo else "Videos to generate")
    if hasattr(win, "run_qty_spin"):
        if is_photo:
            win.run_qty_spin.setToolTip(
                "Each count is one photo pipeline run (each project folder under .Aquaduct_data/pictures/)."
            )
        else:
            win.run_qty_spin.setToolTip(
                help_tooltip_rich(
                    "Each count is one full pipeline run (one video). "
                    "Runs after the first are queued and start automatically when the previous run finishes.",
                    "run",
                    slide=0,
                )
            )
    if hasattr(win, "_video_format_label"):
        win._video_format_label.setText("Headline & topic mode" if is_photo else "Video format")
    if hasattr(win, "custom_instructions_edit"):
        if is_photo:
            win.custom_instructions_edit.setPlaceholderText(
                "Describe the still or layout: subject, composition, style, on-image text, mood… "
                f"(max {MAX_CUSTOM_VIDEO_INSTRUCTIONS} characters stored.)"
            )
        else:
            win.custom_instructions_edit.setPlaceholderText(
                "Describe the video: topic, angle, tone, structure, visual vibe, CTA… "
                f"(max {MAX_CUSTOM_VIDEO_INSTRUCTIONS} characters stored.)"
            )
    if hasattr(win, "preview_btn"):
        win.preview_btn.setVisible(not is_photo)
    if hasattr(win, "storyboard_btn"):
        win.storyboard_btn.setVisible(not is_photo)
    if hasattr(win, "open_videos_btn"):
        win.open_videos_btn.setText("Open outputs folder" if is_photo else "Open videos folder")
    if hasattr(win, "_sync_run_content_hints"):
        win._sync_run_content_hints()
    if hasattr(win, "run_btn"):
        win.run_btn.setToolTip(
            "Each Run starts one pipeline; status appears on the Tasks tab."
            if is_photo
            else help_tooltip_rich(
                "While a job runs, live stage + percent appear as the top row on the Tasks tab.",
                "run",
                slide=0,
            )
        )
