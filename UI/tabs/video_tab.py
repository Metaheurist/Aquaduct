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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def attach_video_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Video settings")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    # Social presets: resolution + aspect
    presets: list[tuple[str, int, int]] = [
        ("TikTok / Reels / Shorts (9:16) — 1080×1920", 1080, 1920),
        ("TikTok / Reels / Shorts (9:16) — 720×1280", 720, 1280),
        ("Instagram Square (1:1) — 1080×1080", 1080, 1080),
        ("YouTube (16:9) — 1920×1080", 1920, 1080),
        ("YouTube (16:9) — 1280×720", 1280, 720),
        ("X/Twitter (16:9) — 1280×720", 1280, 720),
    ]

    win.format_combo = QComboBox()
    win.format_combo.setSizePolicy(QSizePolicy.Policy.Expanding, win.format_combo.sizePolicy().verticalPolicy())
    win.format_combo.setMinimumWidth(560)
    win.format_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    win.format_combo.setMinimumContentsLength(24)
    win.format_combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
    win.format_combo.view().setMinimumWidth(720)
    for label, w0, h0 in presets:
        win.format_combo.addItem(label, (w0, h0))
    cur = (int(win.settings.video.width), int(win.settings.video.height))
    idx = win.format_combo.findData(cur)
    if idx >= 0:
        win.format_combo.setCurrentIndex(idx)
    else:
        # Keep current settings visible even if it's not a known preset
        win.format_combo.insertItem(0, f"Custom — {cur[0]}×{cur[1]}", cur)
        win.format_combo.setCurrentIndex(0)
    form.addRow("Video format", win.format_combo)

    win.images_spin = QSpinBox()
    win.images_spin.setRange(3, 10)
    win.images_spin.setValue(int(win.settings.video.images_per_video))
    form.addRow("Images per video", win.images_spin)

    win.use_slideshow_chk = QCheckBox("Generate images and stitch (slideshow mode)")
    win.use_slideshow_chk.setChecked(bool(win.settings.video.use_image_slideshow))
    form.addRow("", win.use_slideshow_chk)

    win.clips_spin = QSpinBox()
    win.clips_spin.setRange(1, 10)
    win.clips_spin.setValue(int(getattr(win.settings.video, "clips_per_video", 3)))
    form.addRow("Clips per video (clip mode)", win.clips_spin)

    win.clip_seconds_spin = QSpinBox()
    win.clip_seconds_spin.setRange(2, 12)
    win.clip_seconds_spin.setValue(int(round(float(getattr(win.settings.video, "clip_seconds", 4.0)))))
    form.addRow("Seconds per clip (clip mode)", win.clip_seconds_spin)

    win.fps_spin = QSpinBox()
    win.fps_spin.setRange(15, 60)
    win.fps_spin.setValue(int(win.settings.video.fps))
    form.addRow("FPS", win.fps_spin)

    win.min_clip_spin = QSpinBox()
    win.min_clip_spin.setRange(2, 12)
    win.min_clip_spin.setValue(int(round(win.settings.video.microclip_min_s)))
    form.addRow("Micro-clip min seconds", win.min_clip_spin)

    win.max_clip_spin = QSpinBox()
    win.max_clip_spin.setRange(3, 15)
    win.max_clip_spin.setValue(int(round(win.settings.video.microclip_max_s)))
    form.addRow("Micro-clip max seconds", win.max_clip_spin)

    win.bitrate_combo = QComboBox()
    win.bitrate_combo.addItems(["low", "med", "high"])
    win.bitrate_combo.setCurrentText(win.settings.video.bitrate_preset)
    form.addRow("Bitrate preset", win.bitrate_combo)
    win.bitrate_combo.setSizePolicy(QSizePolicy.Policy.Expanding, win.bitrate_combo.sizePolicy().verticalPolicy())
    win.bitrate_combo.setMinimumWidth(560)
    win.bitrate_combo.setToolTip(win.bitrate_combo.currentText())
    win.bitrate_combo.currentIndexChanged.connect(lambda: win.bitrate_combo.setToolTip(win.bitrate_combo.currentText()))

    win.export_microclips_chk = QCheckBox("Export intermediate micro-clips into assets/")
    win.export_microclips_chk.setChecked(bool(win.settings.video.export_microclips))
    form.addRow("", win.export_microclips_chk)

    win.cleanup_images_chk = QCheckBox("Delete generated images after run (save storage)")
    win.cleanup_images_chk.setChecked(bool(getattr(win.settings.video, "cleanup_images_after_run", False)))
    form.addRow("", win.cleanup_images_chk)

    lay.addLayout(form)

    # (Merged) Quality / performance toggles
    divider = QFrame()
    divider.setFrameShape(QFrame.Shape.HLine)
    divider.setStyleSheet("color: #2A2A34; margin-top: 10px; margin-bottom: 6px;")
    lay.addWidget(divider)

    qh = QLabel("Quality / performance")
    qh.setStyleSheet("font-size: 14px; font-weight: 700;")
    lay.addWidget(qh)

    # Keep the same attribute names used by MainWindow._collect_settings_from_ui
    win.prefer_gpu_chk = QCheckBox("Prefer GPU (when available)")
    win.prefer_gpu_chk.setChecked(bool(win.settings.prefer_gpu))
    lay.addWidget(win.prefer_gpu_chk)

    win.try_llm_chk = QCheckBox("Try 4-bit LLM scripting (falls back if unavailable)")
    win.try_llm_chk.setChecked(bool(win.settings.try_llm_4bit))
    lay.addWidget(win.try_llm_chk)

    win.try_sdxl_chk = QCheckBox("Try SDXL Turbo images (falls back if unavailable)")
    win.try_sdxl_chk.setChecked(bool(win.settings.try_sdxl_turbo))
    lay.addWidget(win.try_sdxl_chk)

    info = QLabel("Tip: On 8GB VRAM, the app loads/unloads models per stage to reduce OOM risk.")
    info.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(info)

    # (Merged) Advanced: background music + cache utilities
    divider2 = QFrame()
    divider2.setFrameShape(QFrame.Shape.HLine)
    divider2.setStyleSheet("color: #2A2A34; margin-top: 10px; margin-bottom: 6px;")
    lay.addWidget(divider2)

    ah = QLabel("Advanced")
    ah.setStyleSheet("font-size: 14px; font-weight: 700;")
    lay.addWidget(ah)

    row = QHBoxLayout()
    win.music_path = QLineEdit()
    win.music_path.setPlaceholderText("Optional background music file path…")
    win.music_path.setText(win.settings.background_music_path or "")
    row.addWidget(win.music_path, 1)

    pick = QPushButton("Browse…")
    pick.clicked.connect(win._pick_music)
    row.addWidget(pick)
    lay.addLayout(row)

    cache_row = QHBoxLayout()
    clear_seen = QPushButton("Clear seen URLs cache")
    clear_seen.setObjectName("danger")
    clear_seen.clicked.connect(win._clear_seen_cache)
    cache_row.addWidget(clear_seen)
    cache_row.addStretch(1)
    lay.addLayout(cache_row)

    lay.addStretch(1)
    win.tabs.addTab(w, "Video")
