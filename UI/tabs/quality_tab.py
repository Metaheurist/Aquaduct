from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget


def attach_quality_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Quality / performance")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    win.prefer_gpu_chk = QCheckBox("Prefer GPU (when available)")
    win.prefer_gpu_chk.setChecked(bool(win.settings.prefer_gpu))
    lay.addWidget(win.prefer_gpu_chk)

    info = QLabel("Tip: On 8GB VRAM, the app loads/unloads models per stage to reduce OOM risk.")
    info.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(info)

    lay.addStretch(1)
    win.tabs.addTab(w, "Quality")
