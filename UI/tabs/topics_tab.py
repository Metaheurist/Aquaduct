from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


def attach_topics_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Topic tags (used for discovery + scripting)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    row = QHBoxLayout()
    win.tag_input = QLineEdit()
    win.tag_input.setPlaceholderText("Add a topic tag, e.g. “AI video editor”, “agentic workflow”, “LLM IDE”…")
    row.addWidget(win.tag_input, 1)

    add_btn = QPushButton("Add tag")
    add_btn.setObjectName("primary")
    add_btn.clicked.connect(win._add_tag)
    row.addWidget(add_btn)
    lay.addLayout(row)

    win.tag_list = QListWidget()
    lay.addWidget(win.tag_list, 1)

    btn_row = QHBoxLayout()
    rm_btn = QPushButton("Remove selected")
    rm_btn.setObjectName("danger")
    rm_btn.clicked.connect(win._remove_selected_tags)
    btn_row.addWidget(rm_btn)

    clear_btn = QPushButton("Clear all")
    clear_btn.clicked.connect(win._clear_tags)
    btn_row.addWidget(clear_btn)
    btn_row.addStretch(1)
    lay.addLayout(btn_row)

    win._sync_tags_to_ui()
    win.tabs.addTab(w, "Topics")
