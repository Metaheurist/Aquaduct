from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout, QWidget


def attach_video_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Video settings")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    form = QFormLayout()
    win.images_spin = QSpinBox()
    win.images_spin.setRange(3, 10)
    win.images_spin.setValue(int(win.settings.video.images_per_video))
    form.addRow("Images per video", win.images_spin)

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

    win.export_microclips_chk = QCheckBox("Export intermediate micro-clips into assets/")
    win.export_microclips_chk.setChecked(bool(win.settings.video.export_microclips))
    form.addRow("", win.export_microclips_chk)

    lay.addLayout(form)
    lay.addStretch(1)
    win.tabs.addTab(w, "Video")
