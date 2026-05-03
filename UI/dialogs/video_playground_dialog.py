"""Non-modal F6 video playground: one short MP4 (local T2V, local img2vid, or API T2V)."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from UI.dialogs.auxiliary_progress_dialog import schedule_auxiliary_job_memory_purge
from UI.dialogs.frameless_dialog import FramelessDialog, aquaduct_information, aquaduct_warning
from UI.dialogs.llm_chat_dialog import _switch_main_tab
from UI.services.brain_expand import video_model_id_from_ui
from UI.widgets.tab_sections import section_card, section_title
from UI.widgets.title_bar_outline_button import styled_outline_button
from UI.workers.impl import VideoPlaygroundWorker

from src.core.config import AppSettings, get_paths
from src.runtime.model_backend import is_api_mode, provider_has_key
from src.util.video_playground_prompt import (
    PlaygroundMotionUIKind,
    video_playground_motion_ui_kind,
    video_playground_prompt_char_limit,
)


def resolve_video_target(win) -> tuple[str, str, str, str | None]:
    """
    Returns ``(mode, display_label, model_key_or_repo, error_or_none)``.
    ``mode`` is ``'api'`` or ``'local'``. Mirrors :func:`resolve_image_target` for the video role.
    """
    settings: AppSettings = win.settings
    if is_api_mode(settings):
        am = getattr(settings, "api_models", None)
        vid = getattr(am, "video", None) if am is not None else None
        prov = str(getattr(vid, "provider", "") or "").strip().lower() if vid else ""
        mdl = str(getattr(vid, "model", "") or "").strip() if vid else ""
        if not prov or not mdl:
            return "api", "", "", "API mode: configure the Video provider and model on the API tab."
        if not provider_has_key(settings, prov):
            return "api", "", "", f"API mode: missing API key for provider “{prov}” (API tab)."
        label = f"API · {prov} / {mdl}"
        return "api", label, mdl, None

    repo = video_model_id_from_ui(win)
    if not repo:
        return "local", "", "", "Choose a video model on the Model tab (text-to-video or image-to-video — the playground adapts)."
    label = f"Local · {repo}"
    return "local", label, repo, None


class VideoPlaygroundDialog(FramelessDialog):
    """Ad-hoc clips using the same API/local video targets as the main app (T2V or local img2vid)."""

    def __init__(self, win) -> None:
        super().__init__(win, title="Video playground", modal=False, enable_main_blur=False)
        self._win = win
        self.setMinimumSize(800, 520)
        self._did_center = False
        self._worker: VideoPlaygroundWorker | None = None
        self._last_mp4: str | None = None
        self._motion_ui_kind: PlaygroundMotionUIKind = video_playground_motion_ui_kind(mode="local", video_repo_id="")
        self._init_image_path: str | None = None
        playground_cache = get_paths().data_dir / ".cache" / "video_playground"
        playground_cache.mkdir(parents=True, exist_ok=True)
        self._work_root = Path(mkdtemp(prefix="sess_", dir=str(playground_cache)))

        split_host = QWidget()
        split_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        split_lay = QHBoxLayout(split_host)
        split_lay.setContentsMargins(0, 0, 0, 0)
        split_lay.setSpacing(14)

        left = QWidget()
        left.setMinimumWidth(300)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(10)

        self._subtitle = QLabel("")
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet("color: #9BA6B8; font-size: 12px;")
        self._subtitle.setToolTip(
            "Which video pipeline will run: a local Hugging Face motion repo (Model tab) or API Video provider. "
            "The playground switches between text-to-video (prompt only), image-to-video (source still + optional prompt), "
            "and cloud T2V. Hover individual fields for limits."
        )
        left_lay.addWidget(self._subtitle)

        self._status = QLabel("Ready.")
        self._status.setStyleSheet("color: #B7B7C2; font-size: 11px;")
        self._status.setToolTip("Short status line — detailed step text from the generator appears here while working.")
        left_lay.addWidget(self._status)

        self._busy = QProgressBar()
        self._busy.setRange(0, 100)
        self._busy.setVisible(False)
        self._busy.setToolTip("Overall progress (0–100%) for the current video job.")
        left_lay.addWidget(self._busy)

        act_card, act_lay = section_card(margins=10, spacing=8)
        act_card.setToolTip(
            "Shortcuts to the main window tabs. Changing the Video model or API target updates "
            "text vs image inputs and prompt limits."
        )
        act_title = section_title("Actions", emphasis=False)
        act_title.setToolTip("Open related tabs on the main window to change the local model or API video setup.")
        act_lay.addWidget(act_title)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._model_btn = styled_outline_button("Model tab", "muted_icon", min_width=88)
        self._api_btn = styled_outline_button("API tab", "muted_icon", min_width=88)
        self._model_btn.setToolTip("Switch to the Model tab: pick local motion weights (Video row).")
        self._api_btn.setToolTip("Switch to the API tab: configure the Video provider, model, and keys.")
        self._model_btn.clicked.connect(lambda: _switch_main_tab(self._win, "Model"))
        self._api_btn.clicked.connect(lambda: _switch_main_tab(self._win, "API"))
        row.addWidget(self._model_btn)
        row.addWidget(self._api_btn)
        row.addStretch(1)
        act_lay.addLayout(row)
        left_lay.addWidget(act_card)

        self._image_panel = QWidget()
        img_lay = QVBoxLayout(self._image_panel)
        img_lay.setContentsMargins(0, 0, 0, 0)
        img_lay.setSpacing(6)
        self._image_section_title = QLabel("Source image")
        self._image_section_title.setStyleSheet("color: #9BA6B8; font-size: 12px; font-weight: 600;")
        img_lay.addWidget(self._image_section_title)
        img_btn_row = QHBoxLayout()
        img_btn_row.setSpacing(8)
        self._pick_image_btn = styled_outline_button("Browse…", "muted_icon", min_width=88)
        self._pick_image_btn.clicked.connect(self._on_pick_init_image)
        img_btn_row.addWidget(self._pick_image_btn)
        img_btn_row.addStretch(1)
        img_lay.addLayout(img_btn_row)
        self._init_image_lbl = QLabel("No file chosen.")
        self._init_image_lbl.setWordWrap(True)
        self._init_image_lbl.setStyleSheet("color:#8A96A3;font-size:11px;")
        img_lay.addWidget(self._init_image_lbl)
        left_lay.addWidget(self._image_panel)

        self._prompt_block = QWidget()
        prompt_block_lay = QVBoxLayout(self._prompt_block)
        prompt_block_lay.setContentsMargins(0, 0, 0, 0)
        prompt_block_lay.setSpacing(6)
        self._prompt_lbl = QLabel("Prompt")
        self._prompt_lbl.setToolTip("Describe the motion and scene. Sent to the model when it supports text conditioning.")
        prompt_block_lay.addWidget(self._prompt_lbl)

        self._current_prompt_max = 2000
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("Describe the clip…")
        self._prompt.setMinimumHeight(96)
        self._prompt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._prompt.setToolTip(
            "Natural-language description. Local T2V and API video use this; local img2vid may combine it with the still."
        )
        self._prompt.textChanged.connect(self._on_prompt_text_changed)
        prompt_block_lay.addWidget(self._prompt, 1)

        count_row = QHBoxLayout()
        count_row.setContentsMargins(0, 0, 0, 0)
        count_row.addStretch(1)
        self._prompt_limit_lbl = QLabel("0 / —")
        self._prompt_limit_lbl.setMinimumWidth(112)
        self._prompt_limit_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._prompt_limit_lbl.setStyleSheet("color: #C8CDD8; font-size: 11px; font-weight: 600;")
        count_row.addWidget(self._prompt_limit_lbl, 0)
        prompt_block_lay.addLayout(count_row)
        left_lay.addWidget(self._prompt_block, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._gen_btn = styled_outline_button("Generate", "accent_icon", min_width=88)
        self._save_btn = styled_outline_button("Save as…", "muted_icon", min_width=88)
        self._gen_btn.setToolTip(
            "Run one MP4. Requires a prompt for text-to-video / API; image-to-video needs a source still "
            "(and optional prompt when the model supports it). See counters and field tooltips."
        )
        self._save_btn.setToolTip("Copy the last generated MP4 to a path you choose.")
        self._gen_btn.clicked.connect(self._on_generate)
        self._save_btn.clicked.connect(self._on_save_as)
        self._save_btn.setEnabled(False)
        btn_row.addWidget(self._gen_btn)
        btn_row.addWidget(self._save_btn)
        left_lay.addLayout(btn_row)

        right = QWidget()
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(10)

        info_title = QLabel("Output")
        info_title.setStyleSheet("color: #9BA6B8; font-size: 12px; font-weight: 600;")
        info_title.setToolTip("No in-window player in v1 — use Open video or your file manager.")
        right_lay.addWidget(info_title)

        self._out_info = QLabel("No video yet.")
        self._out_info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._out_info.setWordWrap(True)
        self._out_info.setMinimumSize(280, 200)
        self._out_info.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._out_info.setStyleSheet(
            "background-color:#12141c;color:#8A96A3;border:1px solid #343a4d;border-radius:8px;padding:10px;"
        )
        right_lay.addWidget(self._out_info, 1)

        open_row = QHBoxLayout()
        open_row.addStretch(1)
        self._open_video_btn = styled_outline_button("Open video", "muted_icon", min_width=100)
        self._open_folder_btn = styled_outline_button("Open folder", "muted_icon", min_width=100)
        self._open_video_btn.setToolTip("Open the last MP4 in your default app.")
        self._open_folder_btn.setToolTip("Open the folder containing the last MP4.")
        self._open_video_btn.clicked.connect(self._on_open_video)
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        self._open_video_btn.setEnabled(False)
        self._open_folder_btn.setEnabled(False)
        open_row.addWidget(self._open_video_btn)
        open_row.addWidget(self._open_folder_btn)
        right_lay.addLayout(open_row)

        split_lay.addWidget(left, 0)
        split_lay.addWidget(right, 1)
        self.body_layout.addWidget(split_host, 1)

        self._title_lbl.setToolTip(
            "Video playground: one short clip using your Model/API video settings (text-to-video or local image-to-video). "
            "Press F6 on the main window to focus this dialog."
        )
        self._title_bar.setToolTip("Drag the title bar to move this window.")
        if getattr(self, "_frameless_close_button", None) is not None:
            self._frameless_close_button.setToolTip("Close the video playground window.")

    def _current_motion_ui_kind(self) -> PlaygroundMotionUIKind:
        st = getattr(self._win, "settings", None)
        if st is None:
            return "local_t2v"
        if is_api_mode(st):
            return "api_t2v"
        return video_playground_motion_ui_kind(mode="local", video_repo_id=video_model_id_from_ui(self._win))

    def _on_pick_init_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Source image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*.*)",
        )
        if not path:
            return
        self._init_image_path = path
        self._init_image_lbl.setText(path)
        self._init_image_lbl.setToolTip(path)

    def _sync_motion_ui_widgets(self) -> None:
        kind = self._current_motion_ui_kind()
        self._motion_ui_kind = kind
        show_image = kind in ("local_img2vid_image_only", "local_img2vid_with_text")
        show_prompt = kind in ("api_t2v", "local_t2v", "local_img2vid_with_text")
        self._image_panel.setVisible(show_image)
        self._prompt_block.setVisible(show_prompt)

        if kind == "local_img2vid_image_only":
            self._image_section_title.setToolTip(
                "Image-to-video (e.g. Stable Video Diffusion): motion is driven from this still; "
                "the pipeline does not take a text prompt for this checkpoint."
            )
            self._pick_image_btn.setToolTip("Pick one PNG / JPEG / WebP frame to animate. Required before Generate.")
            self._init_image_lbl.setToolTip(
                (self._init_image_path or "No file chosen.") + " — use Browse to select a still."
            )
        elif kind == "local_img2vid_with_text":
            self._image_section_title.setToolTip(
                "Image-to-video with optional text conditioning: still is required; prompt is passed when the Hub pipeline supports it."
            )
            self._pick_image_btn.setToolTip("Pick a still to condition the motion model. Required before Generate.")
            self._init_image_lbl.setToolTip(
                (self._init_image_path or "No file chosen.") + " — required alongside the prompt."
            )
        else:
            self._image_section_title.setToolTip("")
            self._pick_image_btn.setToolTip("")
            self._init_image_lbl.setToolTip("")

        self._update_prompt_limit_ui()
        self._format_out_panel_idle()

    def _on_prompt_text_changed(self) -> None:
        mx = int(getattr(self, "_current_prompt_max", 2000))
        if mx <= 0:
            return
        t = self._prompt.toPlainText()
        if len(t) > mx:
            cur = self._prompt.textCursor()
            pos = min(cur.position(), mx)
            self._prompt.blockSignals(True)
            self._prompt.setPlainText(t[:mx])
            self._prompt.blockSignals(False)
            cur.setPosition(pos)
            self._prompt.setTextCursor(cur)
            t = self._prompt.toPlainText()
        self._prompt_limit_lbl.setText(f"{len(t)} / {mx}")

    def _update_prompt_limit_ui(self) -> None:
        st = getattr(self._win, "settings", None)
        kind = getattr(self, "_motion_ui_kind", "local_t2v")
        if st is None:
            lim, hint = (
                2000,
                "Open from the main window with settings loaded to see model-specific limits.",
            )
        elif is_api_mode(st):
            am = getattr(st, "api_models", None)
            vid = getattr(am, "video", None) if am is not None else None
            prov = str(getattr(vid, "provider", "") or "").strip().lower() if vid else ""
            mdl = str(getattr(vid, "model", "") or "").strip() if vid else ""
            lim, hint = video_playground_prompt_char_limit(
                mode="api",
                api_provider=prov,
                api_model=mdl,
                motion_ui_kind=kind,
            )
        else:
            repo = video_model_id_from_ui(self._win)
            lim, hint = video_playground_prompt_char_limit(
                mode="local",
                video_repo_id=repo,
                motion_ui_kind=kind,
            )
        self._current_prompt_max = max(0, int(lim))
        if self._current_prompt_max <= 0:
            detail = hint
            self._prompt_limit_lbl.setText("—")
            self._prompt_limit_lbl.setToolTip(hint)
        else:
            detail = (
                f"{hint} Anything longer cannot be entered here so it matches what the pipeline or API will accept."
            )
            self._prompt_limit_lbl.setToolTip(
                f"Character budget for this target: {lim} max. {hint}"
            )
        self._prompt.setToolTip(detail)
        self._prompt_lbl.setToolTip(detail)
        t = self._prompt.toPlainText()
        if self._current_prompt_max > 0 and len(t) > self._current_prompt_max:
            self._prompt.blockSignals(True)
            self._prompt.setPlainText(t[: self._current_prompt_max])
            self._prompt.blockSignals(False)
        self._on_prompt_text_changed()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._did_center:
            self._did_center = True
            self._apply_initial_geometry()
        self._refresh_target()

    def _duration_hint_lines(self) -> list[str]:
        st = getattr(self._win, "settings", None)
        lines: list[str] = []
        if st is None:
            return lines
        vs = getattr(st, "video", None)
        kind = getattr(self, "_motion_ui_kind", "local_t2v")
        if kind == "api_t2v":
            pro_sec = float(getattr(vs, "pro_clip_seconds", 4.0) or 4.0) if vs is not None else 4.0
            lines.append(f"Cloud text-to-video — length ≈ {pro_sec:g} s (Pro settings).")
        elif kind == "local_t2v":
            sec = float(getattr(vs, "clip_seconds", 4.0) or 4.0) if vs is not None else 4.0
            fps = int(getattr(vs, "fps", 30) or 30) if vs is not None else 30
            lines.append(f"Local text-to-video — Video tab clip ≈ {sec:g} s, {fps} fps.")
        elif kind == "local_img2vid_image_only":
            sec = float(getattr(vs, "clip_seconds", 4.0) or 4.0) if vs is not None else 4.0
            fps = int(getattr(vs, "fps", 30) or 30) if vs is not None else 30
            lines.append(f"Local image-to-video — still + motion; ~{sec:g} s, {fps} fps. No text prompt for this checkpoint.")
        else:
            sec = float(getattr(vs, "clip_seconds", 4.0) or 4.0) if vs is not None else 4.0
            fps = int(getattr(vs, "fps", 30) or 30) if vs is not None else 30
            lines.append(f"Local image-to-video with text — still required; ~{sec:g} s, {fps} fps.")
        mx = int(getattr(self, "_current_prompt_max", 0))
        if kind in ("api_t2v", "local_t2v", "local_img2vid_with_text") and mx > 0:
            lines.append(f"Prompt budget: up to {mx} characters (see counter).")
        return lines

    def _format_out_panel_idle(self) -> None:
        parts = self._duration_hint_lines()
        self._out_info.setText("\n\n".join(parts) if parts else "No video yet.")

    def _apply_initial_geometry(self) -> None:
        pr = self.parent()
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            w = min(1040, int(geo.width() * 0.72))
            h = min(720, int(geo.height() * 0.78))
            self.resize(max(self.minimumWidth(), w), max(self.minimumHeight(), h))
        if pr is not None:
            fg = pr.frameGeometry().center()
            self.move(fg - self.rect().center())

    def _refresh_target(self) -> None:
        if getattr(self._win, "settings", None) is None:
            self._subtitle.setText("")
            self._sync_motion_ui_widgets()
            return
        _mode, label, _key, err = resolve_video_target(self._win)
        if err:
            self._subtitle.setText(err)
        elif label:
            motion = self._current_motion_ui_kind()
            tag = ""
            if motion == "api_t2v":
                tag = " (cloud text-to-video)"
            elif motion == "local_t2v":
                tag = " (local text-to-video)"
            elif motion == "local_img2vid_image_only":
                tag = " (local image-to-video — still only)"
            elif motion == "local_img2vid_with_text":
                tag = " (local image-to-video + prompt)"
            self._subtitle.setText(f"{label}{tag}")
        else:
            self._subtitle.setText("")
        self._sync_motion_ui_widgets()

    def _on_generate(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        w = getattr(self._win, "worker", None)
        if w is not None and w.isRunning():
            aquaduct_information(
                self._win,
                "Pipeline running",
                "Wait for the current run to finish before generating a clip here.",
            )
            return
        st = getattr(self._win, "settings", None)
        if st is None:
            return
        kind = self._current_motion_ui_kind()
        prompt = self._prompt.toPlainText().strip()
        init_path = self._init_image_path

        if kind == "api_t2v" or kind == "local_t2v":
            if not prompt:
                aquaduct_warning(self, "Video playground", "Enter a prompt.")
                return
        elif kind == "local_img2vid_image_only":
            if not init_path or not Path(init_path).is_file():
                aquaduct_warning(self, "Video playground", "Choose a source image for this image-to-video model.")
                return
        elif kind == "local_img2vid_with_text":
            if not init_path or not Path(init_path).is_file():
                aquaduct_warning(self, "Video playground", "Choose a source image for image-to-video.")
                return

        _mode, _lab, _key, err = resolve_video_target(self._win)
        if err:
            aquaduct_warning(self._win, "Video playground", err)
            return

        job_dir = self._work_root / "current"
        shutil.rmtree(job_dir, ignore_errors=True)
        job_dir.mkdir(parents=True, exist_ok=True)

        self._gen_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._open_video_btn.setEnabled(False)
        self._open_folder_btn.setEnabled(False)
        self._busy.setVisible(True)
        self._busy.setValue(0)
        self._status.setText("Generating…")
        self._last_mp4 = None
        self._format_out_panel_idle()

        init_for_worker: Path | None = None
        if init_path and Path(init_path).is_file():
            init_for_worker = Path(init_path)

        self._worker = VideoPlaygroundWorker(
            prompt=prompt,
            video_model_id=video_model_id_from_ui(self._win),
            app_settings=st,
            work_dir=job_dir,
            init_image_path=init_for_worker,
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.done.connect(self._on_worker_done)
        self._worker.failed.connect(self._on_worker_fail)
        self._worker.start()

    def _on_worker_progress(self, pct: int, msg: str) -> None:
        self._busy.setValue(int(pct))
        if msg:
            self._status.setText(msg)

    def _on_worker_done(self, path: str) -> None:
        schedule_auxiliary_job_memory_purge()
        self._worker = None
        self._last_mp4 = path
        self._busy.setVisible(False)
        self._gen_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._open_video_btn.setEnabled(True)
        self._open_folder_btn.setEnabled(True)
        self._status.setText("Ready.")
        self._out_info.setText(f"Saved:\n{path}\n\nUse Open video or Save as… to copy elsewhere.")

    def _on_worker_fail(self, msg: str) -> None:
        schedule_auxiliary_job_memory_purge()
        self._worker = None
        self._busy.setVisible(False)
        self._gen_btn.setEnabled(True)
        self._last_mp4 = None
        self._open_video_btn.setEnabled(False)
        self._open_folder_btn.setEnabled(False)
        self._status.setText("Failed.")
        self._format_out_panel_idle()
        aquaduct_warning(self, "Video playground", msg)

    def _on_save_as(self) -> None:
        if not self._last_mp4:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save video",
            "",
            "MP4 (*.mp4);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".mp4"):
            path += ".mp4"
        try:
            shutil.copy2(self._last_mp4, path)
            self._status.setText(f"Saved to {path}")
        except OSError as e:
            aquaduct_warning(self, "Save video", str(e))

    def _on_open_video(self) -> None:
        if not self._last_mp4:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_mp4))

    def _on_open_folder(self) -> None:
        if not self._last_mp4:
            return
        folder = str(Path(self._last_mp4).resolve().parent)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2500)
        try:
            shutil.rmtree(self._work_root, ignore_errors=True)
        except Exception:
            pass
        try:
            fn = getattr(self._win, "_on_video_playground_closed", None)
            if callable(fn):
                fn()
        except Exception:
            pass
        super().closeEvent(event)
