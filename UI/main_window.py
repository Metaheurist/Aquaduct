from __future__ import annotations

import json
import os
import secrets
from collections.abc import Callable
import subprocess
import sys
import threading
import webbrowser
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtCore import QTimer, QUrl, Qt, QPoint, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QTabWidget,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.config import AppSettings, BrandingSettings, VideoSettings, VIDEO_FORMATS, get_paths
from src.crawler import clear_news_seen_cache_files
from src.topics import normalize_video_format
from src.fs_delete import rmtree_robust, unlink_file
from src.model_manager import download_model_to_project, list_installed_repo_ids_from_disk, model_has_local_snapshot
from src.preflight import preflight_check
from src.utils_ffmpeg import find_ffmpeg
from src.ui_settings import load_settings, save_settings, settings_path
from src.personalities import get_personality_by_id
from debug import dprint

from UI.paths import project_root
from UI.tabs import (
    attach_api_tab,
    attach_branding_tab,
    attach_captions_tab,
    attach_characters_tab,
    attach_my_pc_tab,
    attach_run_tab,
    attach_settings_tab,
    attach_tasks_tab,
    attach_topics_tab,
    attach_video_tab,
)
from UI.download_popup import DownloadPopup
from UI.workers import (
    FFmpegEnsureWorker,
    ModelDownloadWorker,
    ModelIntegrityVerifyWorker,
    PipelineBatchWorker,
    PipelineWorker,
    PreviewWorker,
    StoryboardWorker,
    TikTokUploadWorker,
    YouTubeUploadWorker,
)
from UI.workers import TopicDiscoverWorker
from UI.preview_dialog import PreviewDialog
from UI.storyboard_dialog import StoryboardPreviewDialog
from UI.progress_tasks import format_status_line

_TASKS_ACTIVE_JOB_TOKEN = "__active_job__"


