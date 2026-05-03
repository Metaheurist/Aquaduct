from __future__ import annotations

from UI.dialogs.frameless_dialog import FramelessDialog
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

from src.content.topics import discover_uses_headline_sources, normalize_video_format
from src.core.config import VIDEO_FORMATS
from UI.widgets.no_wheel_controls import NoWheelComboBox
from UI.widgets.tab_sections import section_card, section_title
from UI.help.tutorial_links import help_tooltip_rich


def _is_health_topics_mode(topic_mode: str | None) -> bool:
    return normalize_video_format(str(topic_mode or "news")) == "health_advice"


def _is_web_firecrawl_discover_mode(topic_mode: str | None) -> bool:
    """Headline RSS discover vs Firecrawl-first (creative + health_advice)."""
    return not discover_uses_headline_sources(str(topic_mode or "news"))


def _pick_topics_dialog(
    parent: QWidget,
    topics: list[str],
    *,
    topic_mode: str = "news",
    firecrawl_ready: bool = True,
) -> list[str]:
    web_fc = _is_web_firecrawl_discover_mode(topic_mode)
    health = _is_health_topics_mode(topic_mode)
    win_title = (
        "Discover: approve wellness topic ideas"
        if health
        else "Discover: approve creative seeds"
        if web_fc
        else "Discover: approve topic ideas (news)"
    )
    d = FramelessDialog(parent, title=win_title)
    d.setMinimumSize(720, 520)

    header = QLabel(
        "Wellness topics from the web"
        if health
        else "Creative seeds from the web"
        if web_fc
        else "Topic ideas from headlines"
    )
    header.setStyleSheet("font-size: 14px; font-weight: 700;")
    d.body_layout.addWidget(header)

    if health:
        sub = QLabel(
            "Phrases are parsed from page titles Firecrawl found while searching for wellness tips, healthy habits, "
            "and general health-education pages (not Google News headlines). "
            + (
                "Enable Firecrawl on the API tab with a key for reliable results."
                if not firecrawl_ready
                else "Nothing is added until you click Add selected."
            )
        )
    elif web_fc:
        sub = QLabel(
            "Phrases are parsed from page titles Firecrawl found while searching for jokes, memes, short stories, "
            "horror fiction, art, and fandom threads (not Google News headlines). "
            + (
                "Enable Firecrawl on the API tab with a key for reliable results."
                if not firecrawl_ready
                else "Nothing is added until you click Add selected."
            )
        )
    else:
        sub = QLabel(
            "These are auto-extracted from recent headline-style results. Nothing is added until you click Add selected."
        )
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


