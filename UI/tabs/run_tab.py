from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget


def attach_run_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Run the factory (one-shot)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

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

    win.log_box = QTextEdit()
    win.log_box.setReadOnly(True)
    win.log_box.setPlaceholderText("Logs will appear here…")
    lay.addWidget(win.log_box, 1)

    win.tabs.addTab(w, "Run")
