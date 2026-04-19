from __future__ import annotations

from UI.frameless_dialog import FramelessDialog
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from src.core.config import VIDEO_FORMATS


def _pick_topics_dialog(parent: QWidget, topics: list[str]) -> list[str]:
    d = FramelessDialog(parent, title="Newest AI news topics (approve)")
    d.setMinimumSize(720, 520)

    header = QLabel("Newest AI news topics")
    header.setStyleSheet("font-size: 14px; font-weight: 700;")
    d.body_layout.addWidget(header)

    sub = QLabel("These are auto-extracted from the newest headlines. Nothing is added until you click Add selected.")
    sub.setStyleSheet("color: #B7B7C2;")
    sub.setWordWrap(True)
    d.body_layout.addWidget(sub)

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
    d.body_layout.addWidget(scroll, 1)

    btns = QHBoxLayout()
    ok = QPushButton("Add selected")
    ok.setObjectName("primary")
    cancel = QPushButton("Cancel")
    cancel.setObjectName("danger")
    btns.addWidget(ok)
    btns.addWidget(cancel)
    btns.addStretch(1)
    d.body_layout.addLayout(btns)

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
    d = FramelessDialog(parent, title="Newest AI news topics")
    d.setMinimumSize(520, 220)
    header = QLabel("No topics found")
    header.setStyleSheet("font-size: 14px; font-weight: 700;")
    d.body_layout.addWidget(header)
    sub = QLabel("Couldn’t extract any topic candidates from the newest headlines right now. Try again in a minute.")
    sub.setStyleSheet("color: #B7B7C2;")
    sub.setWordWrap(True)
    d.body_layout.addWidget(sub)
    btns = QHBoxLayout()
    ok = QPushButton("OK")
    ok.setObjectName("primary")
    ok.clicked.connect(d.accept)
    btns.addWidget(ok)
    btns.addStretch(1)
    d.body_layout.addLayout(btns)
    d.exec()


def attach_topics_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Topic tags (per video format)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    mode_row = QHBoxLayout()
    mode_lbl = QLabel("Edit tags for")
    mode_lbl.setStyleSheet("color: #B7B7C2;")
    mode_row.addWidget(mode_lbl)
    win.topics_mode_combo = QComboBox()
    win.topics_mode_combo.addItem("News", "news")
    win.topics_mode_combo.addItem("Cartoon", "cartoon")
    win.topics_mode_combo.addItem("Explainer", "explainer")
    win.topics_mode_combo.addItem("Cartoon (unhinged)", "unhinged")
    tm = str(getattr(win.settings, "video_format", "news") or "news")
    if tm not in VIDEO_FORMATS:
        tm = "news"
    tmi = win.topics_mode_combo.findData(tm)
    win.topics_mode_combo.setCurrentIndex(tmi if tmi >= 0 else 0)
    mode_row.addWidget(win.topics_mode_combo, 1)
    mode_row.addStretch(1)
    lay.addLayout(mode_row)

    mode_hint = QLabel(
        "Lists are separate per format. Discover fetches headline ideas using this format’s tag list; picks are added here."
    )
    mode_hint.setWordWrap(True)
    mode_hint.setStyleSheet("color: #8A96A3; font-size: 11px;")
    lay.addWidget(mode_hint)

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
    win.discover_btn.setToolTip("Fetch headline ideas biased by this format’s tags; approve phrases to add them to this list.")
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

    win.topics_mode_combo.currentIndexChanged.connect(win._on_topics_mode_changed)
    win._sync_tags_to_ui()
    win._last_topics_mode = str(win.topics_mode_combo.currentData() or "news")
    win._update_discover_for_topic_mode()

    win._pick_topics_dialog = _pick_topics_dialog
    win._no_topics_dialog = _no_topics_dialog
    win.tabs.addTab(w, "Topics")
