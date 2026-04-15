from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


def attach_advanced_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Advanced")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

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
    win.tabs.addTab(w, "Advanced")
