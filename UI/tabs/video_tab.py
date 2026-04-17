from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
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
    # Give this tab more breathing room; scroll handles overflow.
    lay.setSpacing(12)
    lay.setContentsMargins(14, 12, 14, 14)

    header = QLabel("Video settings")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)
    lay.addSpacing(6)

    # --- Form 1: core video output (must be fully built before addLayout — avoids overlapping rows on Windows)
    form_video = QFormLayout()
    form_video.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form_video.setVerticalSpacing(14)
    form_video.setHorizontalSpacing(18)
    form_video.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    presets: list[tuple[str, int, int]] = [
        ("TikTok / Reels / Shorts (9:16) — 1080×1920", 1080, 1920),
        ("TikTok / Reels / Shorts (9:16) — 720×1280", 720, 1280),
        ("Instagram Square (1:1) — 1080×1080", 1080, 1080),
        ("YouTube (16:9) — 1920×1080", 1920, 1080),
        ("YouTube (16:9) — 1280×720", 1280, 720),
        ("X/Twitter (16:9) — 1280×720", 1280, 720),
    ]

    win.format_combo = QComboBox()
    win.format_combo.setMinimumContentsLength(24)
    for label, w0, h0 in presets:
        win.format_combo.addItem(label, (w0, h0))
    cur = (int(win.settings.video.width), int(win.settings.video.height))
    idx = win.format_combo.findData(cur)
    if idx >= 0:
        win.format_combo.setCurrentIndex(idx)
    else:
        win.format_combo.insertItem(0, f"Custom — {cur[0]}×{cur[1]}", cur)
        win.format_combo.setCurrentIndex(0)
    _prep_combo(win.format_combo)
    form_video.addRow("Video format", win.format_combo)

    win.images_spin = QSpinBox()
    win.images_spin.setRange(3, 10)
    win.images_spin.setValue(int(win.settings.video.images_per_video))
    form_video.addRow("Images per video", win.images_spin)

    win.use_slideshow_chk = QCheckBox("Generate images and stitch (slideshow mode)")
    win.use_slideshow_chk.setChecked(bool(win.settings.video.use_image_slideshow))
    form_video.addRow("", win.use_slideshow_chk)

    win.clips_spin = QSpinBox()
    win.clips_spin.setRange(1, 10)
    win.clips_spin.setValue(int(getattr(win.settings.video, "clips_per_video", 3)))
    form_video.addRow("Clips per video (clip mode)", win.clips_spin)

    win.clip_seconds_spin = QSpinBox()
    win.clip_seconds_spin.setRange(2, 12)
    win.clip_seconds_spin.setValue(int(round(float(getattr(win.settings.video, "clip_seconds", 4.0)))))
    form_video.addRow("Seconds per clip (clip mode)", win.clip_seconds_spin)

    win.fps_spin = QSpinBox()
    win.fps_spin.setRange(15, 60)
    win.fps_spin.setValue(int(win.settings.video.fps))
    form_video.addRow("FPS", win.fps_spin)

    win.min_clip_spin = QSpinBox()
    win.min_clip_spin.setRange(2, 12)
    win.min_clip_spin.setValue(int(round(win.settings.video.microclip_min_s)))
    form_video.addRow("Micro-clip min seconds", win.min_clip_spin)

    win.max_clip_spin = QSpinBox()
    win.max_clip_spin.setRange(3, 15)
    win.max_clip_spin.setValue(int(round(win.settings.video.microclip_max_s)))
    form_video.addRow("Micro-clip max seconds", win.max_clip_spin)

    win.bitrate_combo = QComboBox()
    win.bitrate_combo.addItems(["low", "med", "high"])
    win.bitrate_combo.setCurrentText(win.settings.video.bitrate_preset)
    _prep_combo(win.bitrate_combo, min_w=200)
    win.bitrate_combo.setToolTip(win.bitrate_combo.currentText())
    win.bitrate_combo.currentIndexChanged.connect(lambda: win.bitrate_combo.setToolTip(win.bitrate_combo.currentText()))
    form_video.addRow("Bitrate preset", win.bitrate_combo)

    win.export_microclips_chk = QCheckBox("Export intermediate micro-clips into assets/")
    win.export_microclips_chk.setChecked(bool(win.settings.video.export_microclips))
    form_video.addRow("", win.export_microclips_chk)

    win.cleanup_images_chk = QCheckBox("Delete generated images after run (save storage)")
    win.cleanup_images_chk.setChecked(bool(getattr(win.settings.video, "cleanup_images_after_run", False)))
    form_video.addRow("", win.cleanup_images_chk)

    lay.addLayout(form_video)

    # --- Quality / performance (not in QFormLayout — vertical list of checkboxes)
    divider = QFrame()
    divider.setFrameShape(QFrame.Shape.HLine)
    divider.setStyleSheet("color: #2A2A34; margin-top: 10px; margin-bottom: 6px;")
    lay.addWidget(divider)

    qh = QLabel("Quality / performance")
    qh.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 4px;")
    lay.addWidget(qh)
    lay.addSpacing(2)

    win.prefer_gpu_chk = QCheckBox("Prefer GPU (when available)")
    win.prefer_gpu_chk.setChecked(bool(win.settings.prefer_gpu))
    lay.addWidget(win.prefer_gpu_chk)

    win.try_llm_chk = QCheckBox("Try 4-bit LLM scripting (falls back if unavailable)")
    win.try_llm_chk.setChecked(bool(win.settings.try_llm_4bit))
    lay.addWidget(win.try_llm_chk)

    win.try_sdxl_chk = QCheckBox("Try SDXL Turbo images (falls back if unavailable)")
    win.try_sdxl_chk.setChecked(bool(win.settings.try_sdxl_turbo))
    lay.addWidget(win.try_sdxl_chk)

    win.hq_topics_chk = QCheckBox("High quality topic selection (score + diversify)")
    win.hq_topics_chk.setChecked(bool(getattr(win.settings.video, "high_quality_topic_selection", True)))
    lay.addWidget(win.hq_topics_chk)

    win.fetch_article_chk = QCheckBox("Fetch article text for accuracy (slower)")
    win.fetch_article_chk.setChecked(bool(getattr(win.settings.video, "fetch_article_text", True)))
    lay.addWidget(win.fetch_article_chk)

    win.factcheck_chk = QCheckBox("LLM fact-check pass (safer phrasing + attribution)")
    win.factcheck_chk.setChecked(bool(getattr(win.settings.video, "llm_factcheck", True)))
    lay.addWidget(win.factcheck_chk)

    win.prompt_cond_chk = QCheckBox("Stronger prompt conditioning (scene types + negatives)")
    win.prompt_cond_chk.setChecked(bool(getattr(win.settings.video, "prompt_conditioning", True)))
    lay.addWidget(win.prompt_cond_chk)

    info = QLabel("Tip: On 8GB VRAM, the app loads/unloads models per stage to reduce OOM risk. Motion, transitions, and audio mix live on the Effects tab.")
    info.setStyleSheet("color: #B7B7C2; margin-top: 6px;")
    lay.addWidget(info)

    divider2 = QFrame()
    divider2.setFrameShape(QFrame.Shape.HLine)
    divider2.setStyleSheet("color: #2A2A34; margin-top: 10px; margin-bottom: 6px;")
    lay.addWidget(divider2)

    ah = QLabel("Advanced")
    ah.setStyleSheet("font-size: 14px; font-weight: 700;")
    lay.addWidget(ah)

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
    # Keep a sane viewport so _resize_to_current_tab doesn't shrink the window to ~300px tall.
    scroll.setMinimumHeight(520)
    scroll.setWidget(content)

    shell = QWidget()
    shell_lay = QVBoxLayout(shell)
    shell_lay.setContentsMargins(0, 0, 0, 0)
    shell_lay.setSpacing(0)
    shell_lay.addWidget(scroll)

    win.tabs.addTab(shell, "Video")
