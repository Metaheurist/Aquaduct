from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QTimer, QUrl, Qt, QPoint
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTabWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import AppSettings, BrandingSettings, VideoSettings, get_paths
from src.model_manager import download_model_to_project
from src.preflight import preflight_check
from src.ui_settings import load_settings, save_settings
from src.personalities import get_personality_by_id

from UI.paths import project_root
from UI.tabs import (
    attach_branding_tab,
    attach_my_pc_tab,
    attach_run_tab,
    attach_settings_tab,
    attach_topics_tab,
    attach_video_tab,
)
from UI.download_popup import DownloadPopup
from UI.workers import ModelDownloadWorker, PipelineBatchWorker, PipelineWorker
from UI.workers import TopicDiscoverWorker


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
        attach_branding_tab(self)
        attach_settings_tab(self)
        attach_my_pc_tab(self)

        self.worker: PipelineWorker | None = None
        self.topic_worker: TopicDiscoverWorker | None = None
        self.download_worker: ModelDownloadWorker | None = None
        self._download_popup: DownloadPopup | None = None

        if hasattr(self, "personality_combo") and hasattr(self, "personality_hint"):
            self.personality_combo.currentIndexChanged.connect(self._update_personality_hint)
            self._update_personality_hint()

        # Resize window to match active tab content.
        self.tabs.currentChanged.connect(lambda _idx: self._resize_to_current_tab())
        QTimer.singleShot(0, self._resize_to_current_tab)

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
        page_h = page.sizeHint().height()

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

    def _download_selected(self, kind: str) -> None:
        if kind == "script":
            repo_id = str(self.llm_combo.currentData())
        elif kind == "video":
            repo_id = str(self.img_combo.currentData())
        else:
            repo_id = str(self.voice_combo.currentData())
        self._start_download([repo_id], title="Downloading model")

    def _download_all_selected(self) -> None:
        repo_ids = [
            str(self.llm_combo.currentData()),
            str(self.img_combo.currentData()),
            str(self.voice_combo.currentData()),
        ]
        self._start_download(repo_ids, title="Downloading selected models")

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

        self._start_download(repo_ids, title=f"Downloading ALL models ({len(repo_ids)})")

    def _start_download(self, repo_ids: list[str], *, title: str) -> None:
        if self.download_worker and self.download_worker.isRunning():
            return
        repo_ids = [r for r in repo_ids if r and r.strip()]
        if not repo_ids:
            return

        popup = DownloadPopup(self, title=title)
        self._download_popup = popup

        self.download_worker = ModelDownloadWorker(repo_ids=repo_ids, models_dir=self.paths.models_dir, title=title)

        # If user closes the popup, cancel the background worker so app can exit cleanly.
        popup.cancel_requested.connect(lambda: self.download_worker.cancel() if self.download_worker else None)

        def on_progress(pct: int, status: str) -> None:
            popup.status.setText(status)
            popup.bar.setValue(max(0, min(100, int(pct))))

        def on_done(_msg: str) -> None:
            msg = str(_msg or "").strip().lower()
            if "cancel" in msg:
                popup.status.setText("Cancelled. You can resume later.")
                # Don't force bar to 0; leave last visible state.
            else:
                popup.status.setText("Done.")
                popup.bar.setValue(100)
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
