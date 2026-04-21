from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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

from UI.services.library_fs import format_byte_size, scan_finished_pictures, scan_finished_videos, scan_run_workspaces
from UI.widgets.tab_sections import add_section_spacing, section_card, section_title
from UI.help.tutorial_links import help_tooltip_rich


def attach_library_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setSpacing(10)

    header = QLabel("Library")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    sub = QLabel()
    sub.setWordWrap(True)
    sub.setStyleSheet("color: #8A96A3; font-size: 11px;")
    win._library_intro_label = sub
    lay.addWidget(sub)

    _sty = w.style()
    tool_row = QHBoxLayout()
    tool_row.setSpacing(8)

    win.library_refresh_btn = QPushButton()
    win.library_refresh_btn.setIcon(_sty.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
    win.library_refresh_btn.setObjectName("libraryRefreshBtn")
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

    add_section_spacing(lay, px=10)

    media_card, media_lay = section_card()
    win._library_media_card = media_card
    win._library_media_title = section_title("videos/ — projects with final.mp4", emphasis=True)
    media_lay.addWidget(win._library_media_title)

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
    media_lay.addWidget(win.library_videos_table)

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
    media_lay.addLayout(vbtn)
    lay.addWidget(media_card, 1)

    add_section_spacing(lay, px=14)

    runs_card, runs_lay = section_card()
    runs_lay.addWidget(section_title("runs/ — intermediate workspaces", emphasis=True))

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
    runs_lay.addWidget(win.library_runs_table)

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
    runs_lay.addLayout(rbtn)
    lay.addWidget(runs_card, 1)

    win._library_tab_widget = w
    win.tabs.addTab(w, "Library")

    def _fmt_ts(ts: float) -> str:
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except (OSError, OverflowError, ValueError):
            return "—"

    def _fill() -> None:
        mm = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
        media_root = win.paths.pictures_dir if mm == "photo" else win.paths.videos_dir
        win.library_videos_table.setRowCount(0)
        rows = scan_finished_pictures(media_root) if mm == "photo" else scan_finished_videos(media_root)
        for v in rows:
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
    refresh_library_tab_for_media_mode(win)


def refresh_library_tab_for_media_mode(win) -> None:
    """Align Library copy, group titles, and scans with Photo vs Video mode."""
    mm = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
    is_photo = mm == "photo"
    if hasattr(win, "_library_intro_label"):
        if is_photo:
            win._library_intro_label.setText(
                "Finished projects under pictures/; pipeline workspaces under runs/. Refresh after a render."
            )
        else:
            win._library_intro_label.setText(
                "Finished outputs under videos/; workspaces under runs/. Refresh after a render."
            )
    if hasattr(win, "library_refresh_btn"):
        win.library_refresh_btn.setToolTip(
            help_tooltip_rich(
                "Rescan pictures/ and runs/" if is_photo else "Rescan videos/ and runs/",
                "tasks_library",
                slide=1,
            )
        )
    if hasattr(win, "library_open_videos_root_btn"):
        win.library_open_videos_root_btn.setText("Open pictures folder" if is_photo else "Open videos folder")
        win.library_open_videos_root_btn.setToolTip(
            "Open the pictures/ root (photo mode outputs)" if is_photo else "Open the videos/ root in the file manager"
        )
    if hasattr(win, "_library_media_title") and win._library_media_title is not None:
        win._library_media_title.setText(
            "pictures/ — projects with final.png" if is_photo else "videos/ — projects with final.mp4"
        )
    if hasattr(win, "library_videos_table"):
        win.library_videos_table.setHorizontalHeaderLabels(
            ["Title", "Folder", "Modified", "final.png" if is_photo else "final.mp4"]
        )
    if hasattr(win, "library_video_play_btn"):
        win.library_video_play_btn.setText("Open final.png" if is_photo else "Play final.mp4")
        win.library_video_play_btn.setToolTip(
            "Open final.png with the default app" if is_photo else "Open final.mp4 with the default app"
        )
    if hasattr(win, "_library_fill_tables"):
        try:
            win._library_fill_tables()
        except Exception:
            pass
