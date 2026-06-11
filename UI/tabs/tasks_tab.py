from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from UI.help.tutorial_links import help_tooltip_rich
from UI.theme import resolve_palette, token
from UI.widgets.tab_sections import empty_state_panel
from UI.widgets.toolbar_svg_icons import qicon_toolbar


def attach_tasks_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setSpacing(10)

    win._tasks_header_label = QLabel("Tasks (finished videos)")
    header = win._tasks_header_label
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    sub = QLabel(
        "In-progress renders appear at the top while running; each finished run adds a row. Open or copy captions, or "
        "upload to TikTok / YouTube when enabled in the API tab (separate toggles)."
    )
    sub.setWordWrap(True)
    sub.setStyleSheet(f"color: {token('muted', '#8A96A3')}; font-size: 11px;")
    lay.addWidget(sub)

    def _go_pipeline() -> None:
        try:
            win.tabs.setCurrentWidget(getattr(win, "_run_tab_widget", w))
        except Exception:
            pass

    win.tasks_empty_state = empty_state_panel(
        "No runs yet. Head to the Pipeline tab, pick a format, and press Run - "
        "progress and finished videos will show up here.",
        title="Nothing in the queue",
        action_text="Go to Pipeline",
        on_action=_go_pipeline,
    )
    win.tasks_empty_state.setVisible(False)
    lay.addWidget(win.tasks_empty_state)

    _tpal = resolve_palette(getattr(win.settings, "branding", None))
    _t_accent = str(_tpal.get("accent", "#25F4EE"))
    _t_danger = str(_tpal.get("danger", "#FE2C55"))
    _t_icon_px = 22

    run_group = QGroupBox("Run controls")
    run_group.setStyleSheet(
        "QGroupBox { font-size: 12px; font-weight: 600; margin-top: 6px; } "
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #B7B7C2; }"
    )
    row = QHBoxLayout(run_group)
    row.setSpacing(8)
    row.setContentsMargins(10, 14, 10, 10)

    win.tasks_refresh_btn = QPushButton()
    win.tasks_refresh_btn.setIcon(qicon_toolbar("refresh", _t_accent, _t_icon_px))
    win.tasks_refresh_btn.setToolTip(
        help_tooltip_rich(
            "Refresh task list from upload_tasks.json and in-progress rows.",
            "tasks_library",
            slide=0,
        )
    )
    win.tasks_refresh_btn.setAccessibleName("Refresh task list")
    win.tasks_refresh_btn.clicked.connect(win._tasks_refresh)
    win.tasks_refresh_btn.setMinimumWidth(30)
    win.tasks_refresh_btn.setMaximumWidth(34)
    win.tasks_refresh_btn.setMaximumHeight(28)
    row.addWidget(win.tasks_refresh_btn)

    win.tasks_pause_btn = QPushButton()
    # Pause vs play SVG: _sync_tasks_pause_button_appearance (main window).
    win.tasks_pause_btn.setToolTip(
        help_tooltip_rich(
            "Pause between pipeline steps (not mid–GPU operation). Click again to resume.",
            "run",
            slide=3,
        )
    )
    win.tasks_pause_btn.setAccessibleName("Pause")
    win.tasks_pause_btn.setEnabled(False)
    win.tasks_pause_btn.clicked.connect(win._on_tasks_pause_toggle)
    win.tasks_pause_btn.setMinimumWidth(30)
    win.tasks_pause_btn.setMaximumWidth(34)
    win.tasks_pause_btn.setMaximumHeight(28)
    row.addWidget(win.tasks_pause_btn)

    win.tasks_stop_btn = QPushButton()
    win.tasks_stop_btn.setIcon(qicon_toolbar("stop", _t_danger, _t_icon_px))
    win.tasks_stop_btn.setToolTip(
        help_tooltip_rich(
            "Request cancel at the next checkpoint (may take a few seconds).",
            "run",
            slide=3,
        )
    )
    win.tasks_stop_btn.setAccessibleName("Stop")
    win.tasks_stop_btn.setObjectName("danger")
    win.tasks_stop_btn.setEnabled(False)
    win.tasks_stop_btn.clicked.connect(win._on_tasks_stop)
    win.tasks_stop_btn.setMinimumWidth(30)
    win.tasks_stop_btn.setMaximumWidth(34)
    win.tasks_stop_btn.setMaximumHeight(28)
    row.addWidget(win.tasks_stop_btn)
    row.addStretch(1)
    lay.addWidget(run_group)

    if hasattr(win, "_sync_tasks_pause_button_appearance"):
        win._sync_tasks_pause_button_appearance()

    win.tasks_table = QTableWidget(0, 5)
    win.tasks_table.setHorizontalHeaderLabels(["Title", "Status", "YouTube", "Created", "Output folder"])
    win.tasks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    win.tasks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    win.tasks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    win.tasks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    win.tasks_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    win.tasks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    win.tasks_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    win.tasks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    lay.addWidget(win.tasks_table, 1)

    actions_group = QGroupBox("Selected task")
    actions_group.setStyleSheet(
        "QGroupBox { font-size: 12px; font-weight: 600; margin-top: 6px; } "
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #B7B7C2; }"
    )
    btn_row = QHBoxLayout(actions_group)
    btn_row.setSpacing(8)
    btn_row.setContentsMargins(10, 14, 10, 10)

    win.tasks_open_btn = QPushButton("Open folder")
    win.tasks_open_btn.setObjectName("primary")
    win.tasks_open_btn.setAccessibleName("Open output folder")
    win.tasks_open_btn.clicked.connect(win._tasks_open_folder)
    btn_row.addWidget(win.tasks_open_btn)

    win.tasks_play_btn = QPushButton("Play video")
    win.tasks_play_btn.setAccessibleName("Play video")
    win.tasks_play_btn.clicked.connect(win._tasks_play_video)
    btn_row.addWidget(win.tasks_play_btn)

    win.tasks_copy_btn = QPushButton("Copy caption")
    win.tasks_copy_btn.setAccessibleName("Copy caption")
    win.tasks_copy_btn.clicked.connect(win._tasks_copy_caption)
    btn_row.addWidget(win.tasks_copy_btn)

    win.tasks_approve_btn = QPushButton("Approve")
    win.tasks_approve_btn.setObjectName("primary")
    win.tasks_approve_btn.setAccessibleName("Approve task for publishing")
    win.tasks_approve_btn.setToolTip(
        help_tooltip_rich(
            "Mark the selected finished render as approved. Required before TikTok/YouTube upload "
            "(including auto-upload when enabled on the API tab).",
            "tasks_library",
            slide=0,
        )
    )
    win.tasks_approve_btn.clicked.connect(win._tasks_approve_selected)
    btn_row.addWidget(win.tasks_approve_btn)

    win.tasks_posted_btn = QPushButton("Mark posted (manual)")
    win.tasks_posted_btn.setAccessibleName("Mark posted manually")
    win.tasks_posted_btn.clicked.connect(win._tasks_mark_posted_manual)
    btn_row.addWidget(win.tasks_posted_btn)

    win.tasks_tiktok_btn = QPushButton("Upload to TikTok")
    win.tasks_tiktok_btn.setAccessibleName("Upload to TikTok")
    win.tasks_tiktok_btn.clicked.connect(win._tasks_upload_tiktok)
    btn_row.addWidget(win.tasks_tiktok_btn)

    win.tasks_youtube_btn = QPushButton("Upload to YouTube")
    win.tasks_youtube_btn.setAccessibleName("Upload to YouTube")
    win.tasks_youtube_btn.clicked.connect(win._tasks_upload_youtube)
    btn_row.addWidget(win.tasks_youtube_btn)

    if hasattr(win, "_sync_tasks_upload_buttons"):
        win._sync_tasks_upload_buttons()

    win.tasks_remove_btn = QPushButton("Remove")
    win.tasks_remove_btn.setObjectName("danger")
    win.tasks_remove_btn.setAccessibleName("Remove selected task")
    win.tasks_remove_btn.clicked.connect(win._tasks_remove_selected)
    btn_row.addWidget(win.tasks_remove_btn)

    btn_row.addStretch(1)
    lay.addWidget(actions_group)

    # Activity log: a visible in-app sink for `_append_log` (previously file/stdout only).
    log_toggle = QToolButton()
    from PyQt6.QtCore import QSize

    log_toggle.setIcon(qicon_toolbar("chevron_right", token("muted", "#9BA6B8"), 14))
    log_toggle.setIconSize(QSize(14, 14))
    log_toggle.setText("  Activity log")
    log_toggle.setCheckable(True)
    log_toggle.setChecked(False)
    log_toggle.setAutoRaise(True)
    log_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
    log_toggle.setStyleSheet(
        f"QToolButton {{ color: {token('muted', '#9BA6B8')}; font-size: 12px; font-weight: 600; "
        "border: none; padding: 2px 0; }"
    )
    log_toggle.setToolTip(
        help_tooltip_rich(
            "In-app log of warnings, queue messages, and pipeline notices. Also written to logs/ui.log.",
            "tasks_library",
            slide=0,
        )
    )
    lay.addWidget(log_toggle)

    win.log_box = QTextEdit()
    win.log_box.setReadOnly(True)
    win.log_box.setMaximumHeight(150)
    win.log_box.setVisible(False)
    win.log_box.setPlaceholderText("Activity from runs, downloads, and background tasks appears here.")
    lay.addWidget(win.log_box)

    def _toggle_log(checked: bool) -> None:
        win.log_box.setVisible(checked)
        kind = "chevron_down" if checked else "chevron_right"
        log_toggle.setIcon(qicon_toolbar(kind, token("muted", "#9BA6B8"), 14))
        log_toggle.setText("  Activity log")
        if hasattr(win, "_resize_to_current_tab"):
            try:
                win._resize_to_current_tab()
            except Exception:
                pass

    log_toggle.toggled.connect(_toggle_log)

    win._tasks_tab_widget = w
    win.tabs.addTab(w, "Tasks")


def refresh_tasks_tab_for_media_mode(win) -> None:
    """Align Tasks tab copy with Photo vs Video mode."""
    mm = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
    is_photo = mm == "photo"
    if hasattr(win, "_tasks_header_label"):
        win._tasks_header_label.setText(
            "Tasks (finished pictures)" if is_photo else "Tasks (in-progress & uploads)"
        )
