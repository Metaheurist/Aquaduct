from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def _pick_topics_dialog(parent: QWidget, topics: list[str]) -> list[str]:
    d = QDialog(parent)
    d.setWindowTitle("Newest AI news topics (approve)")
    d.setModal(True)
    d.setMinimumSize(720, 520)

    lay = QVBoxLayout(d)
    header = QLabel("Newest AI news topics")
    header.setStyleSheet("font-size: 14px; font-weight: 700;")
    lay.addWidget(header)

    sub = QLabel("These are auto-extracted from the newest headlines. Nothing is added until you click Add selected.")
    sub.setStyleSheet("color: #B7B7C2;")
    sub.setWordWrap(True)
    lay.addWidget(sub)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    inner = QWidget()
    inner_lay = QVBoxLayout(inner)
    inner_lay.setSpacing(6)

    checks: list[QCheckBox] = []
    for t in topics:
        cb = QCheckBox(t)
        cb.setChecked(True)
        checks.append(cb)
        inner_lay.addWidget(cb)
    inner_lay.addStretch(1)
    scroll.setWidget(inner)
    lay.addWidget(scroll, 1)

    btns = QHBoxLayout()
    ok = QPushButton("Add selected")
    ok.setObjectName("primary")
    cancel = QPushButton("Cancel")
    cancel.setObjectName("danger")
    btns.addWidget(ok)
    btns.addWidget(cancel)
    btns.addStretch(1)
    lay.addLayout(btns)

    out: list[str] = []

    def _on_ok() -> None:
        nonlocal out
        out = [c.text().strip() for c in checks if c.isChecked() and c.text().strip()]
        d.accept()

    ok.clicked.connect(_on_ok)
    cancel.clicked.connect(d.reject)

    if d.exec() != QDialog.DialogCode.Accepted:
        return []
    return out


def _no_topics_dialog(parent: QWidget) -> None:
    d = QDialog(parent)
    d.setWindowTitle("Newest AI news topics")
    d.setModal(True)
    d.setMinimumSize(520, 220)
    lay = QVBoxLayout(d)
    header = QLabel("No topics found")
    header.setStyleSheet("font-size: 14px; font-weight: 700;")
    lay.addWidget(header)
    sub = QLabel("Couldn’t extract any topic candidates from the newest headlines right now. Try again in a minute.")
    sub.setStyleSheet("color: #B7B7C2;")
    sub.setWordWrap(True)
    lay.addWidget(sub)
    btns = QHBoxLayout()
    ok = QPushButton("OK")
    ok.setObjectName("primary")
    ok.clicked.connect(d.accept)
    btns.addWidget(ok)
    btns.addStretch(1)
    lay.addLayout(btns)
    d.exec()


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
    win.discover_btn = QPushButton("Discover")
    win.discover_btn.setToolTip("Find newest AI news topics and approve them before adding.")
    win.discover_btn.clicked.connect(win._discover_topics)
    btn_row.addWidget(win.discover_btn)

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
    win._pick_topics_dialog = _pick_topics_dialog
    win._no_topics_dialog = _no_topics_dialog
    win.tabs.addTab(w, "Topics")
