from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget


def attach_run_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Run the factory (one-shot)")
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

    win.open_videos_btn = QPushButton("Open videos folder")
    win.open_videos_btn.clicked.connect(win._open_videos)
    row.addWidget(win.open_videos_btn)

    win.save_btn = QPushButton("Save settings")
    win.save_btn.clicked.connect(win._save_settings)
    row.addWidget(win.save_btn)

    row.addStretch(1)
    lay.addLayout(row)

    win.tabs.addTab(w, "Run")
