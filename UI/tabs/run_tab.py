from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
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
    root = QVBoxLayout(w)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(0, 0, 0, 0)
    scroll.setWidget(inner)

    header = QLabel("Run Aquaduct (one-shot)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    out_card, out_lay = section_card()
    out_lay.addWidget(section_title("Output", emphasis=True))
    _ser0_qty = getattr(win.settings, "series", None)
    _init_batch = 1
    if _ser0_qty and bool(getattr(_ser0_qty, "series_mode", False)):
        _init_batch = max(1, min(50, int(getattr(_ser0_qty, "episode_count", 1) or 1)))
    qty_wrap = QWidget()
    qty_row = QHBoxLayout(qty_wrap)
    qty_row.setContentsMargins(0, 0, 0, 0)
    qty_lbl = QLabel("Videos to generate")
    qty_lbl.setStyleSheet("color: #B7B7C2;")
    win._run_qty_label = qty_lbl
    qty_row.addWidget(qty_lbl)
    win.run_qty_spin = NoWheelSpinBox()
    win.run_qty_spin.setRange(1, 50)
    win.run_qty_spin.setValue(_init_batch)
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
    out_lay.addWidget(qty_wrap)
    win._run_qty_row_wrap = qty_wrap

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
    win.video_format_combo.setToolTip(
        help_tooltip_rich(
            "Video format selects which topic list and crawler behavior apply, together with the Topics tab.",
            "run",
            slide=2,
        )
    )
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
    win.picture_format_run_combo.setToolTip(
        help_tooltip_rich(
            "Picture format (poster / newspaper / comic) for photo-mode runs; pair with the Picture tab for size and output type.",
            "run",
            slide=2,
        )
    )
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

    ser0 = getattr(win.settings, "series", None)
    series_grp = QGroupBox("Video series (continuation)")
    series_grp.setToolTip(
        help_tooltip_rich(
            "Queue N episodes that share style and continue the same story. Each episode is a separate pipeline job "
            "run one after another. Episode 2+ sees a recap of prior episodes (series bible). "
            "Output folders: videos/&lt;series&gt;/episode_NNN_&lt;title&gt;/.",
            "run",
            slide=0,
        )
    )
    win._series_output_group = series_grp
    series_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    sv = QVBoxLayout(series_grp)
    sv.setSpacing(10)
    win.series_mode_check = QCheckBox("Generate as multi-episode series")
    win.series_mode_check.setChecked(bool(getattr(ser0, "series_mode", False)) if ser0 else False)
    win.series_mode_check.setToolTip(
        help_tooltip_rich(
            "When enabled, set **Episodes to generate** below. Each episode is a full pipeline job run one after another; "
            "later episodes use the rolling recap (series bible). The Output **Videos to generate** row hides while "
            "series mode is on so the count lives in one place.",
            "run",
            slide=0,
        )
    )
    sv.addWidget(win.series_mode_check)
    ep_wrap = QWidget()
    ep_row = QHBoxLayout(ep_wrap)
    ep_row.setContentsMargins(0, 0, 0, 0)
    ep_lbl = QLabel("Episodes to generate")
    ep_lbl.setStyleSheet("color: #B7B7C2;")
    ep_row.addWidget(ep_lbl)
    win.series_episode_spin = NoWheelSpinBox()
    win.series_episode_spin.setRange(1, 50)
    win.series_episode_spin.setValue(win.run_qty_spin.value())
    win.series_episode_spin.setToolTip(
        help_tooltip_rich(
            "How many episodes to queue for this series. Episode 2+ builds on the recap / series bible. "
            "Same range as multi-video runs (1–50).",
            "run",
            slide=0,
        )
    )
    ep_row.addWidget(win.series_episode_spin)
    ep_row.addStretch(1)
    sv.addWidget(ep_wrap)
    win._series_episode_row_wrap = ep_wrap
    win._series_episode_label = ep_lbl

    def _mirror_series_ep_to_run_qty(v: int) -> None:
        win.run_qty_spin.blockSignals(True)
        win.run_qty_spin.setValue(int(v))
        win.run_qty_spin.blockSignals(False)

    win.series_episode_spin.valueChanged.connect(_mirror_series_ep_to_run_qty)

    def _on_series_mode_toggled(checked: bool) -> None:
        mm0 = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
        if mm0 == "photo":
            return
        if checked:
            win.series_episode_spin.blockSignals(True)
            win.series_episode_spin.setValue(win.run_qty_spin.value())
            win.series_episode_spin.blockSignals(False)
            _mirror_series_ep_to_run_qty(win.series_episode_spin.value())
        else:
            win.run_qty_spin.blockSignals(True)
            win.run_qty_spin.setValue(win.series_episode_spin.value())
            win.run_qty_spin.blockSignals(False)

    win.series_mode_check.toggled.connect(_on_series_mode_toggled)
    sn_lbl = QLabel("Series name")
    sn_lbl.setStyleSheet("color: #B7B7C2;")
    sn_lbl.setWordWrap(True)
    sv.addWidget(sn_lbl)
    win.series_name_edit = QLineEdit()
    win.series_name_edit.setPlaceholderText("Optional — used for the folder name under videos/")
    win.series_name_edit.setText(str(getattr(ser0, "series_name", "") or "") if ser0 else "")
    win.series_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    sv.addWidget(win.series_name_edit)
    st_lbl = QLabel("Source per episode")
    st_lbl.setStyleSheet("color: #B7B7C2;")
    st_lbl.setWordWrap(True)
    sv.addWidget(st_lbl)
    win.series_source_strategy_combo = NoWheelComboBox()
    win.series_source_strategy_combo.addItem("Auto (by format)", "auto")
    win.series_source_strategy_combo.addItem("Lock episode 1 sources", "lock_first")
    win.series_source_strategy_combo.addItem("Fresh source each episode", "fresh_per_ep")
    _ss = str(getattr(ser0, "source_strategy", "auto") or "auto") if ser0 else "auto"
    _six = win.series_source_strategy_combo.findData(_ss)
    win.series_source_strategy_combo.setCurrentIndex(_six if _six >= 0 else 0)
    win.series_source_strategy_combo.setToolTip(
        help_tooltip_rich(
            "**Auto**: news / health → new headline each episode; other formats (and custom brief) → same sources as episode 1. "
            "**Lock** / **Fresh** override Auto.",
            "run",
            slide=0,
        )
    )
    win.series_source_strategy_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    sv.addWidget(win.series_source_strategy_combo)
    win.series_lock_style_check = QCheckBox("Lock art style, models & characters\nacross episodes")
    win.series_lock_style_check.setToolTip(
        help_tooltip_rich(
            "Keep the same art style preset, diffusion/checkpoint choices, and character selection for every episode in this run.",
            "run",
            slide=0,
        )
    )
    win.series_lock_style_check.setChecked(bool(getattr(ser0, "lock_style", True)) if ser0 else True)
    sv.addWidget(win.series_lock_style_check)
    win.series_carry_recap_check = QCheckBox("Carry recap / series bible into\nthe next script")
    win.series_carry_recap_check.setChecked(bool(getattr(ser0, "carry_recap", True)) if ser0 else True)
    sv.addWidget(win.series_carry_recap_check)
    win.series_continue_on_failure_check = QCheckBox("Continue series if an episode fails")
    win.series_continue_on_failure_check.setChecked(bool(getattr(ser0, "continue_on_failure", False)) if ser0 else False)
    win.series_continue_on_failure_check.setToolTip(
        help_tooltip_rich(
            "When off (default), a failed episode aborts remaining episodes in the same series queue batch.",
            "run",
            slide=0,
        )
    )
    sv.addWidget(win.series_continue_on_failure_check)
    out_lay.addWidget(series_grp)

    def _series_controls_enabled(on: bool) -> None:
        ep_lbl.setEnabled(on)
        win.series_episode_spin.setEnabled(on)
        sn_lbl.setEnabled(on)
        st_lbl.setEnabled(on)
        win.series_name_edit.setEnabled(on)
        win.series_source_strategy_combo.setEnabled(on)
        win.series_lock_style_check.setEnabled(on)
        win.series_carry_recap_check.setEnabled(on)
        win.series_continue_on_failure_check.setEnabled(on)

    def _refresh_series_controls() -> None:
        mm0 = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
        video = mm0 != "photo"
        sm = bool(win.series_mode_check.isChecked()) and video
        _series_controls_enabled(sm)
        series_grp.setVisible(video)
        if hasattr(win, "_run_qty_row_wrap"):
            win._run_qty_row_wrap.setVisible(not sm if video else True)
        if hasattr(win, "_series_episode_row_wrap"):
            win._series_episode_row_wrap.setVisible(sm)

    win.series_mode_check.stateChanged.connect(lambda *_: (_refresh_series_controls(), refresh_run_tab_for_media_mode(win)))
    _refresh_series_controls()
    win._run_tab_refresh_series_controls = _refresh_series_controls

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
    win.run_content_preset_radio.setToolTip(
        help_tooltip_rich(
            "Preset uses your per-format topic tags plus the news/headline cache (behavior depends on video format).",
            "run",
            slide=1,
        )
    )
    win.run_content_custom_radio.setToolTip(
        help_tooltip_rich(
            "Custom uses your multiline instructions: the script model expands them into a brief, then writes "
            "the full script (two LLM passes — slower than Preset).",
            "run",
            slide=1,
        )
    )
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
    win.custom_instructions_edit.setToolTip(
        help_tooltip_rich(
            "Custom content: the script model expands your notes into a brief, then writes the full script "
            "(two LLM passes). Does not pick headlines from the news cache.",
            "run",
            slide=1,
        )
    )
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
                extra = " Short horror from the web; keep it fiction only."
            vf_hint.setText(
                "Custom mode does not pick headlines from the news cache. The LLM expands your notes into a brief, "
                "then writes the script (two passes — slower than Preset). Topic tags from the Topics tab still bias "
                "hashtags when relevant."
                + extra
            )
        elif vf == "unhinged":
            vf_hint.setText(
                "Comedy headlines from the web using your Topics tags. Satire tone. "
                "Local voices rotate by beat; ElevenLabs uses one voice for the whole track if set."
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
    win.character_combo.setToolTip(
        help_tooltip_rich(
            "Optional character ties voice and visuals to a profile from the Characters tab.",
            "run",
            slide=2,
        )
    )
    c_row.addWidget(win.character_combo, 1)
    c_row.addStretch(1)
    sc_lay.addLayout(c_row)

    win.auto_save_generated_cast_check = QCheckBox("Save generated cast to Characters tab")
    win.auto_save_generated_cast_check.setChecked(
        bool(getattr(win.settings, "auto_save_generated_cast", True))
    )
    win.auto_save_generated_cast_check.setToolTip(
        help_tooltip_rich(
            "When (None) is selected above, the LLM invents a cast for each run. With this on (default), "
            "those characters are upserted into the Characters tab so you can re-use or edit them later. "
            "Names are deduplicated per video format.",
            "run",
            slide=2,
        )
    )
    sc_lay.addWidget(win.auto_save_generated_cast_check)
    lay.addWidget(sc_card)

    lay.addStretch(1)

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
    win.preview_btn.setToolTip(
        help_tooltip_rich(
            "Preview drafts a script package without a full render. Progress appears on the Tasks tab.",
            "run",
            slide=3,
        )
    )
    win.preview_btn.clicked.connect(win._on_preview)
    row.addWidget(win.preview_btn)

    win.storyboard_btn = QPushButton("Storyboard Preview")
    win.storyboard_btn.setToolTip(
        help_tooltip_rich(
            "Storyboard preview builds a visual grid plan. Progress appears on the Tasks tab.",
            "run",
            slide=3,
        )
    )
    win.storyboard_btn.clicked.connect(win._on_storyboard_preview)
    row.addWidget(win.storyboard_btn)

    win.open_videos_btn = QPushButton("Open videos folder")
    win.open_videos_btn.setToolTip(
        help_tooltip_rich(
            "Opens the videos/ output root in the file manager (finished projects with final.mp4).",
            "tasks_library",
            slide=1,
        )
    )
    win.open_videos_btn.clicked.connect(win._open_videos)
    row.addWidget(win.open_videos_btn)

    win.save_btn = QPushButton("Save settings")
    win.save_btn.setToolTip(
        help_tooltip_rich(
            "Writes every tab’s settings to ui_settings.json (same as the title bar Save button).",
            "welcome",
            slide=1,
        )
    )
    win.save_btn.clicked.connect(win._save_settings)
    row.addWidget(win.save_btn)

    row.addStretch(1)
    act_lay.addLayout(row)

    root.addWidget(scroll, 1)
    add_section_spacing(root)
    root.addWidget(act_card, 0)

    win.tabs.addTab(w, "Run")


def refresh_run_tab_for_media_mode(win) -> None:
    """Keep Run tab labels and actions aligned with Video vs Photo mode."""
    from UI.help.tutorial_links import help_tooltip_rich

    mm = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
    is_photo = mm == "photo"
    if hasattr(win, "_run_qty_label"):
        if is_photo:
            win._run_qty_label.setText("Runs to generate")
        elif hasattr(win, "series_mode_check") and win.series_mode_check.isChecked():
            win._run_qty_label.setText("Episodes")
        else:
            win._run_qty_label.setText("Videos to generate")
    if hasattr(win, "run_qty_spin"):
        if is_photo:
            win.run_qty_spin.setToolTip(
                help_tooltip_rich(
                    "Each count is one photo pipeline run (each project folder under .Aquaduct_data/pictures/).",
                    "run",
                    slide=0,
                )
            )
        else:
            _ep = (
                bool(win.series_mode_check.isChecked())
                if hasattr(win, "series_mode_check")
                else bool(getattr(getattr(win.settings, "series", None), "series_mode", False))
            )
            win.run_qty_spin.setToolTip(
                help_tooltip_rich(
                    "Each count is one **episode** (full pipeline). Episodes after the first are queued and start "
                    "when the previous finishes. Continuity uses the series recap / bible.",
                    "run",
                    slide=0,
                )
                if _ep
                else help_tooltip_rich(
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
        win.open_videos_btn.setToolTip(
            help_tooltip_rich(
                "Opens the pictures/ or videos/ output root in the file manager.",
                "tasks_library",
                slide=1,
            )
            if is_photo
            else help_tooltip_rich(
                "Opens the videos/ output root in the file manager (finished projects with final.mp4).",
                "tasks_library",
                slide=1,
            )
        )
    if hasattr(win, "_sync_run_content_hints"):
        win._sync_run_content_hints()
    if hasattr(win, "_run_tab_refresh_series_controls"):
        win._run_tab_refresh_series_controls()
    if hasattr(win, "run_btn"):
        win.run_btn.setToolTip(
            help_tooltip_rich(
                "Each Run starts one photo pipeline; status appears on the Tasks tab.",
                "run",
                slide=0,
            )
            if is_photo
            else help_tooltip_rich(
                "While a job runs, live stage + percent appear as the top row on the Tasks tab.",
                "run",
                slide=0,
            )
        )
