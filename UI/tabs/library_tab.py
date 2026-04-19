from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from UI.library_fs import format_byte_size, scan_finished_videos, scan_run_workspaces
from UI.tab_sections import add_section_spacing
from UI.tutorial_links import help_tooltip_rich


def attach_library_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setSpacing(10)

    header = QLabel("Library")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    sub = QLabel(
        "Browse finished video outputs under videos/ (final.mp4 + assets/) and intermediate run folders under runs/. "
        "Use Refresh after a render completes."
    )
    sub.setWordWrap(True)
    sub.setStyleSheet("color: #8A96A3; font-size: 11px;")
    lay.addWidget(sub)

    _sty = w.style()
    tool_row = QHBoxLayout()
    tool_row.setSpacing(8)

    win.library_refresh_btn = QPushButton()
    win.library_refresh_btn.setIcon(_sty.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
    win.library_refresh_btn.setToolTip(
        help_tooltip_rich(
            "Rescan videos/ and runs/",
            "tasks_library",
            slide=1,
        )
    )
    win.library_refresh_btn.setAccessibleName("Refresh library")
    win.library_refresh_btn.clicked.connect(win._library_refresh)
    win.library_refresh_btn.setMinimumWidth(30)
    win.library_refresh_btn.setMaximumWidth(34)
    win.library_refresh_btn.setMaximumHeight(28)
    tool_row.addWidget(win.library_refresh_btn)

    win.library_open_videos_root_btn = QPushButton("Open videos folder")
    win.library_open_videos_root_btn.setToolTip("Open the videos/ root in the file manager")
    win.library_open_videos_root_btn.clicked.connect(win._library_open_videos_root)
    tool_row.addWidget(win.library_open_videos_root_btn)

    win.library_open_runs_root_btn = QPushButton("Open runs folder")
    win.library_open_runs_root_btn.setToolTip("Open the runs/ root (intermediate workspace per pipeline run)")
    win.library_open_runs_root_btn.clicked.connect(win._library_open_runs_root)
    tool_row.addWidget(win.library_open_runs_root_btn)

    tool_row.addStretch(1)
    lay.addLayout(tool_row)

    add_section_spacing(lay, px=8)

    vg = QGroupBox("videos/ — projects with final.mp4")
    vg.setStyleSheet(
        "QGroupBox { font-size: 12px; font-weight: 600; margin-top: 6px; } "
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #B7B7C2; }"
    )
    vl = QVBoxLayout(vg)
    vl.setContentsMargins(10, 14, 10, 10)

    win.library_videos_table = QTableWidget(0, 4)
    win.library_videos_table.setHorizontalHeaderLabels(["Title", "Folder", "Modified", "final.mp4"])
    win.library_videos_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    win.library_videos_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    win.library_videos_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    win.library_videos_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    win.library_videos_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    win.library_videos_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    win.library_videos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    win.library_videos_table.setMinimumHeight(200)
    win.library_videos_table.cellDoubleClicked.connect(lambda _r, _c: win._library_open_selected_video_dir())
    vl.addWidget(win.library_videos_table)

    vbtn = QHBoxLayout()
    vbtn.setSpacing(8)
    win.library_video_open_btn = QPushButton("Open folder")
    win.library_video_open_btn.setObjectName("primary")
    win.library_video_open_btn.setToolTip("Open the selected video project folder")
    win.library_video_open_btn.clicked.connect(win._library_open_selected_video_dir)
    vbtn.addWidget(win.library_video_open_btn)

    win.library_video_assets_btn = QPushButton("Open assets")
    win.library_video_assets_btn.setToolTip("Open …/assets/ (images, audio, clips)")
    win.library_video_assets_btn.clicked.connect(win._library_open_selected_video_assets)
    vbtn.addWidget(win.library_video_assets_btn)

    win.library_video_play_btn = QPushButton("Play final.mp4")
    win.library_video_play_btn.setToolTip("Open final.mp4 with the default app")
    win.library_video_play_btn.clicked.connect(win._library_play_selected_video)
    vbtn.addWidget(win.library_video_play_btn)

    vbtn.addStretch(1)
    vl.addLayout(vbtn)
    lay.addWidget(vg, 1)

    add_section_spacing(lay, px=10)

    rg = QGroupBox("runs/ — intermediate files per pipeline run")
    rg.setStyleSheet(
        "QGroupBox { font-size: 12px; font-weight: 600; margin-top: 6px; } "
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #B7B7C2; }"
    )
    rl = QVBoxLayout(rg)
    rl.setContentsMargins(10, 14, 10, 10)

    win.library_runs_table = QTableWidget(0, 3)
    win.library_runs_table.setHorizontalHeaderLabels(["Run folder", "Modified", "assets/"])
    win.library_runs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    win.library_runs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    win.library_runs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    win.library_runs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    win.library_runs_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    win.library_runs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    win.library_runs_table.setMinimumHeight(180)
    win.library_runs_table.cellDoubleClicked.connect(lambda _r, _c: win._library_open_selected_run_dir())
    rl.addWidget(win.library_runs_table)

    rbtn = QHBoxLayout()
    rbtn.setSpacing(8)
    win.library_run_open_btn = QPushButton("Open run folder")
    win.library_run_open_btn.setObjectName("primary")
    win.library_run_open_btn.clicked.connect(win._library_open_selected_run_dir)
    rbtn.addWidget(win.library_run_open_btn)

    win.library_run_assets_btn = QPushButton("Open assets")
    win.library_run_assets_btn.setToolTip("Open runs/<id>/assets/")
    win.library_run_assets_btn.clicked.connect(win._library_open_selected_run_assets)
    rbtn.addWidget(win.library_run_assets_btn)

    rbtn.addStretch(1)
    rl.addLayout(rbtn)
    lay.addWidget(rg, 1)

    win._library_tab_widget = w
    win.tabs.addTab(w, "Library")

    def _fmt_ts(ts: float) -> str:
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except (OSError, OverflowError, ValueError):
            return "—"

    def _fill() -> None:
        win.library_videos_table.setRowCount(0)
        for v in scan_finished_videos(win.paths.videos_dir):
            r = win.library_videos_table.rowCount()
            win.library_videos_table.insertRow(r)
            t0 = QTableWidgetItem(v.title[:200])
            t0.setData(Qt.ItemDataRole.UserRole, str(v.path))
            t0.setToolTip(str(v.path))
            win.library_videos_table.setItem(r, 0, t0)
            win.library_videos_table.setItem(r, 1, QTableWidgetItem(v.folder_name[:120]))
            win.library_videos_table.setItem(r, 2, QTableWidgetItem(_fmt_ts(v.modified_ts)))
            win.library_videos_table.setItem(r, 3, QTableWidgetItem(format_byte_size(v.final_bytes)))

        win.library_runs_table.setRowCount(0)
        for rw in scan_run_workspaces(win.paths.runs_dir):
            r = win.library_runs_table.rowCount()
            win.library_runs_table.insertRow(r)
            t0 = QTableWidgetItem(rw.path.name[:120])
            t0.setData(Qt.ItemDataRole.UserRole, str(rw.path))
            t0.setToolTip(str(rw.path))
            win.library_runs_table.setItem(r, 0, t0)
            win.library_runs_table.setItem(r, 1, QTableWidgetItem(_fmt_ts(rw.modified_ts)))
            win.library_runs_table.setItem(
                r, 2, QTableWidgetItem("yes" if rw.has_assets_dir else "—")
            )

    win._library_fill_tables = _fill
    _fill()