def _no_topics_dialog(
    parent: QWidget,
    *,
    topic_mode: str = "news",
    firecrawl_ready: bool = True,
) -> None:
    web_fc = _is_web_firecrawl_discover_mode(topic_mode)
    health = _is_health_topics_mode(topic_mode)
    win_title = (
        "Discover: wellness topics"
        if health
        else "Discover: creative seeds"
        if web_fc
        else "Discover: topic ideas"
    )
    d = FramelessDialog(parent, title=win_title)
    d.setMinimumSize(520, 260)
    if health:
        header = QLabel("No wellness topics yet")
        header.setStyleSheet("font-size: 14px; font-weight: 700;")
        d.body_layout.addWidget(header)
        if not firecrawl_ready:
            sub = QLabel(
                "Health advice mode uses Firecrawl to search the open web for wellness and health-education pages, "
                "then suggests topic phrases from titles.\n\n"
                "Turn on Firecrawl on the API tab and add your API key (or set the FIRECRAWL_API_KEY "
                "environment variable), then try Discover again."
            )
        else:
            sub = QLabel(
                "Firecrawl did not return enough pages to extract phrases from. "
                "Add a few topic tags above to steer the search, try again in a minute, or check your API quota."
            )
    elif web_fc:
        header = QLabel("No creative seeds yet")
        header.setStyleSheet("font-size: 14px; font-weight: 700;")
        d.body_layout.addWidget(header)
        if not firecrawl_ready:
            sub = QLabel(
                "Creative formats (Cartoon, Unhinged, Creepypasta) use Firecrawl to search the open web for jokes, memes, "
                "horror fiction, stories, and image-heavy pages (then turns titles into topic tags).\n\n"
                "Turn on Firecrawl on the API tab and add your API key (or set the FIRECRAWL_API_KEY "
                "environment variable), then try Discover again."
            )
        else:
            sub = QLabel(
                "Firecrawl did not return enough pages to extract phrases from. "
                "Add a few topic tags above to steer the search, try again in a minute, or check your API quota."
            )
    else:
        header = QLabel("No topics found")
        header.setStyleSheet("font-size: 14px; font-weight: 700;")
        d.body_layout.addWidget(header)
        sub = QLabel(
            "Couldn’t extract any topic candidates from the newest headlines right now. Try again in a minute."
        )
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

    header = QLabel("Topics")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    intro = QLabel("Per-mode tag lists - same modes as Run. Details: hover Help or the mode control.")
    intro.setStyleSheet("color: #B7B7C2; font-size: 12px;")
    intro.setWordWrap(True)
    lay.addWidget(intro)

    tags_card, tags_lay = section_card()
    tags_lay.addWidget(section_title("Tags for selected mode", emphasis=True))

    mode_row = QHBoxLayout()
    mode_lbl = QLabel("Edit tags for")
    mode_lbl.setStyleSheet("color: #B7B7C2;")
    mode_row.addWidget(mode_lbl)
    win.topics_mode_combo = NoWheelComboBox()
    win.topics_mode_combo.addItem("News", "news")
    win.topics_mode_combo.addItem("Cartoon", "cartoon")
    win.topics_mode_combo.addItem("Explainer", "explainer")
    win.topics_mode_combo.addItem("Cartoon (unhinged)", "unhinged")
    win.topics_mode_combo.addItem("Creepypasta", "creepypasta")
    win.topics_mode_combo.addItem("Health advice", "health_advice")
    tm = str(getattr(win.settings, "video_format", "news") or "news")
    if tm not in VIDEO_FORMATS:
        tm = "news"
    tmi = win.topics_mode_combo.findData(tm)
    win.topics_mode_combo.setCurrentIndex(tmi if tmi >= 0 else 0)
    mode_row.addWidget(win.topics_mode_combo, 1)
    mode_row.addStretch(1)
    tags_lay.addLayout(mode_row)
    win.topics_mode_combo.setToolTip(
        help_tooltip_rich(
            "Separate lists per source mode (same as Run). Photo mode: tags still steer prompts. "
            "News/Explainer Discover: headline ideas. Cartoon / Unhinged / Creepypasta / Health advice: Firecrawl web pages. "
            "Approved lines are added to this list.",
            "topics_chars",
            slide=1,
        )
    )

    row = QHBoxLayout()
    win.tag_input = QLineEdit()
    win.tag_input.setPlaceholderText("Add a topic tag, e.g. “AI video editor”, “agentic workflow”, “LLM IDE”…")
    row.addWidget(win.tag_input, 1)

    add_btn = QPushButton("Add tag")
    add_btn.setObjectName("primary")
    add_btn.clicked.connect(win._add_tag)
    row.addWidget(add_btn)
    tags_lay.addLayout(row)

    win.tag_list = QListWidget()
    tags_lay.addWidget(win.tag_list, 1)

    notes_intro = QLabel(
        "Optional grounding line per tag: the script LLM treats topic tags as hard constraints - "
        "these notes add extra direction (tone, must-mention angles, things to avoid)."
    )
    notes_intro.setWordWrap(True)
    notes_intro.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    tags_lay.addWidget(section_title("Per-tag notes (grounding)", emphasis=False))
    tags_lay.addWidget(notes_intro)

    topic_notes_scroll = QScrollArea()
    topic_notes_scroll.setWidgetResizable(True)
    topic_notes_scroll.setMinimumHeight(100)
    topic_notes_scroll.setMaximumHeight(240)
    win.topic_notes_inner = QWidget()
    win.topic_notes_layout = QVBoxLayout(win.topic_notes_inner)
    win.topic_notes_layout.setContentsMargins(4, 4, 4, 4)
    topic_notes_scroll.setWidget(win.topic_notes_inner)
    tags_lay.addWidget(topic_notes_scroll)

    notes_btns = QHBoxLayout()
    win.topic_notes_llm_btn = QPushButton("Suggest with LLM")
    win.topic_notes_llm_btn.setToolTip(
        help_tooltip_rich(
            "Generates grounding lines from the Script LLM - one concise line per tag (API uses your Models API settings; "
            "offline uses Model tab HF script model). Checked box replaces existing notes; otherwise empty fields only.",
            "topics_chars",
            slide=0,
        )
    )
    win.topic_notes_llm_btn.clicked.connect(win._topic_notes_suggest_llm)
    notes_btns.addWidget(win.topic_notes_llm_btn)
    win.topic_notes_llm_overwrite = QCheckBox("Replace existing notes")
    win.topic_notes_llm_overwrite.setToolTip("When unchecked, only tags with blank grounding boxes are filled.")
    notes_btns.addWidget(win.topic_notes_llm_overwrite)
    notes_btns.addStretch(1)
    tags_lay.addLayout(notes_btns)

    btn_row = QHBoxLayout()
    win.discover_btn = QPushButton("Discover")
    win.discover_btn.setToolTip(
        help_tooltip_rich(
            "News/Explainer: headline ideas from your tags. Cartoon/Unhinged/Creepypasta: memes and stories from the web. "
            "Health advice: wellness and health-education pages. All web modes need Firecrawl on the API tab.",
            "topics_chars",
            slide=1,
        )
    )
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
    tags_lay.addLayout(btn_row)

    lay.addWidget(tags_card, 1)

    win.topics_mode_combo.currentIndexChanged.connect(win._on_topics_mode_changed)
    win._sync_tags_to_ui()
    win._last_topics_mode = str(win.topics_mode_combo.currentData() or "news")
    win._update_discover_for_topic_mode()

    win._pick_topics_dialog = _pick_topics_dialog
    win._no_topics_dialog = _no_topics_dialog
    win.tabs.addTab(w, "Topics")
