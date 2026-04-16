from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget

from src.config import VIDEO_FORMATS
from src.personalities import get_personality_presets


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
    cur_vf = str(getattr(win.settings, "video_format", "news") or "news")
    if cur_vf not in VIDEO_FORMATS:
        cur_vf = "news"
    idx_vf = win.video_format_combo.findData(cur_vf)
    win.video_format_combo.setCurrentIndex(idx_vf if idx_vf >= 0 else 0)
    fmt_row.addWidget(win.video_format_combo, 1)
    fmt_row.addStretch(1)
    lay.addLayout(fmt_row)

    vf_hint = QLabel("Tags for the run come from the Topics tab list for this format.")
    vf_hint.setWordWrap(True)
    vf_hint.setStyleSheet("color: #8A96A3; font-size: 11px;")
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

    win.run_status = QLabel("Idle")
    win.run_status.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(win.run_status)

    win.run_progress = QProgressBar()
    win.run_progress.setRange(0, 100)
    win.run_progress.setValue(0)
    lay.addWidget(win.run_progress)

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

    regen_header = QLabel("Regenerate a scene (last run)")
    regen_header.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 10px;")
    lay.addWidget(regen_header)

    regen_row = QHBoxLayout()
    regen_lbl = QLabel("Scene #")
    regen_lbl.setStyleSheet("color: #B7B7C2;")
    regen_row.addWidget(regen_lbl)
    win.regen_scene_spin = QSpinBox()
    win.regen_scene_spin.setRange(1, 12)
    win.regen_scene_spin.setValue(1)
    regen_row.addWidget(win.regen_scene_spin)
    win.regen_scene_btn = QPushButton("Regenerate scene")
    win.regen_scene_btn.clicked.connect(win._regenerate_scene_from_last_run)
    regen_row.addWidget(win.regen_scene_btn)
    regen_row.addStretch(1)
    lay.addLayout(regen_row)

    win.tabs.addTab(w, "Run")
