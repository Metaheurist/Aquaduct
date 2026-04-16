from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QTimer, QUrl, Qt, QPoint
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
    QVBoxLayout,
    QWidget,
)

from src.config import AppSettings, BrandingSettings, VideoSettings, get_paths
from src.fs_delete import rmtree_robust, unlink_file
from src.model_manager import download_model_to_project, model_has_local_snapshot
from src.preflight import preflight_check
from src.ui_settings import load_settings, save_settings, settings_path
from src.personalities import get_personality_by_id

from UI.paths import project_root
from UI.tabs import (
    attach_branding_tab,
    attach_captions_tab,
    attach_my_pc_tab,
    attach_run_tab,
    attach_settings_tab,
    attach_topics_tab,
    attach_video_tab,
)
from UI.download_popup import DownloadPopup
from UI.workers import ModelDownloadWorker, PipelineBatchWorker, PipelineWorker, PreviewWorker, StoryboardWorker
from UI.workers import TopicDiscoverWorker
from UI.preview_dialog import PreviewDialog
from UI.storyboard_dialog import StoryboardPreviewDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI News Factory — TikTok Console")

        # Borderless + fixed size (non-resizable)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        # Fixed width, dynamic height (still non-resizable).
        self.setFixedWidth(1080)
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
        title = QLabel("AI News Factory")
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

        # Don't force the tab widget to expand; we'll size the window to its active page.
        root_lay.addWidget(self.tabs, 0)
        self.setCentralWidget(self._root)

        attach_run_tab(self)
        attach_topics_tab(self)
        attach_video_tab(self)
        attach_captions_tab(self)
        attach_branding_tab(self)
        attach_settings_tab(self)
        attach_my_pc_tab(self)

        # Shrink/grow window to the active tab (QTabWidget otherwise sizes to the tallest page).
        self.tabs.currentChanged.connect(lambda _idx: self._resize_to_current_tab())
        QTimer.singleShot(0, self._resize_to_current_tab)
        # Prompt for HF token once the window is ready (if needed).
        QTimer.singleShot(0, self._maybe_prompt_hf_token)
        if hasattr(self, "personality_combo"):
            self.personality_combo.currentIndexChanged.connect(self._update_personality_hint)
            self._update_personality_hint()

        self.worker: PipelineWorker | None = None
        self.topic_worker: TopicDiscoverWorker | None = None
        self.download_worker: ModelDownloadWorker | None = None
        self._download_popup: DownloadPopup | None = None
        self._paused_download_repo_ids: list[str] | None = None
        self._paused_download_title: str | None = None
        self.preview_worker: PreviewWorker | None = None
        self.storyboard_worker: StoryboardWorker | None = None
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
            t = str(getattr(self.settings, "hf_token", "") or "").strip()
            if not t:
                return
            os.environ["HF_TOKEN"] = t
        except Exception:
            pass

    def _maybe_prompt_hf_token(self) -> None:
        """
        If no token is available (env or saved settings), prompt user to paste one.
        """
        try:
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

        hint = QLabel(
            "Some models and size lookups require a Hugging Face access token.\n\n"
            "How to get one:\n"
            "- Go to https://huggingface.co/settings/tokens\n"
            "- Create a token (a standard read-only token is enough)\n"
            "- Paste it below\n\n"
            "We will store it in ui_settings.json and use it for authenticated Hub requests."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #B7B7C2;")
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
            self.settings = replace(self.settings, hf_token=token)
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
        if hasattr(self, "run_status"):
            self.run_status.setText("Idle")
        if hasattr(self, "run_progress"):
            self.run_progress.setValue(0)
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
        self.settings = AppSettings(topic_tags=[])
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

        # Base: title bar + tab bar + current page content.
        title_h = self._title_bar.sizeHint().height() if hasattr(self, "_title_bar") else 40
        tabbar_h = self.tabs.tabBar().sizeHint().height()
        lay = page.layout()
        if lay is not None:
            page_h = int(lay.sizeHint().height())
        else:
            page_h = int(page.sizeHint().height())

        # Layout margins (top+bottom) + small padding inside tab pane.
        h = int(title_h + tabbar_h + page_h + 10 + 10 + 48)

        # Clamp so it doesn't get too tiny or exceed the screen.
        min_h = 360
        max_h = 980
        h = max(min_h, min(max_h, int(h)))
        self.setFixedSize(self.width(), h)

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

    def _sync_tags_to_ui(self) -> None:
        from PyQt6.QtWidgets import QListWidgetItem

        self.tag_list.clear()
        for t in self.settings.topic_tags:
            self.tag_list.addItem(QListWidgetItem(t))

    def _add_tag(self) -> None:
        t = " ".join(self.tag_input.text().split()).strip()
        if not t:
            return
        if t not in self.settings.topic_tags:
            self.settings.topic_tags.append(t)
            self._sync_tags_to_ui()
        self.tag_input.clear()

    def _remove_selected_tags(self) -> None:
        selected = self.tag_list.selectedItems()
        if not selected:
            return
        remove = {it.text() for it in selected}
        # AppSettings is a frozen dataclass; mutate the list in-place.
        self.settings.topic_tags[:] = [t for t in self.settings.topic_tags if t not in remove]
        self._sync_tags_to_ui()

    def _clear_tags(self) -> None:
        # AppSettings is a frozen dataclass; mutate the list in-place.
        self.settings.topic_tags.clear()
        self._sync_tags_to_ui()

    def _discover_topics(self) -> None:
        if self.topic_worker and self.topic_worker.isRunning():
            return
        if hasattr(self, "discover_btn"):
            try:
                self.discover_btn.setEnabled(False)
                self.discover_btn.setText("Discovering…")
            except Exception:
                pass
        self.topic_worker = TopicDiscoverWorker(limit=12)
        self.topic_worker.done.connect(self._on_topics_discovered)
        self.topic_worker.failed.connect(self._on_topics_failed)
        self.topic_worker.start()

    def _on_topics_discovered(self, topics: list[str]) -> None:
        if hasattr(self, "discover_btn"):
            try:
                self.discover_btn.setEnabled(True)
                self.discover_btn.setText("Discover")
            except Exception:
                pass
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

        added = 0
        for t in picked:
            t = " ".join(t.split()).strip()
            if not t:
                continue
            if t not in self.settings.topic_tags:
                self.settings.topic_tags.append(t)
                added += 1
        self._sync_tags_to_ui()
        self._save_settings()
        self._append_log(f"Added {added} topic tag(s).")

    def _on_topics_failed(self, err: str) -> None:
        if hasattr(self, "discover_btn"):
            try:
                self.discover_btn.setEnabled(True)
                self.discover_btn.setText("Discover")
            except Exception:
                pass
        if hasattr(self, "_no_topics_dialog"):
            self._no_topics_dialog(self)
        else:
            self._append_log("Topic discovery failed:")
            self._append_log(err)

    def _collect_settings_from_ui(self) -> AppSettings:
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

        return AppSettings(
            topic_tags=list(self.settings.topic_tags),
            prefer_gpu=bool(self.prefer_gpu_chk.isChecked()),
            try_llm_4bit=bool(self.try_llm_chk.isChecked()),
            try_sdxl_turbo=bool(self.try_sdxl_chk.isChecked()),
            background_music_path=str(self.music_path.text()).strip(),
            hf_token=str(getattr(self.settings, "hf_token", "") or ""),
            personality_id=str(self.personality_combo.currentData()) if hasattr(self, "personality_combo") else getattr(self.settings, "personality_id", "auto"),
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
        seen = self.paths.news_cache_dir / "seen.json"
        try:
            if seen.exists():
                seen.unlink()
                self._append_log("Cleared seen.json cache.")
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

    def _start_download(self, repo_ids: list[str], *, title: str) -> None:
        if self.download_worker and self.download_worker.isRunning():
            return
        repo_ids = [r for r in repo_ids if r and r.strip()]
        if not repo_ids:
            return

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

        def on_progress(pct: int, status: str) -> None:
            popup.status.setText(status)
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
            if self._download_popup is not None:
                self._download_popup.close()
        except Exception:
            pass
        return super().closeEvent(event)

    def _on_run(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self._save_settings()

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
        if hasattr(self, "run_status"):
            self.run_status.setText("Starting…")
        if hasattr(self, "run_progress"):
            self.run_progress.setValue(0)

        if qty <= 1:
            self.worker = PipelineWorker(self.settings)
            self.worker.done.connect(lambda out: self._on_done(out))
            self.worker.failed.connect(self._on_failed)
            self.worker.start()
            return

        self.worker = PipelineBatchWorker(self.settings, quantity=qty)

        def on_prog(pct: int, status: str) -> None:
            if hasattr(self, "run_status"):
                self.run_status.setText(status)
            if hasattr(self, "run_progress"):
                self.run_progress.setValue(max(0, min(100, int(pct))))
            self._resize_to_current_tab()

        def on_done(msg: str) -> None:
            self.run_btn.setEnabled(True)
            if hasattr(self, "run_status"):
                self.run_status.setText(msg)
            if hasattr(self, "run_progress"):
                self.run_progress.setValue(100 if msg.startswith("Created") else self.run_progress.value())
            self._resize_to_current_tab()

        self.worker.progress.connect(on_prog)
        self.worker.done.connect(on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_preview(self) -> None:
        if self.preview_worker and self.preview_worker.isRunning():
            return

        self._save_settings()
        pf = preflight_check(settings=self.settings, strict=False)
        for w in pf.warnings:
            self._append_log(f"Warning: {w}")

        if hasattr(self, "preview_btn"):
            try:
                self.preview_btn.setEnabled(False)
                self.preview_btn.setText("Previewing…")
            except Exception:
                pass
        if hasattr(self, "run_status"):
            self.run_status.setText("Generating preview…")

        self.preview_worker = PreviewWorker(self.settings)

        def on_prog(pct: int, status: str) -> None:
            if hasattr(self, "run_status"):
                self.run_status.setText(status)
            if hasattr(self, "run_progress"):
                self.run_progress.setValue(max(0, min(100, int(pct))))
            self._resize_to_current_tab()

        def on_done(pkg, sources, prompts, personality_id: str, confidence: str) -> None:
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
            if hasattr(self, "preview_btn"):
                try:
                    self.preview_btn.setEnabled(True)
                    self.preview_btn.setText("Preview")
                except Exception:
                    pass
            self._append_log("Preview failed:")
            self._append_log(err)
            if hasattr(self, "run_status"):
                self.run_status.setText("Preview failed.")

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
        pf = preflight_check(settings=self.settings, strict=True)
        for w in pf.warnings:
            self._append_log(f"Warning: {w}")
        if not pf.ok:
            self._append_log("Preflight failed. Fix these issues before running:")
            for e in pf.errors:
                self._append_log(f"- {e}")
            return

        self.run_btn.setEnabled(False)
        if hasattr(self, "run_status"):
            self.run_status.setText("Starting…")
        if hasattr(self, "run_progress"):
            self.run_progress.setValue(0)

        self.worker = PipelineWorker(
            self.settings,
            prebuilt_pkg=self._last_preview_pkg,
            prebuilt_sources=self._last_preview_sources,
            prebuilt_prompts=self._last_preview_prompts,
        )
        self.worker.done.connect(lambda out: self._on_done(out))
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

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
        if hasattr(self, "storyboard_btn"):
            try:
                self.storyboard_btn.setEnabled(False)
                self.storyboard_btn.setText("Storyboard…")
            except Exception:
                pass
        if hasattr(self, "run_status"):
            self.run_status.setText("Generating storyboard preview…")

        self.storyboard_worker = StoryboardWorker(self.settings)

        def on_prog(pct: int, status: str) -> None:
            if hasattr(self, "run_status"):
                self.run_status.setText(status)
            if hasattr(self, "run_progress"):
                self.run_progress.setValue(max(0, min(100, int(pct))))
            self._resize_to_current_tab()

        def on_done(manifest_path, grid_png_path) -> None:
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
            if hasattr(self, "storyboard_btn"):
                try:
                    self.storyboard_btn.setEnabled(True)
                    self.storyboard_btn.setText("Storyboard Preview")
                except Exception:
                    pass
            self._append_log("Storyboard preview failed:")
            self._append_log(err)
            if hasattr(self, "run_status"):
                self.run_status.setText("Storyboard preview failed.")

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
        if hasattr(self, "run_status"):
            self.run_status.setText("Rendering approved storyboard…")
        if hasattr(self, "run_progress"):
            self.run_progress.setValue(0)

        # Use a special attribute read by run_once (we'll add support) via PipelineWorker args.
        self.worker = PipelineWorker(self.settings, prebuilt_pkg=None, prebuilt_sources=None, prebuilt_prompts=prompts, prebuilt_seeds=seeds)
        self.worker.done.connect(lambda out: self._on_done(out))
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_done(self, out_dir: str) -> None:
        self.run_btn.setEnabled(True)
        if hasattr(self, "run_status"):
            self.run_status.setText("Done" if out_dir else "No new items found.")
        if hasattr(self, "run_progress"):
            self.run_progress.setValue(100 if out_dir else 0)
        if not out_dir:
            return
        self._append_log(f"Completed: {out_dir}")

    def _on_failed(self, err: str) -> None:
        self.run_btn.setEnabled(True)
        self._append_log("Run failed:")
        self._append_log(err)
