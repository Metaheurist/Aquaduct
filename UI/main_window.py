from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QTabWidget,
)

from src.config import AppSettings, VideoSettings, get_paths
from src.model_manager import download_model_to_project
from src.ui_settings import load_settings, save_settings

from UI.paths import project_root
from UI.tabs import (
    attach_advanced_tab,
    attach_my_pc_tab,
    attach_quality_tab,
    attach_run_tab,
    attach_settings_tab,
    attach_topics_tab,
    attach_video_tab,
)
from UI.workers import PipelineWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI News Factory — TikTok Console")
        self.resize(1080, 720)

        self.paths = get_paths()
        self.settings = load_settings()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        attach_run_tab(self)
        attach_topics_tab(self)
        attach_video_tab(self)
        attach_quality_tab(self)
        attach_advanced_tab(self)
        attach_settings_tab(self)
        attach_my_pc_tab(self)

        self.worker: PipelineWorker | None = None

    def _append_log(self, line: str) -> None:
        self.log_box.append(line.rstrip())

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
        self.settings.topic_tags = [t for t in self.settings.topic_tags if t not in remove]
        self._sync_tags_to_ui()

    def _clear_tags(self) -> None:
        self.settings.topic_tags = []
        self._sync_tags_to_ui()

    def _collect_settings_from_ui(self) -> AppSettings:
        video = VideoSettings(
            width=self.settings.video.width,
            height=self.settings.video.height,
            fps=int(self.fps_spin.value()),
            microclip_min_s=float(self.min_clip_spin.value()),
            microclip_max_s=float(self.max_clip_spin.value()),
            music_volume=self.settings.video.music_volume,
            voice_volume=self.settings.video.voice_volume,
            images_per_video=int(self.images_spin.value()),
            export_microclips=bool(self.export_microclips_chk.isChecked()),
            bitrate_preset=self.bitrate_combo.currentText(),  # type: ignore[arg-type]
        )
        return AppSettings(
            topic_tags=list(self.settings.topic_tags),
            prefer_gpu=bool(self.prefer_gpu_chk.isChecked()),
            try_llm_4bit=bool(self.try_llm_chk.isChecked()),
            try_sdxl_turbo=bool(self.try_sdxl_chk.isChecked()),
            background_music_path=str(self.music_path.text()).strip(),
            llm_model_id=str(self.llm_combo.currentData()) if hasattr(self, "llm_combo") else self.settings.llm_model_id,
            image_model_id=str(self.img_combo.currentData()) if hasattr(self, "img_combo") else self.settings.image_model_id,
            voice_model_id=str(self.voice_combo.currentData()) if hasattr(self, "voice_combo") else self.settings.voice_model_id,
            video=video,
        )

    def _save_settings(self) -> None:
        self.settings = self._collect_settings_from_ui()
        save_settings(self.settings)
        self._append_log("Saved settings.")

    def _open_videos(self) -> None:
        self.paths.videos_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(Path(self.paths.videos_dir).as_uri())  # type: ignore[arg-type]

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
        if missing:
            self.deps_status.setPlainText("Missing imports:\n- " + "\n- ".join(missing))
        else:
            self.deps_status.setPlainText("All core imports are available.")

    def _install_deps(self) -> None:
        req = project_root() / "requirements.txt"
        if not req.exists():
            self.deps_status.setPlainText("requirements.txt not found.")
            return
        self._append_log("Installing dependencies (pip -r requirements.txt)…")
        try:
            p = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req)],
                capture_output=True,
                text=True,
            )
            self.deps_status.setPlainText((p.stdout or "") + "\n" + (p.stderr or ""))
            self._append_log("Dependency install finished.")
        except Exception as e:
            self.deps_status.setPlainText(f"Install failed: {e}")

    def _download_selected(self, kind: str) -> None:
        if kind == "script":
            repo_id = str(self.llm_combo.currentData())
        elif kind == "video":
            repo_id = str(self.img_combo.currentData())
        else:
            repo_id = str(self.voice_combo.currentData())
        self._append_log(f"Downloading model: {repo_id}")
        try:
            local = download_model_to_project(repo_id, models_dir=self.paths.models_dir)
            self._append_log(f"Downloaded to: {local}")
        except Exception as e:
            self._append_log(f"Download failed: {e}")

    def _download_all_selected(self) -> None:
        self._download_selected("script")
        self._download_selected("video")
        self._download_selected("voice")

    def _on_run(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self._save_settings()
        self.run_btn.setEnabled(False)
        self._append_log("Starting run…")

        self.worker = PipelineWorker(self.settings)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_done(self, out_dir: str) -> None:
        self.run_btn.setEnabled(True)
        if not out_dir:
            self._append_log("No new items found.")
            return
        self._append_log(f"Completed: {out_dir}")

    def _on_failed(self, err: str) -> None:
        self.run_btn.setEnabled(True)
        self._append_log("Run failed:")
        self._append_log(err)
