from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def attach_tasks_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Tasks (finished videos)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    sub = QLabel(
        "Each successful run adds a row. Open or copy captions for manual posting, or upload to TikTok / YouTube when "
        "enabled and connected in the API tab (separate toggles)."
    )
    sub.setWordWrap(True)
    sub.setStyleSheet("color: #8A96A3; font-size: 11px;")
    lay.addWidget(sub)

    win.tasks_table = QTableWidget(0, 5)
    win.tasks_table.setHorizontalHeaderLabels(["Title", "Status", "YouTube", "Created", "Video folder"])
    win.tasks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    win.tasks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    win.tasks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    win.tasks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    win.tasks_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    win.tasks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    win.tasks_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    win.tasks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    lay.addWidget(win.tasks_table, 1)

    row = QHBoxLayout()
    ref = QPushButton("Refresh")
    ref.clicked.connect(win._tasks_refresh)
    row.addWidget(ref)
    row.addStretch(1)
    lay.addLayout(row)

    btn_row = QHBoxLayout()
    win.tasks_open_btn = QPushButton("Open folder")
    win.tasks_open_btn.setObjectName("primary")
    win.tasks_open_btn.clicked.connect(win._tasks_open_folder)
    btn_row.addWidget(win.tasks_open_btn)

    win.tasks_play_btn = QPushButton("Play video")
    win.tasks_play_btn.clicked.connect(win._tasks_play_video)
    btn_row.addWidget(win.tasks_play_btn)

    win.tasks_copy_btn = QPushButton("Copy caption")
    win.tasks_copy_btn.clicked.connect(win._tasks_copy_caption)
    btn_row.addWidget(win.tasks_copy_btn)

    win.tasks_posted_btn = QPushButton("Mark posted (manual)")
    win.tasks_posted_btn.clicked.connect(win._tasks_mark_posted_manual)
    btn_row.addWidget(win.tasks_posted_btn)

    win.tasks_tiktok_btn = QPushButton("Upload to TikTok")
    win.tasks_tiktok_btn.clicked.connect(win._tasks_upload_tiktok)
    btn_row.addWidget(win.tasks_tiktok_btn)

    win.tasks_youtube_btn = QPushButton("Upload to YouTube")
    win.tasks_youtube_btn.clicked.connect(win._tasks_upload_youtube)
    btn_row.addWidget(win.tasks_youtube_btn)

    win.tasks_remove_btn = QPushButton("Remove")
    win.tasks_remove_btn.setObjectName("danger")
    win.tasks_remove_btn.clicked.connect(win._tasks_remove_selected)
    btn_row.addWidget(win.tasks_remove_btn)

    btn_row.addStretch(1)
    lay.addLayout(btn_row)

    win.tabs.addTab(w, "Tasks")