class _InternetStatusBridge(QObject):
    """Emit reachability from a worker thread (Qt delivers the slot on the GUI thread)."""

    finished = pyqtSignal(bool)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Aquaduct")

        # Borderless + fixed size (non-resizable)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        # Fixed width, dynamic height (still non-resizable).
        self.setFixedWidth(1000)
        self._drag_pos: QPoint | None = None

        self.paths = get_paths()
        self.settings = load_settings()
        self._apply_saved_hf_token_to_env()

        self.tabs = QTabWidget()
        # Custom title bar (frameless window needs its own controls)
        self._root = QWidget()
        root_lay = QVBoxLayout(self._root)
        root_lay.setContentsMargins(10, 10, 10, 10)
        root_lay.setSpacing(8)

        self._title_bar = QWidget()
        title_row = QHBoxLayout(self._title_bar)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title = QLabel("Aquaduct")
        title.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF;")
        title_row.addWidget(title, 1)

        save_btn = QPushButton("💾")
        save_btn.setObjectName("saveBtn")
        save_btn.setFixedSize(44, 32)
        save_btn.setToolTip("Save settings")
        save_btn.clicked.connect(self._save_settings)
        title_row.addWidget(save_btn, 0, Qt.AlignmentFlag.AlignRight)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(44, 32)
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)
        root_lay.addWidget(self._title_bar, 0)

        self._internet_online: bool | None = None
        self._network_banner = QLabel()
        self._network_banner.setVisible(False)
        self._network_banner.setWordWrap(True)
        self._network_banner.setStyleSheet(
            "background-color: rgba(255, 160, 72, 0.12); color: #E8C080; padding: 8px 10px; "
            "border-radius: 8px; border: 1px solid rgba(255, 190, 120, 0.28); font-size: 12px;"
        )
        self._network_banner.setText(
            "No internet connection detected. Headlines and new model downloads need a network. "
            "Preview and full runs still work when your chosen models are already saved on disk."
        )
        root_lay.addWidget(self._network_banner, 0)

        # Don't force the tab widget to expand; we'll size the window to its active page.
        root_lay.addWidget(self.tabs, 0)
        self.setCentralWidget(self._root)

        attach_run_tab(self)
        attach_characters_tab(self)
        attach_topics_tab(self)
        attach_tasks_tab(self)
        attach_video_tab(self)
        attach_captions_tab(self)
        attach_branding_tab(self)
        attach_api_tab(self)
        attach_settings_tab(self)
        attach_my_pc_tab(self)

        # Shrink/grow window to the active tab (QTabWidget otherwise sizes to the tallest page).
        self.tabs.currentChanged.connect(self._on_tab_changed)
        QTimer.singleShot(0, self._resize_to_current_tab)
        QTimer.singleShot(0, self._tasks_refresh)
        # Prompt for HF token once the window is ready (if needed).
        QTimer.singleShot(0, self._maybe_prompt_hf_token)
        QTimer.singleShot(0, self._update_hf_api_warnings)
        if hasattr(self, "personality_combo"):
            self.personality_combo.currentIndexChanged.connect(self._update_personality_hint)
            self._update_personality_hint()

        self._internet_bridge = _InternetStatusBridge()
        self._internet_bridge.finished.connect(self._on_internet_status)

        def _probe_internet() -> None:
            from src.network_status import is_internet_likely_reachable

            ok = is_internet_likely_reachable()
            self._internet_bridge.finished.emit(ok)

        threading.Thread(target=_probe_internet, daemon=True).start()

        self.worker: PipelineWorker | None = None
        self.topic_worker: TopicDiscoverWorker | None = None
        self.download_worker: ModelDownloadWorker | None = None
        self._download_popup: DownloadPopup | None = None
        self._paused_download_repo_ids: list[str] | None = None
        self._paused_download_title: str | None = None
        self.preview_worker: PreviewWorker | None = None
        self.storyboard_worker: StoryboardWorker | None = None
        self.tiktok_upload_worker: TikTokUploadWorker | None = None
        self.youtube_upload_worker: YouTubeUploadWorker | None = None
        self._integrity_worker: ModelIntegrityVerifyWorker | None = None
        self._ffmpeg_ensure_worker: FFmpegEnsureWorker | None = None
        self._ffmpeg_run_after: Callable[[], None] | None = None
        self._tasks_active_row: dict[str, str] | None = None
        self._last_preview_pkg = None
        self._last_preview_sources = None
        self._last_preview_prompts = None
        self._last_preview_personality_id = "auto"
        self._last_storyboard_manifest = None
        self._last_storyboard_grid = None

        self._reset_run_session_state()

    def _apply_saved_hf_token_to_env(self) -> None:
        """
        If user saved an HF token in ui_settings.json, expose it to huggingface_hub via env var
        for the current app session (unless the user already provided one via env).
        """
        try:
            if os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
                return
            if not bool(getattr(self.settings, "hf_api_enabled", True)):
                return
            t = str(getattr(self.settings, "hf_token", "") or "").strip()
            if not t:
                return
            os.environ["HF_TOKEN"] = t
        except Exception:
            pass

    def _apply_hf_token_from_current_settings(self) -> None:
        """After save or dialog: sync HF_TOKEN from settings when user enabled HF API."""
        try:
            if os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
                return
            if not bool(getattr(self.settings, "hf_api_enabled", True)):
                return
            t = str(getattr(self.settings, "hf_token", "") or "").strip()
            if t:
                os.environ["HF_TOKEN"] = t
        except Exception:
            pass

    def _update_hf_api_warnings(self) -> None:
        """Model tab banner when Hugging Face token usage is disabled (soft)."""
        try:
            if not hasattr(self, "_settings_hf_banner"):
                return
            hf_on = bool(getattr(self.settings, "hf_api_enabled", True))
            if hasattr(self, "api_hf_enabled_chk"):
                hf_on = bool(self.api_hf_enabled_chk.isChecked())
            self._settings_hf_banner.setVisible(not hf_on)
        except Exception:
            pass

    def _maybe_prompt_hf_token(self) -> None:
        """
        If no token is available (env or saved settings), prompt user to paste one.
        """
        try:
            if not bool(getattr(self.settings, "hf_api_enabled", True)):
                return
            if os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
                return
            saved = str(getattr(self.settings, "hf_token", "") or "").strip()
            if saved:
                os.environ["HF_TOKEN"] = saved
                return
        except Exception:
            pass

        dlg = QDialog(self)
        dlg.setWindowTitle("Hugging Face token (recommended)")
        dlg.setModal(True)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        _hf_tokens = "https://huggingface.co/settings/tokens"
        hint = QLabel(
            "Some models and size lookups require a Hugging Face access token.<br><br>"
            "<b>How to get one:</b><br>"
            f'- Go to <a href="{_hf_tokens}">{_hf_tokens}</a><br>'
            "- Create a token (a standard read-only token is enough)<br>"
            "- Paste it below<br><br>"
            "We will store it in ui_settings.json and use it for authenticated Hub requests."
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setOpenExternalLinks(True)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "QLabel { color: #B7B7C2; } "
            "QLabel a { color: #25F4EE; text-decoration: none; } "
            "QLabel a:hover { text-decoration: underline; }"
        )
        lay.addWidget(hint)

        inp = QLineEdit()
        inp.setPlaceholderText("hf_... (paste your token here)")
        inp.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(inp)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        token = str(inp.text() or "").strip()
        if not token:
            return

        # Persist to ui_settings.json + env for current session
        try:
            self.settings = replace(self.settings, hf_token=token, hf_api_enabled=True)
            save_settings(self.settings)
        except Exception:
            pass
        try:
            os.environ["HF_TOKEN"] = token
        except Exception:
            pass

    def _reset_run_session_state(self) -> None:
        """
        Each app launch: clear Run tab progress, last-run scene #, and in-memory preview/storyboard
        so the UI never shows a previous session's status (e.g. Preview failed / partial progress).
        """
        self._clear_tasks_active_row()
        if hasattr(self, "regen_scene_spin"):
            self.regen_scene_spin.setValue(1)
        if hasattr(self, "preview_btn"):
            self.preview_btn.setEnabled(True)
            self.preview_btn.setText("Preview")
        if hasattr(self, "storyboard_btn"):
            self.storyboard_btn.setEnabled(True)
            self.storyboard_btn.setText("Storyboard Preview")
        if hasattr(self, "run_btn"):
            self.run_btn.setEnabled(True)
        self._last_preview_pkg = None
        self._last_preview_sources = None
        self._last_preview_prompts = None
        self._last_preview_personality_id = "auto"
        self._last_storyboard_manifest = None
        self._last_storyboard_grid = None

    def _busy_background_jobs(self) -> list[str]:
        """Human-readable labels for workers that may hold files open."""
        out: list[str] = []
        if self.worker and self.worker.isRunning():
            out.append("video generation")
        if self.topic_worker and self.topic_worker.isRunning():
            out.append("topic discovery")
        if self.preview_worker and self.preview_worker.isRunning():
            out.append("preview")
        if self.storyboard_worker and self.storyboard_worker.isRunning():
            out.append("storyboard preview")
        return out

    def _clear_all_data(self) -> None:
        """
        Wipe local app state: settings, downloaded models, cache, and generated outputs.
        """
        reply = QMessageBox.question(
            self,
            "Clear all data?",
            "This will delete:\n\n"
            "- ui_settings.json (all saved settings)\n"
            "- models/ (downloaded models)\n"
            "- data/news_cache/ (topic cache)\n"
            "- .cache/ (ffmpeg + other caches)\n"
            "- runs/ and videos/ (generated outputs)\n\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Stop download thread first so we can delete models/ without WinError 32 on partial files.
        try:
            if self.download_worker and self.download_worker.isRunning():
                self.download_worker.cancel()
                self.download_worker.wait(3000)
        except Exception:
            pass
        if self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(
                self,
                "Clear data",
                "The model download thread is still stopping. Wait a few seconds and try Clear again.",
            )
            return

        busy = self._busy_background_jobs()
        if busy:
            QMessageBox.warning(
                self,
                "Clear data",
                "Stop these before clearing data (they may lock files under this project):\n\n- "
                + "\n- ".join(busy)
                + "\n\nIf nothing is running, restart the app and try again.",
            )
            return
        try:
            if self._download_popup is not None:
                self._download_popup.close()
        except Exception:
            pass

        self._paused_download_repo_ids = None
        self._paused_download_title = None

        # Best-effort deletes; leave directories recreated.
        errors: list[str] = []

        # Settings file (repo root)
        uerr = unlink_file(settings_path())
        if uerr:
            errors.append(uerr)

        # Models, caches, and outputs (Windows: readonly bits + short lock retries)
        for folder in (
            self.paths.models_dir,
            self.paths.news_cache_dir,
            self.paths.cache_dir,
            self.paths.runs_dir,
            self.paths.videos_dir,
        ):
            rerr = rmtree_robust(folder)
            if rerr:
                errors.append(rerr)

        # Recreate required folders so subsequent operations don't crash.
        try:
            self.paths.models_dir.mkdir(parents=True, exist_ok=True)
            self.paths.news_cache_dir.mkdir(parents=True, exist_ok=True)
            self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
            self.paths.runs_dir.mkdir(parents=True, exist_ok=True)
            self.paths.videos_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        # Reset to defaults and persist (fresh ui_settings.json).
        self.settings = AppSettings()
        try:
            save_settings(self.settings)
        except Exception:
            pass

        if errors:
            tip = (
                "\n\nTip: Close any Explorer windows inside this repo, pause antivirus for the folder, "
                "wait a few seconds, then try Clear again."
            )
            QMessageBox.warning(self, "Clear data finished (with errors)", "\n".join(errors) + tip)
        else:
            QMessageBox.information(self, "Clear data finished", "All local data was cleared. Restart the app for a clean slate.")

        if hasattr(self, "personality_combo") and hasattr(self, "personality_hint"):
            self._update_personality_hint()

        self._resize_to_current_tab()

    def _resize_to_current_tab(self) -> None:
        """
        Keep window non-resizable, but adjust fixed height to current tab contents.
        """
        page = self.tabs.currentWidget()
        if page is None:
            return

        # Base: title bar + optional offline banner + tab bar + current page content.
        title_h = self._title_bar.sizeHint().height() if hasattr(self, "_title_bar") else 40
        banner_h = 0
        if hasattr(self, "_network_banner") and self._network_banner.isVisible():
            banner_h = int(self._network_banner.sizeHint().height()) + 8
        tabbar_h = self.tabs.tabBar().sizeHint().height()
        lay = page.layout()
        if lay is not None:
            page_h = int(lay.sizeHint().height())
        else:
            page_h = int(page.sizeHint().height())

        # Layout margins (top+bottom) + small padding inside tab pane.
        h = int(title_h + banner_h + tabbar_h + page_h + 10 + 10 + 48)

        # Clamp so it doesn't get too tiny or exceed the screen.
        min_h = 360
        max_h = 980
        h = max(min_h, min(max_h, int(h)))
        self.setFixedSize(self.width(), h)

    def _on_tab_changed(self, idx: int) -> None:
        self._resize_to_current_tab()
        self._update_hf_api_warnings()
        try:
            if self.tabs.tabText(idx) == "Run":
                self._refresh_character_combo()
            if self.tabs.tabText(idx) == "Characters" and hasattr(self, "_characters_refresh_elevenlabs"):
                self._characters_refresh_elevenlabs()
        except Exception:
            pass

    def _refresh_character_combo(self) -> None:
        if not hasattr(self, "character_combo"):
            return
        from src.characters_store import load_all

        cur = self.character_combo.currentData()
        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        self.character_combo.addItem("(None)", "")
        try:
            for ch in load_all():
                self.character_combo.addItem(ch.name, ch.id)
        except Exception:
            pass
        idx = self.character_combo.findData(cur)
        self.character_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.character_combo.blockSignals(False)

    def _on_internet_status(self, online: bool) -> None:
        self._internet_online = online
        if hasattr(self, "_network_banner"):
            self._network_banner.setVisible(not online)
        self._resize_to_current_tab()

    def _maybe_log_offline_notice(self) -> None:
        if getattr(self, "_internet_online", None) is False:
            self._append_log(
                "Offline: news fetch and new downloads need the internet; local models on disk can still run."
            )

    def _update_personality_hint(self) -> None:
        if not hasattr(self, "personality_combo") or not hasattr(self, "personality_hint"):
            return
        pid = str(self.personality_combo.currentData() or "auto")
        if pid == "auto":
            self.personality_hint.setText("Auto: will choose based on headlines + topic tags.")
        else:
            p = get_personality_by_id(pid)
            self.personality_hint.setText(f"Selected: {p.label}")
        self._resize_to_current_tab()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            # Store offset between cursor and window top-left
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _append_log(self, line: str) -> None:
        msg = line.rstrip()
        if hasattr(self, "log_box"):
            try:
                self.log_box.append(msg)
                return
            except Exception:
                pass
        print(msg)

    def _ensure_topic_modes(self) -> None:
        d = self.settings.topic_tags_by_mode
        for m in VIDEO_FORMATS:
            if m not in d:
                d[m] = []

    def _topics_bucket_key(self) -> str:
        if hasattr(self, "topics_mode_combo"):
            return normalize_video_format(str(self.topics_mode_combo.currentData() or "news"))
        return normalize_video_format(str(getattr(self.settings, "video_format", "news")))

    def _flush_topic_list_to_mode(self, mode: str) -> None:
        if not hasattr(self, "tag_list"):
            return
        mode = normalize_video_format(mode)
        tags: list[str] = []
        for i in range(self.tag_list.count()):
            it = self.tag_list.item(i)
            if it is None:
                continue
            t = it.text().strip()
            if t:
                tags.append(t)
        self._ensure_topic_modes()
        self.settings.topic_tags_by_mode[mode] = tags

    def _on_topics_mode_changed(self, _idx: int) -> None:
        if not hasattr(self, "topics_mode_combo"):
            return
        old = getattr(self, "_last_topics_mode", None)
        new = normalize_video_format(str(self.topics_mode_combo.currentData() or "news"))
        if old is not None and old != new:
            self._flush_topic_list_to_mode(old)
        self._last_topics_mode = new
        self._sync_tags_to_ui()
        self._update_discover_for_topic_mode()

    def _update_discover_for_topic_mode(self) -> None:
        if not hasattr(self, "discover_btn"):
            return
        self.discover_btn.setEnabled(True)
        mode = self._topics_bucket_key()
        self.discover_btn.setToolTip(
            f'Discover: fetch headlines biased by your "{mode}" tag list; approved phrases are added to this list.'
        )

    def _sync_tags_to_ui(self) -> None:
        from PyQt6.QtWidgets import QListWidgetItem

        if not hasattr(self, "tag_list"):
            return
        self._ensure_topic_modes()
        self.tag_list.clear()
        key = self._topics_bucket_key()
        for t in self.settings.topic_tags_by_mode.get(key, []):
            self.tag_list.addItem(QListWidgetItem(t))

    def _add_tag(self) -> None:
        self._ensure_topic_modes()
        t = " ".join(self.tag_input.text().split()).strip()
        if not t:
            return
        key = self._topics_bucket_key()
        bucket = self.settings.topic_tags_by_mode.setdefault(key, [])
        if t not in bucket:
            bucket.append(t)
            self._sync_tags_to_ui()
        self.tag_input.clear()

    def _remove_selected_tags(self) -> None:
        selected = self.tag_list.selectedItems()
        if not selected:
            return
        self._ensure_topic_modes()
        remove = {it.text() for it in selected}
        key = self._topics_bucket_key()
        bucket = self.settings.topic_tags_by_mode.setdefault(key, [])
        self.settings.topic_tags_by_mode[key] = [x for x in bucket if x not in remove]
        self._sync_tags_to_ui()

    def _clear_tags(self) -> None:
        self._ensure_topic_modes()
        key = self._topics_bucket_key()
        self.settings.topic_tags_by_mode[key] = []
        self._sync_tags_to_ui()

    def _discover_topics(self) -> None:
        if self.topic_worker and self.topic_worker.isRunning():
            return
        self._maybe_log_offline_notice()
        self._topic_discover_target_mode = self._topics_bucket_key()
        if hasattr(self, "discover_btn"):
            try:
                self.discover_btn.setEnabled(False)
                self.discover_btn.setText("Discovering…")
            except Exception:
                pass
        self.topic_worker = TopicDiscoverWorker(
            settings=self._collect_settings_from_ui(),
            limit=12,
            topic_mode=self._topic_discover_target_mode,
        )
        self.topic_worker.done.connect(self._on_topics_discovered)
        self.topic_worker.failed.connect(self._on_topics_failed)
        self.topic_worker.start()

    def _on_topics_discovered(self, topics: list[str]) -> None:
        if hasattr(self, "discover_btn"):
            try:
                self.discover_btn.setText("Discover")
            except Exception:
                pass
            self._update_discover_for_topic_mode()
        topics = [t for t in (topics or []) if isinstance(t, str)]
        if not topics:
            if hasattr(self, "_no_topics_dialog"):
                self._no_topics_dialog(self)
            return

        if hasattr(self, "_pick_topics_dialog"):
            picked = self._pick_topics_dialog(self, topics)
        else:
            picked = topics

        if not picked:
            self._append_log("Topic discovery cancelled.")
            return

        self._ensure_topic_modes()
        key = normalize_video_format(
            str(
                getattr(self, "_topic_discover_target_mode", None)
                or self._topics_bucket_key()
            )
        )
        bucket = self.settings.topic_tags_by_mode.setdefault(key, [])
        added = 0
        for t in picked:
            t = " ".join(t.split()).strip()
            if not t:
                continue
            if t not in bucket:
                bucket.append(t)
                added += 1
        self._sync_tags_to_ui()
        self._save_settings()
        self._append_log(f"Added {added} topic tag(s) to {key}.")

    def _on_topics_failed(self, err: str) -> None:
        if hasattr(self, "discover_btn"):
            try:
                self.discover_btn.setText("Discover")
            except Exception:
                pass
            self._update_discover_for_topic_mode()
        if hasattr(self, "_no_topics_dialog"):
            self._no_topics_dialog(self)
        else:
            self._append_log("Topic discovery failed:")
            self._append_log(err)

    def _collect_settings_from_ui(self) -> AppSettings:
        if hasattr(self, "topics_mode_combo"):
            self._flush_topic_list_to_mode(str(self.topics_mode_combo.currentData() or "news"))

        fmt = (self.settings.video.width, self.settings.video.height)
        if hasattr(self, "format_combo"):
            try:
                d = self.format_combo.currentData()
                if isinstance(d, tuple) and len(d) == 2:
                    fmt = (int(d[0]), int(d[1]))
            except Exception:
                pass

        video = VideoSettings(
            width=int(fmt[0]),
            height=int(fmt[1]),
            fps=int(self.fps_spin.value()),
            microclip_min_s=float(self.min_clip_spin.value()),
            microclip_max_s=float(self.max_clip_spin.value()),
            music_volume=self.settings.video.music_volume,
            voice_volume=self.settings.video.voice_volume,
            images_per_video=int(self.images_spin.value()),
            export_microclips=bool(self.export_microclips_chk.isChecked()),
            bitrate_preset=self.bitrate_combo.currentText(),  # type: ignore[arg-type]
            use_image_slideshow=bool(self.use_slideshow_chk.isChecked()) if hasattr(self, "use_slideshow_chk") else True,
            clips_per_video=int(self.clips_spin.value()) if hasattr(self, "clips_spin") else 3,
            clip_seconds=float(self.clip_seconds_spin.value()) if hasattr(self, "clip_seconds_spin") else 4.0,
            cleanup_images_after_run=bool(self.cleanup_images_chk.isChecked()) if hasattr(self, "cleanup_images_chk") else False,
            high_quality_topic_selection=bool(self.hq_topics_chk.isChecked()) if hasattr(self, "hq_topics_chk") else True,
            fetch_article_text=bool(self.fetch_article_chk.isChecked()) if hasattr(self, "fetch_article_chk") else True,
            llm_factcheck=bool(self.factcheck_chk.isChecked()) if hasattr(self, "factcheck_chk") else True,
            prompt_conditioning=bool(self.prompt_cond_chk.isChecked()) if hasattr(self, "prompt_cond_chk") else True,
            seed_base=int(str(self.seed_base_input.text()).strip())
            if hasattr(self, "seed_base_input") and str(self.seed_base_input.text()).strip().lstrip("-").isdigit()
            else None,
            quality_retries=int(self.quality_retries_spin.value()) if hasattr(self, "quality_retries_spin") else 2,
            enable_motion=bool(self.enable_motion_chk.isChecked()) if hasattr(self, "enable_motion_chk") else True,
            transition_strength=str(self.transition_combo.currentData() or "low") if hasattr(self, "transition_combo") else "low",
            audio_polish=str(self.audio_polish_combo.currentData() or "basic") if hasattr(self, "audio_polish_combo") else "basic",
            music_ducking=bool(self.music_ducking_chk.isChecked()) if hasattr(self, "music_ducking_chk") else True,
            music_ducking_amount=float(self.ducking_spin.value()) / 100.0 if hasattr(self, "ducking_spin") else float(getattr(self.settings.video, "music_ducking_amount", 0.7)),
            music_fade_s=float(self.music_fade_spin.value()) if hasattr(self, "music_fade_spin") else 1.2,
            sfx_mode=str(self.sfx_combo.currentData() or "off") if hasattr(self, "sfx_combo") else "off",
            captions_enabled=bool(self.captions_enabled_chk.isChecked()) if hasattr(self, "captions_enabled_chk") else True,
            caption_highlight_intensity=str(self.caption_highlight_combo.currentData() or "strong")
            if hasattr(self, "caption_highlight_combo")
            else "strong",
            caption_max_words=int(self.caption_max_words_spin.value()) if hasattr(self, "caption_max_words_spin") else 8,
            facts_card_enabled=bool(self.facts_card_chk.isChecked()) if hasattr(self, "facts_card_chk") else True,
            facts_card_position=str(self.facts_card_pos_combo.currentData() or "top_left")
            if hasattr(self, "facts_card_pos_combo")
            else "top_left",
            facts_card_duration=str(self.facts_card_dur_combo.currentData() or "short")
            if hasattr(self, "facts_card_dur_combo")
            else "short",
        )

        branding = getattr(self.settings, "branding", BrandingSettings())
        if hasattr(self, "brand_theme_enable") and hasattr(self, "brand_palette_combo"):
            try:
                branding = BrandingSettings(
                    theme_enabled=bool(self.brand_theme_enable.isChecked()),
                    palette_id=str(self.brand_palette_combo.currentData() or "default"),
                    bg_enabled=bool(self.brand_bg_chk.isChecked()) if hasattr(self, "brand_bg_chk") else False,
                    bg_hex=str(self.brand_bg_hex.text()).strip() if hasattr(self, "brand_bg_hex") else branding.bg_hex,
                    panel_enabled=bool(self.brand_panel_chk.isChecked()) if hasattr(self, "brand_panel_chk") else False,
                    panel_hex=str(self.brand_panel_hex.text()).strip() if hasattr(self, "brand_panel_hex") else branding.panel_hex,
                    text_enabled=bool(self.brand_text_chk.isChecked()) if hasattr(self, "brand_text_chk") else False,
                    text_hex=str(self.brand_text_hex.text()).strip() if hasattr(self, "brand_text_hex") else branding.text_hex,
                    muted_enabled=bool(self.brand_muted_chk.isChecked()) if hasattr(self, "brand_muted_chk") else False,
                    muted_hex=str(self.brand_muted_hex.text()).strip() if hasattr(self, "brand_muted_hex") else branding.muted_hex,
                    accent_enabled=bool(self.brand_accent_chk.isChecked()) if hasattr(self, "brand_accent_chk") else False,
                    accent_hex=str(self.brand_accent_hex.text()).strip() if hasattr(self, "brand_accent_hex") else branding.accent_hex,
                    danger_enabled=bool(self.brand_danger_chk.isChecked()) if hasattr(self, "brand_danger_chk") else False,
                    danger_hex=str(self.brand_danger_hex.text()).strip() if hasattr(self, "brand_danger_hex") else branding.danger_hex,
                    watermark_enabled=bool(self.brand_watermark_enable.isChecked())
                    if hasattr(self, "brand_watermark_enable")
                    else bool(getattr(branding, "watermark_enabled", False)),
                    watermark_path=str(self.brand_watermark_path.text()).strip()
                    if hasattr(self, "brand_watermark_path")
                    else str(getattr(branding, "watermark_path", "")),
                    watermark_opacity=float(self.brand_watermark_opacity.value()) / 100.0
                    if hasattr(self, "brand_watermark_opacity")
                    else float(getattr(branding, "watermark_opacity", 0.22)),
                    watermark_scale=float(self.brand_watermark_scale.value()) / 100.0
                    if hasattr(self, "brand_watermark_scale")
                    else float(getattr(branding, "watermark_scale", 0.18)),
                    watermark_position=str(self.brand_watermark_pos.currentData() or "top_right")
                    if hasattr(self, "brand_watermark_pos")
                    else str(getattr(branding, "watermark_position", "top_right")),
                    video_style_enabled=bool(self.brand_video_style_enable.isChecked())
                    if hasattr(self, "brand_video_style_enable")
                    else bool(getattr(branding, "video_style_enabled", False)),
                    video_style_strength=str(self.brand_video_style_strength.currentData() or "subtle")
                    if hasattr(self, "brand_video_style_strength")
                    else str(getattr(branding, "video_style_strength", "subtle")),
                )
            except Exception:
                branding = getattr(self.settings, "branding", BrandingSettings())

        # Video/images selection can be either a simple repo_id (images or text→vid),
        # or a paired selection: (image_repo_id, video_repo_id) for img→vid pipelines.
        img_data = self.img_combo.currentData() if hasattr(self, "img_combo") else self.settings.image_model_id
        image_model_id = self.settings.image_model_id
        video_model_id = self.settings.video_model_id if hasattr(self.settings, "video_model_id") else ""
        if isinstance(img_data, tuple) and len(img_data) == 2:
            image_model_id = str(img_data[0])
            video_model_id = str(img_data[1])
        else:
            image_model_id = str(img_data)
            video_model_id = ""

        hf_tok = (
            str(self.api_hf_token_edit.text()).strip()
            if hasattr(self, "api_hf_token_edit")
            else str(getattr(self.settings, "hf_token", "") or "")
        )
        hf_en = (
            bool(self.api_hf_enabled_chk.isChecked())
            if hasattr(self, "api_hf_enabled_chk")
            else bool(getattr(self.settings, "hf_api_enabled", True))
        )
        fc_en = (
            bool(self.api_fc_enabled_chk.isChecked())
            if hasattr(self, "api_fc_enabled_chk")
            else bool(getattr(self.settings, "firecrawl_enabled", False))
        )
        fc_key = (
            str(self.api_fc_key_edit.text()).strip()
            if hasattr(self, "api_fc_key_edit")
            else str(getattr(self.settings, "firecrawl_api_key", "") or "")
        )
        el_en = (
            bool(self.api_el_enabled_chk.isChecked())
            if hasattr(self, "api_el_enabled_chk")
            else bool(getattr(self.settings, "elevenlabs_enabled", False))
        )
        el_key = (
            str(self.api_el_key_edit.text()).strip()
            if hasattr(self, "api_el_key_edit")
            else str(getattr(self.settings, "elevenlabs_api_key", "") or "")
        )

        tt_en = bool(self.api_tt_enabled_chk.isChecked()) if hasattr(self, "api_tt_enabled_chk") else bool(getattr(self.settings, "tiktok_enabled", False))
        tt_ck = str(self.api_tt_client_key.text()).strip() if hasattr(self, "api_tt_client_key") else str(getattr(self.settings, "tiktok_client_key", "") or "")
        tt_cs = str(self.api_tt_client_secret.text()).strip() if hasattr(self, "api_tt_client_secret") else str(getattr(self.settings, "tiktok_client_secret", "") or "")
        tt_ru = str(self.api_tt_redirect_uri.text()).strip() if hasattr(self, "api_tt_redirect_uri") else str(getattr(self.settings, "tiktok_redirect_uri", "") or "")
        tt_port = int(self.api_tt_oauth_port.value()) if hasattr(self, "api_tt_oauth_port") else int(getattr(self.settings, "tiktok_oauth_port", 8765))
        tt_at = str(self.settings.tiktok_access_token or "")  # refreshed via worker / OAuth only
        tt_rt = str(self.settings.tiktok_refresh_token or "")
        tt_exp = float(getattr(self.settings, "tiktok_token_expires_at", 0.0) or 0.0)
        tt_oid = str(getattr(self.settings, "tiktok_open_id", "") or "")
        tt_mode = (
            str(self.api_tt_pub_mode.currentData() or "inbox") if hasattr(self, "api_tt_pub_mode") else str(getattr(self.settings, "tiktok_publishing_mode", "inbox"))
        )
        if tt_mode not in ("inbox", "direct"):
            tt_mode = "inbox"
        tt_auto = bool(self.api_tt_auto_upload_chk.isChecked()) if hasattr(self, "api_tt_auto_upload_chk") else bool(getattr(self.settings, "tiktok_auto_upload_after_render", False))

        yt_en = bool(self.api_yt_enabled_chk.isChecked()) if hasattr(self, "api_yt_enabled_chk") else bool(getattr(self.settings, "youtube_enabled", False))
        yt_cid = str(self.api_yt_client_id.text()).strip() if hasattr(self, "api_yt_client_id") else str(getattr(self.settings, "youtube_client_id", "") or "")
        yt_sec = str(self.api_yt_client_secret.text()).strip() if hasattr(self, "api_yt_client_secret") else str(getattr(self.settings, "youtube_client_secret", "") or "")
        yt_ru = str(self.api_yt_redirect_uri.text()).strip() if hasattr(self, "api_yt_redirect_uri") else str(getattr(self.settings, "youtube_redirect_uri", "") or "")
        yt_port = int(self.api_yt_oauth_port.value()) if hasattr(self, "api_yt_oauth_port") else int(getattr(self.settings, "youtube_oauth_port", 8888))
        yt_at = str(self.settings.youtube_access_token or "")
        yt_rt = str(self.settings.youtube_refresh_token or "")
        yt_exp = float(getattr(self.settings, "youtube_token_expires_at", 0.0) or 0.0)
        yt_priv = (
            str(self.api_yt_privacy.currentData() or "private") if hasattr(self, "api_yt_privacy") else str(getattr(self.settings, "youtube_privacy_status", "private"))
        )
        if yt_priv not in ("public", "unlisted", "private"):
            yt_priv = "private"
        yt_shorts_tag = bool(self.api_yt_shorts_tag_chk.isChecked()) if hasattr(self, "api_yt_shorts_tag_chk") else bool(getattr(self.settings, "youtube_add_shorts_hashtag", True))
        yt_auto = bool(self.api_yt_auto_upload_chk.isChecked()) if hasattr(self, "api_yt_auto_upload_chk") else bool(getattr(self.settings, "youtube_auto_upload_after_render", False))

        vfmt = (
            normalize_video_format(str(self.video_format_combo.currentData() or "news"))
            if hasattr(self, "video_format_combo")
            else normalize_video_format(str(getattr(self.settings, "video_format", "news")))
        )
        topic_map = {str(k): list(v) for k, v in (self.settings.topic_tags_by_mode or {}).items()}

        return AppSettings(
            topic_tags_by_mode=topic_map,
            video_format=vfmt,
            prefer_gpu=bool(self.prefer_gpu_chk.isChecked()),
            try_llm_4bit=bool(self.try_llm_chk.isChecked()),
            try_sdxl_turbo=bool(self.try_sdxl_chk.isChecked()),
            background_music_path=str(self.music_path.text()).strip(),
            hf_token=hf_tok,
            hf_api_enabled=hf_en,
            firecrawl_enabled=fc_en,
            firecrawl_api_key=fc_key,
            elevenlabs_enabled=el_en,
            elevenlabs_api_key=el_key,
            tiktok_enabled=tt_en,
            tiktok_client_key=tt_ck,
            tiktok_client_secret=tt_cs,
            tiktok_redirect_uri=tt_ru or "http://127.0.0.1:8765/callback/",
            tiktok_oauth_port=tt_port,
            tiktok_access_token=tt_at,
            tiktok_refresh_token=tt_rt,
            tiktok_token_expires_at=tt_exp,
            tiktok_open_id=tt_oid,
            tiktok_publishing_mode=tt_mode,  # type: ignore[arg-type]
            tiktok_auto_upload_after_render=tt_auto,
            youtube_enabled=yt_en,
            youtube_client_id=yt_cid,
            youtube_client_secret=yt_sec,
            youtube_redirect_uri=yt_ru or "http://127.0.0.1:8888/callback/",
            youtube_oauth_port=yt_port,
            youtube_access_token=yt_at,
            youtube_refresh_token=yt_rt,
            youtube_token_expires_at=yt_exp,
            youtube_privacy_status=yt_priv,  # type: ignore[arg-type]
            youtube_add_shorts_hashtag=yt_shorts_tag,
            youtube_auto_upload_after_render=yt_auto,
            personality_id=str(self.personality_combo.currentData()) if hasattr(self, "personality_combo") else getattr(self.settings, "personality_id", "auto"),
            active_character_id=str(self.character_combo.currentData()) if hasattr(self, "character_combo") else str(getattr(self.settings, "active_character_id", "") or ""),
            llm_model_id=str(self.llm_combo.currentData()) if hasattr(self, "llm_combo") else self.settings.llm_model_id,
            image_model_id=image_model_id,
            video_model_id=video_model_id,
            voice_model_id=str(self.voice_combo.currentData()) if hasattr(self, "voice_combo") else self.settings.voice_model_id,
            video=video,
            branding=branding,
        )

    def _save_settings(self) -> None:
        self.settings = self._collect_settings_from_ui()
        save_settings(self.settings)
        self._apply_hf_token_from_current_settings()
        self._update_hf_api_warnings()
        self._append_log("Saved settings.")

    def _open_videos(self) -> None:
        self.paths.videos_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.videos_dir)))

    def _pick_music(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select background music", "", "Audio Files (*.mp3 *.wav *.m4a);;All Files (*)"
        )
        if path:
            self.music_path.setText(path)

    def _clear_seen_cache(self) -> None:
        d = self.paths.news_cache_dir
        try:
            removed = clear_news_seen_cache_files(d)
            if removed:
                self._append_log(f"Cleared news URL/title cache ({removed} file(s)).")
        except Exception as e:
            self._append_log(f"Failed to clear cache: {e}")

    def _check_deps(self) -> None:
        mods = [
            "requests",
            "bs4",
            "lxml",
            "torch",
            "transformers",
            "accelerate",
            "bitsandbytes",
            "diffusers",
            "huggingface_hub",
            "moviepy",
            "PIL",
            "numpy",
            "soundfile",
            "pyttsx3",
            "PyQt6",
        ]
        missing = []
        for m in mods:
            try:
                __import__(m)
            except Exception:
                missing.append(m)
        msg = ("Missing imports:\n- " + "\n- ".join(missing)) if missing else "All core imports are available."
        if hasattr(self, "deps_status"):
            try:
                self.deps_status.setPlainText(msg)
                return
            except Exception:
                pass
        self._append_log(msg)

    def _install_deps(self) -> None:
        req = project_root() / "requirements.txt"
        if not req.exists():
            if hasattr(self, "deps_status"):
                try:
                    self.deps_status.setPlainText("requirements.txt not found.")
                    return
                except Exception:
                    pass
            self._append_log("requirements.txt not found.")
            return
        self._append_log("Installing dependencies (pip -r requirements.txt)…")
        try:
            p = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req)],
                capture_output=True,
                text=True,
            )
            out = (p.stdout or "") + "\n" + (p.stderr or "")
            if hasattr(self, "deps_status"):
                try:
                    self.deps_status.setPlainText(out)
                except Exception:
                    self._append_log(out)
            else:
                self._append_log(out)
            self._append_log("Dependency install finished.")
        except Exception as e:
            if hasattr(self, "deps_status"):
                try:
                    self.deps_status.setPlainText(f"Install failed: {e}")
                    return
                except Exception:
                    pass
            self._append_log(f"Install failed: {e}")

    def _repos_still_need_download(self, repo_ids: list[str]) -> tuple[list[str], list[str]]:
        """
        Returns (repos_missing_on_disk, repos_already_present), de-duplicated in order.
        """
        need: list[str] = []
        have: list[str] = []
        seen: set[str] = set()
        models_dir = self.paths.models_dir
        for r in repo_ids:
            r = str(r).strip()
            if not r or r in seen:
                continue
            seen.add(r)
            if model_has_local_snapshot(r, models_dir=models_dir):
                have.append(r)
            else:
                need.append(r)
        return need, have

    def _download_selected(self, kind: str) -> None:
        if kind == "script":
            repo_ids = [str(self.llm_combo.currentData())]
        elif kind == "video":
            d = self.img_combo.currentData()
            if isinstance(d, tuple) and len(d) == 2:
                repo_ids = [str(d[0]), str(d[1])]
            else:
                repo_ids = [str(d)]
        else:
            repo_ids = [str(self.voice_combo.currentData())]
        repo_ids = [r for r in repo_ids if r and str(r).strip()]
        if not repo_ids:
            return
        need, have = self._repos_still_need_download(repo_ids)
        if have:
            preview = ", ".join(have[:4])
            if len(have) > 4:
                preview += f", … (+{len(have) - 4} more)"
            self._append_log(f"Skipping {len(have)} already downloaded: {preview}")
        if not need:
            self._append_log("Nothing to download — selected model(s) are already on disk.")
            return
        self._start_download(need, title="Downloading model")

    def _download_all_selected(self) -> None:
        repo_ids: list[str] = [str(self.llm_combo.currentData())]
        img_d = self.img_combo.currentData()
        if isinstance(img_d, tuple) and len(img_d) == 2:
            repo_ids.extend([str(img_d[0]), str(img_d[1])])
        else:
            repo_ids.append(str(img_d))
        repo_ids.append(str(self.voice_combo.currentData()))
        seen: set[str] = set()
        deduped: list[str] = []
        for r in repo_ids:
            r = str(r).strip()
            if not r or r in seen:
                continue
            seen.add(r)
            deduped.append(r)
        need, have = self._repos_still_need_download(deduped)
        if have:
            preview = ", ".join(have[:4])
            if len(have) > 4:
                preview += f", … (+{len(have) - 4} more)"
            self._append_log(f"Skipping {len(have)} already downloaded: {preview}")
        if not need:
            self._append_log("All selected models are already on disk — nothing to download.")
            return
        self._start_download(need, title="Downloading selected models")

    def _download_all_models(self) -> None:
        """
        Downloads every curated model option into the project `models/` folder.
        """
        if not hasattr(self, "_model_opts") or not self._model_opts:
            self._append_log("No model options loaded yet.")
            return
        repo_ids = []
        seen = set()
        for opt in self._model_opts:
            rid = str(opt.repo_id).strip()
            if not rid or rid in seen:
                continue
            seen.add(rid)
            repo_ids.append(rid)

        need, have = self._repos_still_need_download(repo_ids)
        if have:
            self._append_log(f"Skipping {len(have)} model(s) already on disk (download-all queue).")
        if not need:
            self._append_log("All curated models are already on disk.")
            return
        self._start_download(need, title=f"Downloading ALL models ({len(need)} remaining)")

    def _repos_selected_installed_only(self) -> list[str]:
        """Current LLM / image / voice selections, de-duplicated, only repos with a local snapshot."""
        if not hasattr(self, "llm_combo"):
            return []
        repo_ids: list[str] = [str(self.llm_combo.currentData())]
        img_d = self.img_combo.currentData()
        if isinstance(img_d, tuple) and len(img_d) == 2:
            repo_ids.extend([str(img_d[0]), str(img_d[1])])
        else:
            repo_ids.append(str(img_d))
        repo_ids.append(str(self.voice_combo.currentData()))
        seen: set[str] = set()
        out: list[str] = []
        for r in repo_ids:
            r = str(r).strip()
            if not r or r in seen:
                continue
            seen.add(r)
            out.append(r)
        models_dir = self.paths.models_dir
        return [r for r in out if model_has_local_snapshot(r, models_dir=models_dir)]

    def _verify_models_checksums_selected(self) -> None:
        repo_ids = self._repos_selected_installed_only()
        self._start_integrity_verify(repo_ids, scope_label="selected models")

    def _verify_models_checksums_all(self) -> None:
        repo_ids = list_installed_repo_ids_from_disk(self.paths.models_dir)
        self._start_integrity_verify(repo_ids, scope_label="all folders in models/")

    def _start_integrity_verify(self, repo_ids: list[str], *, scope_label: str) -> None:
        if self._integrity_worker and self._integrity_worker.isRunning():
            self._append_log("A checksum verification run is already in progress.")
            return
        if not repo_ids:
            self._append_log(
                "No installed model snapshots to verify. "
                "Download a model first, or pick folders that exist under models/."
            )
            return
        self._append_log(
            "Verifying local files against Hugging Face (SHA-256 / git blob ids). "
            "Large models can take several minutes."
        )
        self._integrity_worker = ModelIntegrityVerifyWorker(
            repo_ids=repo_ids,
            models_dir=self.paths.models_dir,
            scope_label=scope_label,
        )

        def _on_prog(rid: str, msg: str) -> None:
            self._append_log(f"{msg} {rid}")

        self._integrity_worker.progress.connect(_on_prog)
        self._integrity_worker.done.connect(self._on_integrity_verify_done)
        self._integrity_worker.failed.connect(self._on_integrity_verify_failed)
        self._integrity_worker.start()

    def _on_integrity_verify_done(self, text: str) -> None:
        self._append_log(text)
        self._integrity_worker = None

    def _on_integrity_verify_failed(self, err: str) -> None:
        self._append_log("Model integrity check failed:")
        self._append_log(err)
        self._integrity_worker = None

    def _start_download(self, repo_ids: list[str], *, title: str) -> None:
        if self.download_worker and self.download_worker.isRunning():
            return
        repo_ids = [r for r in repo_ids if r and r.strip()]
        if not repo_ids:
            return
        dprint("ui", "_start_download", title, f"repos={len(repo_ids)}")

        # Resume if we have a paused queue that matches this request (common case: click Download again).
        if self._paused_download_repo_ids:
            paused_remaining = [r for r in (self._paused_download_repo_ids or []) if r and r.strip()]
            requested = set(repo_ids)
            if paused_remaining and set(paused_remaining).issubset(requested):
                repo_ids = paused_remaining
                title = self._paused_download_title or "Resuming download"

        popup = DownloadPopup(self, title=title)
        self._download_popup = popup

        remote_sizes = dict(getattr(self, "_hf_remote_sizes", None) or {})
        self.download_worker = ModelDownloadWorker(
            repo_ids=repo_ids,
            models_dir=self.paths.models_dir,
            title=title,
            remote_bytes_by_repo=remote_sizes,
        )

        # If user closes the popup, cancel the background worker so app can exit cleanly.
        popup.cancel_requested.connect(lambda: self.download_worker.cancel() if self.download_worker else None)

        def _pause_download() -> None:
            if not self.download_worker:
                return

            # Compute remaining list (include current repo_id because it may be partial).
            remaining: list[str] = []
            try:
                idx = int(getattr(self.download_worker, "current_index", 0) or 0)
                cur = str(getattr(self.download_worker, "current_repo_id", "") or "").strip()
                all_ids = list(getattr(self.download_worker, "repo_ids", []) or [])
                if idx <= 0:
                    remaining = [str(r) for r in all_ids if str(r).strip()]
                else:
                    tail = [str(r) for r in all_ids[idx:] if str(r).strip()]
                    if cur:
                        remaining = [cur] + tail
                    else:
                        remaining = [str(r) for r in all_ids[idx - 1 :] if str(r).strip()]
            except Exception:
                remaining = [str(r) for r in (repo_ids or []) if str(r).strip()]

            self._paused_download_repo_ids = remaining or None
            self._paused_download_title = title
            self.download_worker.pause()

        popup.pause_requested.connect(_pause_download)

        def on_progress(task_id: str, pct: int, status: str) -> None:
            popup.status.setText(format_status_line(task_id, pct, status))
            popup.bar.setValue(max(0, min(100, int(pct))))

        def on_done(_msg: str) -> None:
            msg = str(_msg or "").strip().lower()
            if "pause" in msg:
                popup.status.setText("Paused. You can close this window and resume later.")
                # Don't force bar to 0; leave last visible state.
            elif "cancel" in msg:
                popup.status.setText("Cancelled. You can resume later.")
                # Don't force bar to 0; leave last visible state.
            else:
                popup.status.setText("Done.")
                popup.bar.setValue(100)
                self._paused_download_repo_ids = None
                self._paused_download_title = None
                try:
                    if hasattr(self, "_refresh_settings_model_combos"):
                        self._refresh_settings_model_combos()
                except Exception:
                    pass
            popup.accept()

        def on_failed(err: str) -> None:
            popup.status.setText("Download failed.")
            popup.bar.setValue(0)
            popup.reject()
            self._append_log(err)

        self.download_worker.progress.connect(on_progress)
        self.download_worker.done.connect(on_done)
        self.download_worker.failed.connect(on_failed)
        self.download_worker.start()

        popup.exec()
        self._download_popup = None

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # Make app exit reliably even if a background download is running.
        try:
            if self.download_worker and self.download_worker.isRunning():
                self.download_worker.cancel()
                # Best-effort: wait briefly so the thread can unwind.
                self.download_worker.wait(1500)
        except Exception:
            pass
        try:
            if self._integrity_worker and self._integrity_worker.isRunning():
                self._integrity_worker.wait(2000)
        except Exception:
            pass
        try:
            if self._ffmpeg_ensure_worker and self._ffmpeg_ensure_worker.isRunning():
                self._ffmpeg_ensure_worker.wait(4000)
        except Exception:
            pass
        try:
            if self._download_popup is not None:
                self._download_popup.close()
        except Exception:
            pass
        return super().closeEvent(event)

    def _run_when_ffmpeg_ready(self, then: Callable[[], None]) -> None:
        """
        If ``.cache/ffmpeg`` has no ``ffmpeg`` yet, download in a background thread, then run ``then``.
        Otherwise call ``then`` immediately.
        """
        if find_ffmpeg(self.paths.ffmpeg_dir):
            then()
            return
        if self._ffmpeg_ensure_worker and self._ffmpeg_ensure_worker.isRunning():
            self._append_log(
                'FFmpeg is still downloading — wait for "FFmpeg is ready" in the log, then click Run again.'
            )
            return
        self._append_log(
            "First-time setup: downloading FFmpeg to .cache/ffmpeg/ (needs internet; may take a few minutes)…"
        )
        self._ffmpeg_run_after = then
        w = FFmpegEnsureWorker(self.paths.ffmpeg_dir)
        self._ffmpeg_ensure_worker = w
        w.finished_ok.connect(self._on_ffmpeg_install_done)
        w.failed.connect(self._on_ffmpeg_install_failed)
        w.start()

    def _on_ffmpeg_install_done(self) -> None:
        self._ffmpeg_ensure_worker = None
        self._append_log("FFmpeg is ready.")
        fn = self._ffmpeg_run_after
        self._ffmpeg_run_after = None
        if fn:
            fn()

    def _on_ffmpeg_install_failed(self, err: str) -> None:
        self._ffmpeg_ensure_worker = None
        self._ffmpeg_run_after = None
        self._append_log("FFmpeg download failed:")
        self._append_log(err[:4000])

    def _on_run(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        dprint("ui", "_on_run")
        self._save_settings()
        self._maybe_log_offline_notice()

        def _continue() -> None:
            pf = preflight_check(settings=self.settings, strict=True)
            for w in pf.warnings:
                self._append_log(f"Warning: {w}")
            if not pf.ok:
                self._append_log("Preflight failed. Fix these issues before running:")
                for e in pf.errors:
                    self._append_log(f"- {e}")
                return

            qty = int(self.run_qty_spin.value()) if hasattr(self, "run_qty_spin") else 1

            self.run_btn.setEnabled(False)

            if qty <= 1:
                self._set_tasks_active_row("Pipeline run", "Running…", folder="In progress")
                self.worker = PipelineWorker(self.settings)
                self.worker.done.connect(lambda out: self._on_done(out))
                self.worker.failed.connect(self._on_failed)
                self.worker.start()
                return

            self._set_tasks_active_row(f"Batch pipeline ({qty} videos)", "Starting…", folder="Queued")
            self.worker = PipelineBatchWorker(self.settings, quantity=qty)

            def on_prog(task_id: str, pct: int, status: str) -> None:
                self._update_tasks_active_progress(task_id, pct, status)
                self._resize_to_current_tab()

            def on_done(msg: str) -> None:
                self._clear_tasks_active_row()
                self.run_btn.setEnabled(True)
                self._append_log(msg)
                self._resize_to_current_tab()

            self.worker.progress.connect(on_prog)
            self.worker.done.connect(on_done)
            self.worker.failed.connect(self._on_failed)
            self.worker.start()

        self._run_when_ffmpeg_ready(_continue)

    def _on_preview(self) -> None:
        if self.preview_worker and self.preview_worker.isRunning():
            return

        dprint("ui", "_on_preview")
        self._save_settings()
        self._maybe_log_offline_notice()
        pf = preflight_check(settings=self.settings, strict=False)
        for w in pf.warnings:
            self._append_log(f"Warning: {w}")

        if hasattr(self, "preview_btn"):
            try:
                self.preview_btn.setEnabled(False)
                self.preview_btn.setText("Previewing…")
            except Exception:
                pass
        self._set_tasks_active_row("Preview script", "Starting…", folder="—")

        self.preview_worker = PreviewWorker(self.settings)

        def on_prog(task_id: str, pct: int, status: str) -> None:
            self._update_tasks_active_progress(task_id, pct, status)
            self._resize_to_current_tab()

        def on_done(pkg, sources, prompts, personality_id: str, confidence: str) -> None:
            self._clear_tasks_active_row()
            if hasattr(self, "preview_btn"):
                try:
                    self.preview_btn.setEnabled(True)
                    self.preview_btn.setText("Preview")
                except Exception:
                    pass
            self._last_preview_pkg = pkg
            self._last_preview_sources = sources
            self._last_preview_prompts = prompts
            self._last_preview_personality_id = str(personality_id or "auto")

            segs = []
            try:
                for s in getattr(pkg, "segments", []) or []:
                    segs.append(
                        {
                            "narration": getattr(s, "narration", ""),
                            "visual_prompt": getattr(s, "visual_prompt", ""),
                            "on_screen_text": getattr(s, "on_screen_text", "") or "",
                        }
                    )
            except Exception:
                segs = []

            dlg = PreviewDialog(
                self,
                title=str(getattr(pkg, "title", "")),
                personality_id=self._last_preview_personality_id,
                confidence=str(confidence or ""),
                hook=str(getattr(pkg, "hook", "")),
                segments=segs,
                cta=str(getattr(pkg, "cta", "")),
                on_regenerate=self._on_preview,
                on_approve_run=self._approve_preview_and_run,
            )
            dlg.exec()

        def on_failed(err: str) -> None:
            self._clear_tasks_active_row()
            if hasattr(self, "preview_btn"):
                try:
                    self.preview_btn.setEnabled(True)
                    self.preview_btn.setText("Preview")
                except Exception:
                    pass
            self._append_log("Preview failed:")
            self._append_log(err)

        self.preview_worker.progress.connect(on_prog)
        self.preview_worker.done.connect(on_done)
        self.preview_worker.failed.connect(on_failed)
        self.preview_worker.start()

    def _approve_preview_and_run(self) -> None:
        """
        Run the pipeline using the last previewed script/storyboard, without re-generating the script.
        """
        if not self._last_preview_pkg:
            return
        if self.worker and self.worker.isRunning():
            return

        self._save_settings()
        self._maybe_log_offline_notice()

        def _continue() -> None:
            pf = preflight_check(settings=self.settings, strict=True)
            for w in pf.warnings:
                self._append_log(f"Warning: {w}")
            if not pf.ok:
                self._append_log("Preflight failed. Fix these issues before running:")
                for e in pf.errors:
                    self._append_log(f"- {e}")
                return

            self.run_btn.setEnabled(False)
            self._set_tasks_active_row("Pipeline run", "Running (approved preview)…", folder="In progress")

            self.worker = PipelineWorker(
                self.settings,
                prebuilt_pkg=self._last_preview_pkg,
                prebuilt_sources=self._last_preview_sources,
                prebuilt_prompts=self._last_preview_prompts,
            )
            self.worker.done.connect(lambda out: self._on_done(out))
            self.worker.failed.connect(self._on_failed)
            self.worker.start()

        self._run_when_ffmpeg_ready(_continue)

    def _regenerate_scene_from_last_run(self) -> None:
        """
        Regenerate a single storyboard scene from the latest video folder manifest, then re-render final.mp4.
        """
        try:
            idx = int(self.regen_scene_spin.value()) if hasattr(self, "regen_scene_spin") else 1
        except Exception:
            idx = 1
        idx = max(1, idx)

        try:
            # Find latest video dir with manifest.json
            vids = list(self.paths.videos_dir.glob("*"))
            vids = [p for p in vids if p.is_dir() and (p / "assets" / "manifest.json").exists()]
            if not vids:
                self._append_log("No manifest.json found yet. Run once to generate a storyboard first.")
                return
            vids.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            video_dir = vids[0]
            manifest = video_dir / "assets" / "manifest.json"

            import json

            m = json.loads(manifest.read_text(encoding="utf-8"))
            scenes = m.get("scenes", []) if isinstance(m, dict) else []
            if not isinstance(scenes, list) or not scenes:
                self._append_log("Manifest has no scenes.")
                return
            if idx > len(scenes):
                self._append_log(f"Scene #{idx} out of range (1..{len(scenes)}).")
                return
            sc = scenes[idx - 1] if isinstance(scenes[idx - 1], dict) else {}
            prompt = str(sc.get("prompt", "")).strip()
            seed = int(sc.get("seed", 0) or 0)
            img_path = str(sc.get("image_path", "")).strip()
            if not prompt or not img_path:
                self._append_log("Manifest missing prompt/image_path for that scene.")
                return

            from pathlib import Path
            from src.artist import generate_images
            from src.editor import assemble_microclips_then_concat
            from src.config import get_paths, get_models

            paths = get_paths()
            models = get_models()
            settings = self._collect_settings_from_ui()
            img_id = settings.image_model_id.strip() or models.sdxl_turbo_id

            out_path = Path(img_path)
            out_dir = out_path.parent
            self._append_log(f"Regenerating scene #{idx}…")
            regen = generate_images(
                sdxl_turbo_model_id=img_id,
                prompts=[prompt],
                out_dir=out_dir,
                max_images=1,
                seeds=[seed + 1],
            )
            if regen:
                try:
                    regen[0].path.replace(out_path)
                except Exception:
                    pass
                sc["seed"] = seed + 1
                sc["image_path"] = str(out_path)
                scenes[idx - 1] = sc
                m["scenes"] = scenes
                manifest.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")

            # Re-render final using current settings, reusing existing voice/captions.
            voice_wav = video_dir / "assets" / "voice.wav"
            captions_json = video_dir / "assets" / "captions.json"
            final_mp4 = video_dir / "final.mp4"
            images = [Path(str(s.get("image_path", ""))) for s in scenes if isinstance(s, dict) and str(s.get("image_path", "")).strip()]
            images = [p for p in images if p.exists()]
            assemble_microclips_then_concat(
                ffmpeg_dir=paths.ffmpeg_dir,
                settings=settings.video,
                images=images,
                voice_wav=voice_wav,
                captions_json=captions_json,
                out_final_mp4=final_mp4,
                out_assets_dir=video_dir / "assets",
                background_music=Path(settings.background_music_path).resolve() if settings.background_music_path else None,
                branding=getattr(settings, "branding", None),
            )
            self._append_log(f"Re-rendered: {final_mp4}")
        except Exception as e:
            self._append_log(f"Regenerate failed: {e}")

    def _on_storyboard_preview(self) -> None:
        if self.storyboard_worker and self.storyboard_worker.isRunning():
            return
        self._save_settings()
        self._maybe_log_offline_notice()
        if hasattr(self, "storyboard_btn"):
            try:
                self.storyboard_btn.setEnabled(False)
                self.storyboard_btn.setText("Storyboard…")
            except Exception:
                pass
        self._set_tasks_active_row("Storyboard preview", "Starting…", folder="—")

        self.storyboard_worker = StoryboardWorker(self.settings)

        def on_prog(task_id: str, pct: int, status: str) -> None:
            self._update_tasks_active_progress(task_id, pct, status)
            self._resize_to_current_tab()

        def on_done(manifest_path, grid_png_path) -> None:
            self._clear_tasks_active_row()
            if hasattr(self, "storyboard_btn"):
                try:
                    self.storyboard_btn.setEnabled(True)
                    self.storyboard_btn.setText("Storyboard Preview")
                except Exception:
                    pass
            self._last_storyboard_manifest = manifest_path
            self._last_storyboard_grid = grid_png_path
            dlg = StoryboardPreviewDialog(
                self,
                manifest_path=manifest_path,
                grid_png_path=grid_png_path,
                on_regenerate_scene=self._storyboard_regenerate_scene,
                on_regenerate_all=self._on_storyboard_preview,
                on_approve_render=self._approve_storyboard_and_render,
            )
            dlg.exec()

        def on_failed(err: str) -> None:
            self._clear_tasks_active_row()
            if hasattr(self, "storyboard_btn"):
                try:
                    self.storyboard_btn.setEnabled(True)
                    self.storyboard_btn.setText("Storyboard Preview")
                except Exception:
                    pass
            self._append_log("Storyboard preview failed:")
            self._append_log(err)

        self.storyboard_worker.progress.connect(on_prog)
        self.storyboard_worker.done.connect(on_done)
        self.storyboard_worker.failed.connect(on_failed)
        self.storyboard_worker.start()

    def _storyboard_regenerate_scene(self, scene_idx: int) -> None:
        """
        Regenerate a scene preview image in the current storyboard manifest and refresh grid.
        """
        import json
        from pathlib import Path

        if not self._last_storyboard_manifest or not self._last_storyboard_grid:
            return
        manifest = Path(str(self._last_storyboard_manifest))
        grid = Path(str(self._last_storyboard_grid))
        if not manifest.exists():
            return

        m = json.loads(manifest.read_text(encoding="utf-8"))
        scenes = m.get("scenes", []) if isinstance(m, dict) else []
        if not isinstance(scenes, list) or not scenes:
            return
        idx = max(1, int(scene_idx))
        if idx > len(scenes):
            return
        sc = scenes[idx - 1] if isinstance(scenes[idx - 1], dict) else {}

        prompt = str(sc.get("prompt", "")).strip()
        seed = int(sc.get("seed", 0) or 0)
        lock = bool(sc.get("lock_seed", False))
        prev_path = str(sc.get("preview_image_path", "")).strip()
        if not prev_path:
            # default preview location
            prev_path = str(manifest.parent / "previews" / f"scene_{idx:02d}.png")
        out_path = Path(prev_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        from src.artist import generate_images
        from src.config import get_models

        models = get_models()
        settings = self._collect_settings_from_ui()
        img_id = settings.image_model_id.strip() or models.sdxl_turbo_id

        new_seed = seed if lock else (seed + 1)
        gen = generate_images(
            sdxl_turbo_model_id=img_id,
            prompts=[prompt],
            out_dir=out_path.parent,
            max_images=1,
            seeds=[new_seed],
            steps=4,
        )
        if gen:
            try:
                gen[0].path.replace(out_path)
            except Exception:
                pass

        sc["seed"] = int(new_seed)
        sc["preview_image_path"] = str(out_path)
        sc["status"] = "regenerated"
        scenes[idx - 1] = sc
        m["scenes"] = scenes
        manifest.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")

        # Rebuild grid
        try:
            from src.storyboard import render_preview_grid

            paths = [Path(str(s.get("preview_image_path", ""))) for s in scenes if isinstance(s, dict)]
            paths = [p for p in paths if p.exists()]
            render_preview_grid(scene_paths=paths, out_grid=grid, cols=4, thumb=256)
        except Exception:
            pass

    def _approve_storyboard_and_render(self) -> None:
        """
        Run the full pipeline using the approved storyboard manifest prompts/seeds.
        """
        import json
        from pathlib import Path

        if not self._last_storyboard_manifest:
            return
        manifest = Path(str(self._last_storyboard_manifest))
        if not manifest.exists():
            return
        m = json.loads(manifest.read_text(encoding="utf-8"))
        scenes = m.get("scenes", []) if isinstance(m, dict) else []
        if not isinstance(scenes, list) or not scenes:
            return

        prompts = [str(s.get("prompt", "")).strip() for s in scenes if isinstance(s, dict)]
        seeds = [int(s.get("seed", 0) or 0) for s in scenes if isinstance(s, dict)]

        # Store for worker run; use PipelineWorker to run_once with prebuilt prompts/seeds.
        self._save_settings()
        if self.worker and self.worker.isRunning():
            return
        self.run_btn.setEnabled(False)
        self._set_tasks_active_row("Pipeline run", "Running (approved storyboard)…", folder="In progress")

        # Use a special attribute read by run_once (we'll add support) via PipelineWorker args.
        self.worker = PipelineWorker(self.settings, prebuilt_pkg=None, prebuilt_sources=None, prebuilt_prompts=prompts, prebuilt_seeds=seeds)
        self.worker.done.connect(lambda out: self._on_done(out))
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_done(self, out_dir: str) -> None:
        self._clear_tasks_active_row()
        self.run_btn.setEnabled(True)
        if not out_dir:
            self._append_log("No new items found.")
            return
        self._append_log(f"Completed: {out_dir}")
        try:
            from pathlib import Path

            from src.upload_tasks import append_task_for_video_dir

            p = Path(str(out_dir).strip())
            if p.is_dir() and (p / "final.mp4").is_file():
                task = append_task_for_video_dir(p)
                self._tasks_refresh()
                if task:
                    if bool(getattr(self.settings, "tiktok_auto_upload_after_render", False)):
                        self._maybe_auto_tiktok_upload(task.id)
                    if bool(getattr(self.settings, "youtube_auto_upload_after_render", False)):
                        self._maybe_auto_youtube_upload(task.id)
        except Exception as e:
            dprint("tasks", "enqueue after run failed", str(e))

    def _maybe_auto_tiktok_upload(self, task_id: str) -> None:
        s = self.settings
        if not bool(getattr(s, "tiktok_enabled", False)):
            return
        if not str(getattr(s, "tiktok_client_key", "") or "").strip():
            return
        if not str(getattr(s, "tiktok_refresh_token", "") or "").strip() and not str(
            getattr(s, "tiktok_access_token", "") or ""
        ).strip():
            return
        if getattr(s, "tiktok_publishing_mode", "inbox") != "inbox":
            self._append_log("TikTok auto-upload skipped — set publishing mode to Inbox.")
            return
        if self.tiktok_upload_worker and self.tiktok_upload_worker.isRunning():
            return
        self._append_log("Starting TikTok upload (auto)…")
        self._start_tiktok_upload_worker(task_id)

    def _maybe_auto_youtube_upload(self, task_id: str) -> None:
        s = self.settings
        if not bool(getattr(s, "youtube_enabled", False)):
            return
        if not str(getattr(s, "youtube_client_id", "") or "").strip():
            return
        if not str(getattr(s, "youtube_client_secret", "") or "").strip():
            return
        if not str(getattr(s, "youtube_refresh_token", "") or "").strip() and not str(
            getattr(s, "youtube_access_token", "") or ""
        ).strip():
            return
        if self.youtube_upload_worker and self.youtube_upload_worker.isRunning():
            return
        if self.tiktok_upload_worker and self.tiktok_upload_worker.isRunning():
            # Avoid overlapping heavy uploads — user can retry YouTube from Tasks
            return
        self._append_log("Starting YouTube upload (auto)…")
        self._start_youtube_upload_worker(task_id)

    def _set_tasks_active_row(
        self,
        title: str,
        status: str,
        *,
        youtube: str = "",
        created: str | None = None,
        folder: str = "—",
    ) -> None:
        c = created or (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M") + " UTC")
        self._tasks_active_row = {
            "title": title,
            "status": status,
            "youtube": youtube,
            "created": c,
            "folder": folder,
        }
        self._tasks_refresh()

    def _update_tasks_active_progress(self, task_id: str, pct: int, message: str) -> None:
        if not self._tasks_active_row:
            return
        self._tasks_active_row["status"] = format_status_line(task_id, pct, message)[:300]
        self._tasks_refresh()

    def _clear_tasks_active_row(self) -> None:
        if self._tasks_active_row is None:
            return
        self._tasks_active_row = None
        self._tasks_refresh()

    def _tasks_refresh(self) -> None:
        if not hasattr(self, "tasks_table"):
            return
        from pathlib import Path

        from src.upload_tasks import load_tasks

        self.tasks_table.setRowCount(0)
        if self._tasks_active_row:
            ar = self._tasks_active_row
            self.tasks_table.insertRow(0)
            t0 = QTableWidgetItem(str(ar.get("title", "Working…"))[:120])
            t0.setData(Qt.ItemDataRole.UserRole, _TASKS_ACTIVE_JOB_TOKEN)
            self.tasks_table.setItem(0, 0, t0)
            self.tasks_table.setItem(0, 1, QTableWidgetItem(str(ar.get("status", "running"))[:200]))
            self.tasks_table.setItem(0, 2, QTableWidgetItem(str(ar.get("youtube", ""))[:80]))
            self.tasks_table.setItem(0, 3, QTableWidgetItem(str(ar.get("created", ""))[:24]))
            self.tasks_table.setItem(0, 4, QTableWidgetItem(str(ar.get("folder", "—"))[:120]))
        for t in load_tasks():
            r = self.tasks_table.rowCount()
            self.tasks_table.insertRow(r)
            title_item = QTableWidgetItem(t.title[:120])
            title_item.setData(Qt.ItemDataRole.UserRole, t.id)
            self.tasks_table.setItem(r, 0, title_item)
            self.tasks_table.setItem(r, 1, QTableWidgetItem(t.status))
            yt_cell = ""
            if str(getattr(t, "youtube_status", "") or "") == "posted" and str(getattr(t, "youtube_video_id", "") or ""):
                yv = str(t.youtube_video_id)
                yt_cell = yv if len(yv) <= 14 else yv[:12] + "…"
            elif str(getattr(t, "youtube_status", "") or "") == "failed":
                yt_cell = "failed"
            elif str(getattr(t, "youtube_status", "") or ""):
                yt_cell = str(t.youtube_status)
            self.tasks_table.setItem(r, 2, QTableWidgetItem(yt_cell))
            self.tasks_table.setItem(r, 3, QTableWidgetItem(t.created_at[:19] if t.created_at else ""))
            vd = Path(t.video_dir).name
            self.tasks_table.setItem(r, 4, QTableWidgetItem(vd))

    def _tasks_selected_id(self) -> str | None:
        if not hasattr(self, "tasks_table"):
            return None
        items = self.tasks_table.selectedItems()
        if not items:
            return None
        row = items[0].row()
        it = self.tasks_table.item(row, 0)
        if it is None:
            return None
        tid = it.data(Qt.ItemDataRole.UserRole)
        if tid == _TASKS_ACTIVE_JOB_TOKEN:
            return None
        return str(tid) if tid else None

    def _tasks_open_folder(self) -> None:
        tid = self._tasks_selected_id()
        if not tid:
            return
        from pathlib import Path

        from src.upload_tasks import load_tasks

        for t in load_tasks():
            if t.id == tid:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(t.video_dir))))
                return

    def _tasks_play_video(self) -> None:
        tid = self._tasks_selected_id()
        if not tid:
            return
        from pathlib import Path

        from src.upload_tasks import load_tasks

        for t in load_tasks():
            if t.id == tid:
                p = Path(t.video_dir) / "final.mp4"
                if p.is_file():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
                return

    def _tasks_copy_caption(self) -> None:
        tid = self._tasks_selected_id()
        if not tid:
            return
        from pathlib import Path

        from src.tiktok_post import build_caption_package
        from src.upload_tasks import load_tasks

        for t in load_tasks():
            if t.id == tid:
                _, cap = build_caption_package(Path(t.video_dir))
                QGuiApplication.clipboard().setText(cap)
                self._append_log("Caption copied to clipboard.")
                return

    def _tasks_mark_posted_manual(self) -> None:
        tid = self._tasks_selected_id()
        if not tid:
            return
        from src.upload_tasks import set_task_status

        set_task_status(tid, "posted")
        self._tasks_refresh()

    def _tasks_remove_selected(self) -> None:
        tid = self._tasks_selected_id()
        if not tid:
            return
        from src.upload_tasks import remove_task

        remove_task(tid)
        self._tasks_refresh()

    def _tasks_upload_tiktok(self) -> None:
        tid = self._tasks_selected_id()
        if not tid:
            QMessageBox.information(self, "Tasks", "Select a task row first.")
            return
        self.settings = self._collect_settings_from_ui()
        if not bool(getattr(self.settings, "tiktok_enabled", False)):
            QMessageBox.information(self, "TikTok", "Enable TikTok in the API tab and connect your account.")
            return
        if self.tiktok_upload_worker and self.tiktok_upload_worker.isRunning():
            return
        self._start_tiktok_upload_worker(tid)

    def _tasks_upload_youtube(self) -> None:
        tid = self._tasks_selected_id()
        if not tid:
            QMessageBox.information(self, "Tasks", "Select a task row first.")
            return
        self.settings = self._collect_settings_from_ui()
        if not bool(getattr(self.settings, "youtube_enabled", False)):
            QMessageBox.information(self, "YouTube", "Enable YouTube in the API tab and connect your account.")
            return
        if self.youtube_upload_worker and self.youtube_upload_worker.isRunning():
            return
        if self.tiktok_upload_worker and self.tiktok_upload_worker.isRunning():
            QMessageBox.information(self, "Uploads", "Another upload is in progress — wait for it to finish.")
            return
        self._start_youtube_upload_worker(tid)

    def _start_tiktok_upload_worker(self, task_id: str) -> None:
        self.settings = self._collect_settings_from_ui()
        self.tiktok_upload_worker = TikTokUploadWorker(self.settings, task_id)
        self.tiktok_upload_worker.finished_ok.connect(self._on_tiktok_upload_ok)
        self.tiktok_upload_worker.failed.connect(self._on_tiktok_upload_failed)
        self.tiktok_upload_worker.start()

    def _start_youtube_upload_worker(self, task_id: str) -> None:
        self.settings = self._collect_settings_from_ui()
        self.youtube_upload_worker = YouTubeUploadWorker(self.settings, task_id)
        self.youtube_upload_worker.finished_ok.connect(self._on_youtube_upload_ok)
        self.youtube_upload_worker.failed.connect(self._on_youtube_upload_failed)
        self.youtube_upload_worker.start()

    def _on_tiktok_upload_ok(self, message: str, access: str, refresh: str, exp: float) -> None:
        self._append_log(message)
        try:
            self.settings = replace(
                self.settings,
                tiktok_access_token=str(access or ""),
                tiktok_refresh_token=str(refresh or ""),
                tiktok_token_expires_at=float(exp or 0),
            )
            save_settings(self.settings)
        except Exception:
            pass
        self._tasks_refresh()

    def _on_tiktok_upload_failed(self, err: str) -> None:
        self._append_log("TikTok upload failed:")
        self._append_log(err)
        self._tasks_refresh()

    def _on_youtube_upload_ok(self, message: str, access: str, refresh: str, exp: float) -> None:
        self._append_log(message)
        try:
            prev_rt = str(getattr(self.settings, "youtube_refresh_token", "") or "").strip()
            self.settings = replace(
                self.settings,
                youtube_access_token=str(access or ""),
                youtube_refresh_token=str(refresh or "").strip() or prev_rt,
                youtube_token_expires_at=float(exp or 0),
            )
            save_settings(self.settings)
        except Exception:
            pass
        self._tasks_refresh()

    def _on_youtube_upload_failed(self, err: str) -> None:
        self._append_log("YouTube upload failed:")
        self._append_log(err)
        self._tasks_refresh()

    def _tiktok_connect_clicked(self) -> None:
        self.settings = self._collect_settings_from_ui()
        ck = str(getattr(self.settings, "tiktok_client_key", "") or "").strip()
        sec = str(getattr(self.settings, "tiktok_client_secret", "") or "").strip()
        if not ck or not sec:
            QMessageBox.warning(self, "TikTok", "Enter Client key and Client secret from developers.tiktok.com first, then Save or try again.")
            return
        port = int(getattr(self.settings, "tiktok_oauth_port", 8765) or 8765)
        redirect = str(getattr(self.settings, "tiktok_redirect_uri", "") or "").strip()
        if not redirect:
            from src.tiktok_post import default_redirect_uri

            redirect = default_redirect_uri(port)
        state = secrets.token_urlsafe(24)
        from src.tiktok_post import build_authorize_url, exchange_authorization_code, generate_pkce, parse_token_response

        verifier, challenge = generate_pkce()
        scopes = ["user.info.basic", "video.upload"]

        def work() -> None:
            import time

            from src.tiktok_oauth_server import run_oauth_loopback

            try:
                code, oerr = run_oauth_loopback(port, state, timeout_s=300.0)
                if oerr:
                    QTimer.singleShot(0, lambda: self._tiktok_oauth_ui_failed(str(oerr)))
                    return
                if not code:
                    QTimer.singleShot(0, lambda: self._tiktok_oauth_ui_failed("No authorization code (timeout or closed browser)."))
                    return
                raw = exchange_authorization_code(
                    client_key=ck,
                    client_secret=sec,
                    code=code,
                    redirect_uri=redirect,
                    code_verifier=verifier,
                )
                p = parse_token_response(raw)
                exp = time.time() + float(p.get("expires_in", 86400))
                QTimer.singleShot(
                    0,
                    lambda: self._tiktok_oauth_ui_ok(str(p["access_token"]), str(p.get("refresh_token") or ""), exp, str(p.get("open_id") or "")),
                )
            except Exception as e:
                QTimer.singleShot(0, lambda: self._tiktok_oauth_ui_failed(str(e)))

        threading.Thread(target=work, daemon=True).start()
        url = build_authorize_url(client_key=ck, redirect_uri=redirect, state=state, scopes=scopes, code_challenge=challenge)
        QTimer.singleShot(350, lambda: webbrowser.open(url))
        self._append_log("Opened browser for TikTok login — complete authorization in the browser.")

    def _tiktok_oauth_ui_failed(self, err: str) -> None:
        QMessageBox.warning(self, "TikTok OAuth", err[:800])
        self._append_log(f"TikTok OAuth failed: {err}")

    def _tiktok_oauth_ui_ok(self, access: str, refresh: str, exp: float, open_id: str) -> None:
        try:
            self.settings = replace(
                self.settings,
                tiktok_access_token=access,
                tiktok_refresh_token=refresh,
                tiktok_token_expires_at=float(exp),
                tiktok_open_id=open_id,
            )
            save_settings(self.settings)
            self._append_log("TikTok connected. Tokens saved locally.")
            if hasattr(self, "api_tt_status_lbl"):
                self.api_tt_status_lbl.setText("Status: connected (tokens saved)")
        except Exception as e:
            self._append_log(f"Failed to save TikTok tokens: {e}")

    def _youtube_connect_clicked(self) -> None:
        import time

        self.settings = self._collect_settings_from_ui()
        cid = str(getattr(self.settings, "youtube_client_id", "") or "").strip()
        sec = str(getattr(self.settings, "youtube_client_secret", "") or "").strip()
        if not cid or not sec:
            QMessageBox.warning(
                self,
                "YouTube",
                "Enter OAuth Client ID and Client secret from Google Cloud Console first, then Save or try again.",
            )
            return
        port = int(getattr(self.settings, "youtube_oauth_port", 8888) or 8888)
        redirect = str(getattr(self.settings, "youtube_redirect_uri", "") or "").strip()
        if not redirect:
            from src.youtube_upload import default_youtube_redirect_uri

            redirect = default_youtube_redirect_uri(port)
        state = secrets.token_urlsafe(24)
        from src.youtube_upload import build_authorization_url, exchange_authorization_code, parse_token_response

        def work() -> None:
            from src.tiktok_oauth_server import run_oauth_loopback

            try:
                code, oerr = run_oauth_loopback(
                    port,
                    state,
                    timeout_s=300.0,
                    success_html_body="<html><body><p>YouTube authorization received. You can close this tab.</p></body></html>",
                )
                if oerr:
                    QTimer.singleShot(0, lambda: self._youtube_oauth_ui_failed(str(oerr)))
                    return
                if not code:
                    QTimer.singleShot(
                        0,
                        lambda: self._youtube_oauth_ui_failed("No authorization code (timeout or closed browser)."),
                    )
                    return
                raw = exchange_authorization_code(
                    client_id=cid,
                    client_secret=sec,
                    code=code,
                    redirect_uri=redirect,
                )
                p = parse_token_response(raw)
                exp = time.time() + float(p.get("expires_in", 3600))
                rt_new = str(p.get("refresh_token") or "").strip()
                QTimer.singleShot(
                    0,
                    lambda: self._youtube_oauth_ui_ok(
                        str(p["access_token"]),
                        rt_new,
                        exp,
                    ),
                )
            except Exception as e:
                QTimer.singleShot(0, lambda: self._youtube_oauth_ui_failed(str(e)))

        threading.Thread(target=work, daemon=True).start()
        url = build_authorization_url(client_id=cid, redirect_uri=redirect, state=state)
        QTimer.singleShot(350, lambda: webbrowser.open(url))
        self._append_log("Opened browser for Google login — finish authorization to enable YouTube uploads.")

    def _youtube_oauth_ui_failed(self, err: str) -> None:
        QMessageBox.warning(self, "YouTube OAuth", err[:800])
        self._append_log(f"YouTube OAuth failed: {err}")

    def _youtube_oauth_ui_ok(self, access: str, refresh: str, exp: float) -> None:
        try:
            prev_rt = str(getattr(self.settings, "youtube_refresh_token", "") or "").strip()
            self.settings = replace(
                self.settings,
                youtube_access_token=access,
                youtube_refresh_token=refresh or prev_rt,
                youtube_token_expires_at=float(exp),
            )
            save_settings(self.settings)
            self._append_log("YouTube connected. Tokens saved locally.")
            if hasattr(self, "api_yt_status_lbl"):
                self.api_yt_status_lbl.setText("Status: connected (tokens saved)")
        except Exception as e:
            self._append_log(f"Failed to save YouTube tokens: {e}")

    def _on_failed(self, err: str) -> None:
        self._clear_tasks_active_row()
        self.run_btn.setEnabled(True)
        self._append_log("Run failed:")
        self._append_log(err)
