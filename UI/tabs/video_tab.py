from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
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

from UI.no_wheel_controls import NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox
from UI.tab_sections import add_section_spacing, section_title
from UI.tutorial_links import help_tooltip_rich
from src.settings.video_platform_presets import (
    PLATFORM_PRESETS,
    distinct_resolutions,
    find_best_preset_for_video,
    preset_by_id,
)


def _prep_combo(combo: QComboBox, *, min_w: int = 260, max_w: int = 520, pop_min: int = 400) -> None:
    combo.setSizePolicy(QSizePolicy.Policy.Preferred, combo.sizePolicy().verticalPolicy())
    combo.setMinimumWidth(min_w)
    combo.setMaximumWidth(max_w)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
    combo.view().setMinimumWidth(pop_min)


def attach_video_tab(win) -> None:
    # Scroll: window height is capped (~980px) but this tab is taller — without a scroll area
    # QFormLayout rows get vertically compressed and overlap.
    content = QWidget()
    lay = QVBoxLayout(content)
    lay.setSpacing(12)
    lay.setContentsMargins(14, 12, 14, 14)

    header = QLabel("Video settings")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)
    lay.addSpacing(4)

    lay.addWidget(section_title("Platform template"))

    # Game-style preset tiles (exclusive selection, like graphics quality menus)
    _TILE_QSS = """
        QPushButton#videoPresetTile {
            background-color: #1A1A22;
            border: 2px solid #2E2E38;
            border-radius: 8px;
            padding: 6px 8px;
            min-height: 44px;
            max-height: 64px;
            text-align: left;
            font-size: 10px;
            color: #E8E8EE;
        }
        QPushButton#videoPresetTile:hover {
            border-color: #4A90D9;
            background-color: #22222C;
        }
        QPushButton#videoPresetTile:checked {
            border-color: #25F4EE;
            background-color: #252532;
        }
        QPushButton#videoPresetTile:pressed {
            background-color: #2A2A36;
        }
    """

    tile_wrap = QWidget()
    tile_grid = QGridLayout(tile_wrap)
    tile_grid.setHorizontalSpacing(8)
    tile_grid.setVerticalSpacing(8)
    tile_grid.setContentsMargins(0, 0, 0, 0)

    win._platform_preset_tile_group = QButtonGroup(win)
    win._platform_preset_tile_group.setExclusive(True)
    win._platform_preset_tile_buttons: dict[str, QPushButton] = {}

    # Four columns so tiles stay narrow inside the fixed ~1000px window (long platform names were clipping).
    cols = 4
    r, c = 0, 0
    for p in PLATFORM_PRESETS:
        btn = QPushButton()
        btn.setObjectName("videoPresetTile")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_TILE_QSS)
        # Compact lines: wide platform strings force huge min-width; full list stays in the tooltip.
        btn.setText(f"{p.title}\n{p.width}×{p.height} · {p.fps}fps")
        btn.setToolTip(f"{p.title}\n\n{p.platforms}")
        btn.setProperty("preset_id", p.id)
        btn.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        win._platform_preset_tile_group.addButton(btn)
        win._platform_preset_tile_buttons[p.id] = btn
        tile_grid.addWidget(btn, r, c)
        c += 1
        if c >= cols:
            c = 0
            r += 1

    custom_tile = QPushButton()
    custom_tile.setObjectName("videoPresetTile")
    custom_tile.setCheckable(True)
    custom_tile.setCursor(Qt.CursorShape.PointingHandCursor)
    custom_tile.setStyleSheet(_TILE_QSS)
    custom_tile.setText("Custom\nManual settings")
    custom_tile.setToolTip("Keep your own mix of settings. Pick a template first, then tweak fields below.")
    custom_tile.setProperty("preset_id", "")
    custom_tile.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
    win._platform_preset_tile_group.addButton(custom_tile)
    win._platform_preset_custom_tile = custom_tile
    tile_grid.addWidget(custom_tile, r, c)
    for col in range(cols):
        tile_grid.setColumnStretch(col, 1)

    lay.addWidget(tile_wrap)

    preset_hint = QLabel(
        "Click a card to apply a platform profile (like graphics presets). "
        "Editing any value below switches selection to Custom."
    )
    preset_hint.setWordWrap(True)
    preset_hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(preset_hint)

    add_section_spacing(lay, px=14)
    lay.addWidget(section_title("Output & timing", emphasis=True))

    # --- Form 1: core video output
    form_video = QFormLayout()
    form_video.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form_video.setVerticalSpacing(14)
    form_video.setHorizontalSpacing(18)
    form_video.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    win.format_combo = NoWheelComboBox()
    win.format_combo.setMinimumContentsLength(24)
    for label, w0, h0 in distinct_resolutions():
        win.format_combo.addItem(label, (w0, h0))
    cur = (int(win.settings.video.width), int(win.settings.video.height))
    idx = win.format_combo.findData(cur)
    if idx >= 0:
        win.format_combo.setCurrentIndex(idx)
    else:
        win.format_combo.insertItem(0, f"Custom — {cur[0]}×{cur[1]}", cur)
        win.format_combo.setCurrentIndex(0)
    _prep_combo(win.format_combo)
    form_video.addRow("Resolution", win.format_combo)

    win.images_spin = NoWheelSpinBox()
    win.images_spin.setRange(3, 10)
    win.images_spin.setValue(int(win.settings.video.images_per_video))
    form_video.addRow("Images per video", win.images_spin)

    win.use_slideshow_chk = QCheckBox("Generate images and stitch (slideshow mode)")
    win.use_slideshow_chk.setChecked(bool(win.settings.video.use_image_slideshow))
    form_video.addRow("", win.use_slideshow_chk)

    win.pro_mode_chk = QCheckBox("Pro mode (multi-scene video from script)")
    win.pro_mode_chk.setChecked(bool(getattr(win.settings.video, "pro_mode", False)))
    win.pro_mode_chk.setToolTip(
        help_tooltip_rich(
            "Splits the script into scene prompts. Text-to-video models (e.g. ZeroScope) animate prompts directly. "
            "Image-to-video models (e.g. Stable Video Diffusion) first render each scene as a still with the Image model, "
            "then animate those keyframes. Slideshow must be off.",
            "video",
            slide=1,
        )
    )
    form_video.addRow("", win.pro_mode_chk)

    win.pro_clip_seconds_spin = NoWheelDoubleSpinBox()
    win.pro_clip_seconds_spin.setRange(0.5, 120.0)
    win.pro_clip_seconds_spin.setSingleStep(0.5)
    win.pro_clip_seconds_spin.setDecimals(1)
    win.pro_clip_seconds_spin.setValue(float(getattr(win.settings.video, "pro_clip_seconds", 4.0)))
    win.pro_clip_seconds_spin.setToolTip(
        "Target duration per generated scene (seconds). Long beats may split into extra scenes. "
        "See preflight for model caps."
    )
    form_video.addRow("Pro scene length (seconds)", win.pro_clip_seconds_spin)

    win.clips_spin = NoWheelSpinBox()
    win.clips_spin.setRange(1, 10)
    win.clips_spin.setValue(int(getattr(win.settings.video, "clips_per_video", 3)))
    form_video.addRow("Scenes per video (motion mode, slideshow off)", win.clips_spin)

    win.clip_seconds_spin = NoWheelSpinBox()
    win.clip_seconds_spin.setRange(2, 12)
    win.clip_seconds_spin.setValue(int(round(float(getattr(win.settings.video, "clip_seconds", 4.0)))))
    form_video.addRow("Seconds per scene (motion mode, slideshow off)", win.clip_seconds_spin)

    win.fps_spin = NoWheelSpinBox()
    win.fps_spin.setRange(15, 60)
    win.fps_spin.setValue(int(win.settings.video.fps))
    form_video.addRow("FPS", win.fps_spin)

    win.min_clip_spin = NoWheelSpinBox()
    win.min_clip_spin.setRange(2, 12)
    win.min_clip_spin.setValue(int(round(win.settings.video.microclip_min_s)))
    form_video.addRow("Micro-scene min seconds", win.min_clip_spin)

    win.max_clip_spin = NoWheelSpinBox()
    win.max_clip_spin.setRange(3, 15)
    win.max_clip_spin.setValue(int(round(win.settings.video.microclip_max_s)))
    form_video.addRow("Micro-scene max seconds", win.max_clip_spin)

    win.bitrate_combo = NoWheelComboBox()
    win.bitrate_combo.addItems(["low", "med", "high"])
    win.bitrate_combo.setCurrentText(win.settings.video.bitrate_preset)
    _prep_combo(win.bitrate_combo, min_w=200)
    win.bitrate_combo.setToolTip(win.bitrate_combo.currentText())
    win.bitrate_combo.currentIndexChanged.connect(lambda: win.bitrate_combo.setToolTip(win.bitrate_combo.currentText()))
    form_video.addRow("Bitrate preset", win.bitrate_combo)

    win.export_microclips_chk = QCheckBox("Export intermediate micro-scenes into assets/")
    win.export_microclips_chk.setChecked(bool(win.settings.video.export_microclips))
    form_video.addRow("", win.export_microclips_chk)

    win.cleanup_images_chk = QCheckBox("Delete generated images after run (save storage)")
    win.cleanup_images_chk.setChecked(bool(getattr(win.settings.video, "cleanup_images_after_run", False)))
    form_video.addRow("", win.cleanup_images_chk)

    win.allow_nsfw_chk = QCheckBox("Allow NSFW image output (disables diffusion safety checker)")
    win.allow_nsfw_chk.setChecked(bool(getattr(win.settings, "allow_nsfw", False)))
    win.allow_nsfw_chk.setToolTip(
        "When enabled, Stable Diffusion will not blank frames flagged by the built-in classifier. "
        "Use only where appropriate; you are responsible for compliance with platform rules."
    )
    form_video.addRow("", win.allow_nsfw_chk)

    lay.addLayout(form_video)

    add_section_spacing(lay)
    lay.addWidget(section_title("Quality / performance", emphasis=True))
    lay.addSpacing(2)

    win.prefer_gpu_chk = QCheckBox("Prefer GPU (when available)")
    win.prefer_gpu_chk.setChecked(bool(win.settings.prefer_gpu))
    lay.addWidget(win.prefer_gpu_chk)

    win.hq_topics_chk = QCheckBox("High quality topic selection (score + diversify)")
    win.hq_topics_chk.setChecked(bool(getattr(win.settings.video, "high_quality_topic_selection", True)))
    lay.addWidget(win.hq_topics_chk)

    win.fetch_article_chk = QCheckBox("Fetch article text for accuracy (slower)")
    win.fetch_article_chk.setChecked(bool(getattr(win.settings.video, "fetch_article_text", True)))
    lay.addWidget(win.fetch_article_chk)

    win.prompt_cond_chk = QCheckBox("Stronger prompt conditioning (scene types + negatives)")
    win.prompt_cond_chk.setChecked(bool(getattr(win.settings.video, "prompt_conditioning", True)))
    lay.addWidget(win.prompt_cond_chk)

    add_section_spacing(lay, px=12)
    lay.addWidget(section_title("Story pipeline (LLM)"))

    win.story_multistage_chk = QCheckBox("Multi-stage script review (format-specific LLM passes)")
    win.story_multistage_chk.setChecked(bool(getattr(win.settings.video, "story_multistage_enabled", False)))
    win.story_multistage_chk.setToolTip(
        "Runs extra local LLM passes after the first draft: beat structure, safety, length, and clarity "
        "(news/explainer) or dialogue, pacing, and punchlines (cartoon/unhinged). Slower but higher quality."
    )
    lay.addWidget(win.story_multistage_chk)

    win.story_web_chk = QCheckBox("Gather web context for the script (Firecrawl search + scrape)")
    win.story_web_chk.setChecked(bool(getattr(win.settings.video, "story_web_context", False)))
    win.story_web_chk.setToolTip(
        help_tooltip_rich(
            "Requires Firecrawl enabled with a valid API key on the API tab. Builds a short digest saved under "
            "the run folder and feeds it into script generation and refinement. "
            "For Cartoon and Unhinged formats, searches bias toward memes / viral / templates and run extra queries.",
            "video",
            slide=2,
        )
    )
    lay.addWidget(win.story_web_chk)

    win.story_refimg_chk = QCheckBox("Download reference images for diffusion (from scraped pages)")
    win.story_refimg_chk.setChecked(bool(getattr(win.settings.video, "story_reference_images", False)))
    win.story_refimg_chk.setToolTip(
        "Saves images from scraped pages (up to a few more for Cartoon / Unhinged when meme searches run) "
        "under the run folder; the first is used as an img2img init for the first generated frame when your "
        "image model supports image-to-image. Needs Firecrawl for discovery; SDXL-style models work best."
    )
    lay.addWidget(win.story_refimg_chk)

    info = QLabel("Tip: On 8GB VRAM, the app loads/unloads models per stage to reduce OOM risk. Motion, transitions, and audio mix live on the Effects tab.")
    info.setStyleSheet("color: #B7B7C2; margin-top: 6px;")
    lay.addWidget(info)

    add_section_spacing(lay)
    lay.addWidget(section_title("Advanced", emphasis=True))

    row = QHBoxLayout()
    row.setSpacing(10)
    win.music_path = QLineEdit()
    win.music_path.setPlaceholderText("Optional background music file path…")
    win.music_path.setText(win.settings.background_music_path or "")
    row.addWidget(win.music_path, 1)

    pick = QPushButton("Browse…")
    pick.clicked.connect(win._pick_music)
    row.addWidget(pick)
    lay.addLayout(row)

    cache_row = QHBoxLayout()
    cache_row.setSpacing(10)
    clear_seen = QPushButton("Clear seen URLs cache")
    clear_seen.setObjectName("danger")
    clear_seen.clicked.connect(win._clear_seen_cache)
    cache_row.addWidget(clear_seen)
    cache_row.addStretch(1)
    lay.addLayout(cache_row)

    hint = lay.sizeHint()
    content.setMinimumHeight(max(hint.height(), 400))
    content.setMinimumWidth(max(hint.width(), 520))

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setMinimumHeight(520)
    scroll.setWidget(content)

    shell = QWidget()
    shell_lay = QVBoxLayout(shell)
    shell_lay.setContentsMargins(0, 0, 0, 0)
    shell_lay.setSpacing(0)
    shell_lay.addWidget(scroll)

    win.tabs.addTab(shell, "Video")

    # --- Platform template: apply + mark Custom when user edits underlying fields
    win._applying_video_template = False

    def _ensure_resolution_row(w: int, h: int) -> None:
        data = (int(w), int(h))
        fi = win.format_combo.findData(data)
        if fi >= 0:
            win.format_combo.setCurrentIndex(fi)
            return
        win.format_combo.insertItem(0, f"Custom — {data[0]}×{data[1]}", data)
        win.format_combo.setCurrentIndex(0)

    def _apply_platform_preset(preset_id: str) -> None:
        pr = preset_by_id(preset_id)
        if not pr:
            return
        win._applying_video_template = True
        try:
            _ensure_resolution_row(pr.width, pr.height)
            win.fps_spin.setValue(int(pr.fps))
            win.min_clip_spin.setValue(int(round(pr.microclip_min_s)))
            win.max_clip_spin.setValue(int(round(pr.microclip_max_s)))
            win.images_spin.setValue(int(pr.images_per_video))
            win.bitrate_combo.setCurrentText(pr.bitrate_preset)
            win.clips_spin.setValue(int(pr.clips_per_video))
            win.clip_seconds_spin.setValue(int(round(pr.clip_seconds)))
            win.pro_mode_chk.setChecked(bool(getattr(pr, "pro_mode", False)))
            win.pro_clip_seconds_spin.setValue(float(getattr(pr, "pro_clip_seconds", 4.0)))
            if getattr(pr, "pro_mode", False):
                win.use_slideshow_chk.setChecked(False)
            _sync_pro_mode_ui()
        finally:
            win._applying_video_template = False

    def _mark_video_template_custom() -> None:
        if getattr(win, "_applying_video_template", False):
            return
        if not hasattr(win, "_platform_preset_custom_tile"):
            return
        win._applying_video_template = True
        try:
            win._platform_preset_custom_tile.setChecked(True)
            win._video_platform_preset_id = ""
        finally:
            win._applying_video_template = False

    def _on_preset_tile_clicked(btn: QPushButton) -> None:
        if getattr(win, "_applying_video_template", False):
            return
        raw = btn.property("preset_id")
        pid = "" if raw is None else str(raw)
        win._video_platform_preset_id = pid
        if pid:
            _apply_platform_preset(pid)

    win._apply_platform_preset = _apply_platform_preset
    win._mark_video_template_custom = _mark_video_template_custom
    win._video_platform_preset_id = ""

    def _sync_pro_mode_ui() -> None:
        pro = bool(win.pro_mode_chk.isChecked())
        lbl = form_video.labelForField(win.images_spin)
        if lbl is not None:
            lbl.setVisible(not pro)
        win.images_spin.setVisible(not pro)
        win.pro_clip_seconds_spin.setEnabled(pro)
        if pro:
            win.use_slideshow_chk.setChecked(False)
            win.use_slideshow_chk.setEnabled(False)
        else:
            win.use_slideshow_chk.setEnabled(True)

    def _on_pro_mode_toggled(*_a) -> None:
        _sync_pro_mode_ui()
        _mark_video_template_custom()

    win._platform_preset_tile_group.buttonClicked.connect(_on_preset_tile_clicked)

    win.format_combo.currentIndexChanged.connect(lambda *_: _mark_video_template_custom())
    win.bitrate_combo.currentIndexChanged.connect(lambda *_: _mark_video_template_custom())
    for _spin in (
        win.fps_spin,
        win.images_spin,
        win.min_clip_spin,
        win.max_clip_spin,
        win.clips_spin,
        win.clip_seconds_spin,
    ):
        _spin.valueChanged.connect(lambda *_: _mark_video_template_custom())
    win.pro_mode_chk.toggled.connect(_on_pro_mode_toggled)
    win.pro_clip_seconds_spin.valueChanged.connect(lambda *_: _mark_video_template_custom())

    # Restore template selection from settings (prefer saved id, else infer from numbers)
    v = win.settings.video
    saved_id = str(getattr(v, "platform_preset_id", "") or "").strip()
    win._applying_video_template = True
    try:
        if saved_id and preset_by_id(saved_id) and saved_id in win._platform_preset_tile_buttons:
            win._platform_preset_tile_buttons[saved_id].setChecked(True)
            win._video_platform_preset_id = saved_id
        else:
            inferred = find_best_preset_for_video(
                width=int(v.width),
                height=int(v.height),
                fps=int(v.fps),
                microclip_min_s=float(v.microclip_min_s),
                microclip_max_s=float(v.microclip_max_s),
                images_per_video=int(v.images_per_video),
                bitrate_preset=str(v.bitrate_preset),
                clips_per_video=int(getattr(v, "clips_per_video", 3)),
                clip_seconds=float(getattr(v, "clip_seconds", 4.0)),
                pro_mode=bool(getattr(v, "pro_mode", False)),
                pro_clip_seconds=float(getattr(v, "pro_clip_seconds", 4.0)),
            )
            if inferred and inferred in win._platform_preset_tile_buttons:
                win._platform_preset_tile_buttons[inferred].setChecked(True)
                win._video_platform_preset_id = inferred
            else:
                win._platform_preset_custom_tile.setChecked(True)
                win._video_platform_preset_id = ""
    finally:
        win._applying_video_template = False
        _sync_pro_mode_ui()
