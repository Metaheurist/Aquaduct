from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from UI.services.library_fs import format_byte_size, scan_finished_pictures, scan_finished_videos, scan_run_workspaces
from UI.widgets.tab_scaffold import make_tab_root
from UI.widgets.tab_sections import empty_state_panel, section_card, section_title
from UI.widgets.two_column import two_column_row
from UI.help.tutorial_links import help_tooltip_rich


def attach_library_tab(win) -> None:
    w = QWidget()
    outer = QVBoxLayout(w)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    sub = QLabel()
    sub.setWordWrap(True)
    sub.setStyleSheet("color: #8A96A3; font-size: 12px; margin: 0; padding: 0 0 6px 0;")
    win._library_intro_label = sub

    tool_strip = QWidget()
    tool_row = QHBoxLayout(tool_strip)
    tool_row.setContentsMargins(0, 0, 0, 4)
    tool_row.setSpacing(10)

    _sty = w.style()
    win.library_refresh_btn = QPushButton()
    win.library_refresh_btn.setIcon(_sty.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
    win.library_refresh_btn.setObjectName("libraryRefreshBtn")
    win.library_refresh_btn.setAccessibleName("Refresh library")
    win.library_refresh_btn.clicked.connect(win._library_refresh)
    win.library_refresh_btn.setMinimumWidth(30)
    win.library_refresh_btn.setMaximumWidth(34)
    win.library_refresh_btn.setMaximumHeight(28)
    win.library_refresh_btn.setProperty("shape", "circle")
    tool_row.addWidget(win.library_refresh_btn)

    win.library_open_videos_root_btn = QPushButton("Open videos folder")
    win.library_open_videos_root_btn.setToolTip(
        help_tooltip_rich("Open the videos/ root in the file manager.", "tasks_library", slide=1)
    )
    win.library_open_videos_root_btn.clicked.connect(win._library_open_videos_root)
    tool_row.addWidget(win.library_open_videos_root_btn)

    win.library_open_runs_root_btn = QPushButton("Open runs folder")
    win.library_open_runs_root_btn.setToolTip(
        help_tooltip_rich(
            "Open the runs/ root (intermediate workspace per pipeline run).",
            "tasks_library",
            slide=1,
        )
    )
    win.library_open_runs_root_btn.clicked.connect(win._library_open_runs_root)
    tool_row.addWidget(win.library_open_runs_root_btn)

    win.library_search_edit = QLineEdit()
    win.library_search_edit.setPlaceholderText("Search title, folder, hashtags…")
    win.library_search_edit.setClearButtonEnabled(True)
    win.library_search_edit.setMaximumWidth(280)
    win.library_search_edit.textChanged.connect(lambda _t: win._library_fill_tables())
    tool_row.addWidget(win.library_search_edit)

    tool_row.addStretch(1)

    inner_root, _, _, lay = make_tab_root(
        title="Library",
        before_card=(sub, tool_strip),
        body_card=False,
        fill_vertical=True,
    )

    media_card, media_lay = section_card()
    media_card.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
    win._library_media_card = media_card
    win._library_media_title = section_title("videos/ - projects with final.mp4", emphasis=True)
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
    win.library_videos_table.setMinimumHeight(140)
    win.library_videos_table.setSizePolicy(
        QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    )
    win.library_videos_table.verticalHeader().setVisible(False)
    win.library_videos_table.verticalHeader().setDefaultSectionSize(26)
    win.library_videos_table.cellDoubleClicked.connect(lambda _r, _c: win._library_open_selected_video_dir())
    media_lay.addWidget(win.library_videos_table, 1)

    win.library_media_empty = empty_state_panel(
        "Finished renders show up here. Run a job from the Pipeline tab, then press Refresh.",
        title="No finished projects yet",
    )
    win.library_media_empty.setVisible(False)
    media_lay.addWidget(win.library_media_empty)

    vbtn = QHBoxLayout()
    vbtn.setContentsMargins(0, 8, 0, 0)
    vbtn.setSpacing(10)
    win.library_video_open_btn = QPushButton("Open folder")
    win.library_video_open_btn.setObjectName("primary")
    win.library_video_open_btn.setMinimumWidth(120)
    win.library_video_open_btn.setToolTip(
        help_tooltip_rich("Open the selected video or picture project folder.", "tasks_library", slide=1)
    )
    win.library_video_open_btn.clicked.connect(win._library_open_selected_video_dir)
    vbtn.addWidget(win.library_video_open_btn)

    win.library_video_assets_btn = QPushButton("Open assets")
    win.library_video_assets_btn.setToolTip(
        help_tooltip_rich("Open …/assets/ (images, audio, clips).", "tasks_library", slide=1)
    )
    win.library_video_assets_btn.clicked.connect(win._library_open_selected_video_assets)
    vbtn.addWidget(win.library_video_assets_btn)

    win.library_video_play_btn = QPushButton("Play final.mp4")
    win.library_video_play_btn.setToolTip(
        help_tooltip_rich("Open final.mp4 or final.png with the default app.", "tasks_library", slide=1)
    )
    win.library_video_play_btn.clicked.connect(win._library_play_selected_video)
    vbtn.addWidget(win.library_video_play_btn)

    win.library_resume_series_btn = QPushButton("Resume series")
    win.library_resume_series_btn.setToolTip(
        help_tooltip_rich(
            "Queue remaining episodes for a series folder (uses series.json next episode index).",
            "tasks_library",
            slide=1,
        )
    )
    win.library_resume_series_btn.clicked.connect(win._library_resume_series_queue)
    vbtn.addWidget(win.library_resume_series_btn)

    vbtn.addStretch(1)
    media_lay.addLayout(vbtn)

    runs_card, runs_lay = section_card()
    runs_card.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
    runs_lay.addWidget(section_title("runs/ - intermediate workspaces", emphasis=True))

    win.library_runs_table = QTableWidget(0, 3)
    win.library_runs_table.setHorizontalHeaderLabels(["Run folder", "Modified", "assets/"])
    win.library_runs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    win.library_runs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    win.library_runs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    win.library_runs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    win.library_runs_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    win.library_runs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    win.library_runs_table.setMinimumHeight(140)
    win.library_runs_table.setSizePolicy(
        QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    )
    win.library_runs_table.verticalHeader().setVisible(False)
    win.library_runs_table.verticalHeader().setDefaultSectionSize(26)
    win.library_runs_table.cellDoubleClicked.connect(lambda _r, _c: win._library_open_selected_run_dir())
    runs_lay.addWidget(win.library_runs_table, 1)

    rbtn = QHBoxLayout()
    rbtn.setContentsMargins(0, 8, 0, 0)
    rbtn.setSpacing(10)
    win.library_run_open_btn = QPushButton("Open run folder")
    win.library_run_open_btn.setObjectName("primary")
    win.library_run_open_btn.setMinimumWidth(120)
    win.library_run_open_btn.clicked.connect(win._library_open_selected_run_dir)
    rbtn.addWidget(win.library_run_open_btn)

    win.library_run_assets_btn = QPushButton("Open assets")
    win.library_run_assets_btn.setToolTip(
        help_tooltip_rich("Open runs/<id>/assets/ for the selected workspace.", "tasks_library", slide=1)
    )
    win.library_run_assets_btn.clicked.connect(win._library_open_selected_run_assets)
    rbtn.addWidget(win.library_run_assets_btn)

    rbtn.addStretch(1)
    runs_lay.addLayout(rbtn)

    lay.addWidget(two_column_row(media_card, runs_card, spacing=16), 1)

    inner_root.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
    outer.addWidget(inner_root, 1)

    win._library_tab_widget = w
    win.tabs.addTab(w, "Library")

    def _fmt_ts(ts: float) -> str:
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except (OSError, OverflowError, ValueError):
            return "-"

    def _fill() -> None:
        mm = str(getattr(win.settings, "media_mode", "video") or "video").strip().lower()
        media_root = win.paths.pictures_dir if mm == "photo" else win.paths.videos_dir
        win.library_videos_table.setRowCount(0)
        rows = scan_finished_pictures(media_root) if mm == "photo" else scan_finished_videos(media_root)
        q = ""
        if hasattr(win, "library_search_edit"):
            q = str(win.library_search_edit.text() or "").strip().lower()
        if q:

            def _blob(vp) -> str:
                try:
                    import json

                    mp = vp.path / "meta.json"
                    if mp.is_file():
                        d = json.loads(mp.read_text(encoding="utf-8"))
                        tags = " ".join(str(x) for x in (d.get("hashtags") or []) if x)
                        return f"{d.get('title','')} {d.get('description','')} {tags}".lower()
                except Exception:
                    pass
                return ""

            rows = [
                v
                for v in rows
                if q in v.title.lower() or q in v.folder_name.lower() or q in _blob(v)
            ]
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

        if hasattr(win, "library_media_empty"):
            has_media = win.library_videos_table.rowCount() > 0
            win.library_media_empty.setVisible(not has_media)
            win.library_videos_table.setVisible(has_media)

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
                r, 2, QTableWidgetItem("yes" if rw.has_assets_dir else "-")
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
            help_tooltip_rich(
                "Open the pictures/ root (photo mode outputs).",
                "tasks_library",
                slide=1,
            )
            if is_photo
            else help_tooltip_rich(
                "Open the videos/ root in the file manager.",
                "tasks_library",
                slide=1,
            )
        )
    if hasattr(win, "_library_media_title") and win._library_media_title is not None:
        win._library_media_title.setText(
            "pictures/ - projects with final.png" if is_photo else "videos/ - projects with final.mp4"
        )
    if hasattr(win, "library_videos_table"):
        win.library_videos_table.setHorizontalHeaderLabels(
            ["Title", "Folder", "Modified", "final.png" if is_photo else "final.mp4"]
        )
    if hasattr(win, "library_video_play_btn"):
        win.library_video_play_btn.setText("Open final.png" if is_photo else "Play final.mp4")
        win.library_video_play_btn.setToolTip(
            help_tooltip_rich("Open final.png with the default app.", "tasks_library", slide=1)
            if is_photo
            else help_tooltip_rich("Open final.mp4 with the default app.", "tasks_library", slide=1)
        )
    if hasattr(win, "_library_fill_tables"):
        try:
            win._library_fill_tables()
        except Exception:
            pass
