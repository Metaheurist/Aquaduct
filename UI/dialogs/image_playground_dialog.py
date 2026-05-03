"""Non-modal F4 image playground: one prompt → still (local diffusion or API image role)."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QPixmap, QResizeEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from UI.dialogs.auxiliary_progress_dialog import schedule_auxiliary_job_memory_purge
from UI.dialogs.frameless_dialog import FramelessDialog, aquaduct_information, aquaduct_warning
from UI.dialogs.llm_chat_dialog import _switch_main_tab
from UI.services.brain_expand import image_model_id_from_ui
from UI.widgets.tab_sections import section_card, section_title
from UI.widgets.title_bar_outline_button import styled_outline_button
from UI.workers.impl import ImagePlaygroundWorker

from src.core.config import AppSettings, get_paths
from src.render.artist import t2i_user_step_choices
from src.runtime.model_backend import is_api_mode, provider_has_key


def resolve_image_target(win) -> tuple[str, str, str, str | None]:
    """
    Returns ``(mode, display_label, model_key_or_repo, error_or_none)``.
    ``mode`` is ``'api'`` or ``'local'``. Mirrors :func:`resolve_chat_target` for the image role.
    """
    settings: AppSettings = win.settings
    if is_api_mode(settings):
        am = getattr(settings, "api_models", None)
        img = getattr(am, "image", None) if am is not None else None
        prov = str(getattr(img, "provider", "") or "").strip().lower() if img else ""
        mdl = str(getattr(img, "model", "") or "").strip() if img else ""
        if not prov or not mdl:
            return "api", "", "", "API mode: configure the Image provider and model on the API tab."
        if not provider_has_key(settings, prov):
            return "api", "", "", f"API mode: missing API key for provider “{prov}” (API tab)."
        label = f"API · {prov} / {mdl}"
        return "api", label, mdl, None

    repo = image_model_id_from_ui(win)
    if not repo:
        return "local", "", "", "Choose an image model on the Model tab."
    label = f"Local · {repo}"
    return "local", label, repo, None


class ImagePlaygroundDialog(FramelessDialog):
    """Ad-hoc text-to-image using the same targets as the pipeline."""

    def __init__(self, win) -> None:
        super().__init__(win, title="Image playground", modal=False, enable_main_blur=False)
        self._win = win
        self.setMinimumSize(800, 520)
        self._did_center = False
        self._worker: ImagePlaygroundWorker | None = None
        self._last_png: str | None = None
        self._preview_full: QPixmap | None = None
        self._step_values: list[int] = []
        playground_cache = get_paths().data_dir / ".cache" / "image_playground"
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
            "Which image pipeline will run: a local Hugging Face diffusion repo (Model) "
            "or your API Image provider/model (API tab). Messages here explain what to fix."
        )
        left_lay.addWidget(self._subtitle)

        self._status = QLabel("Ready.")
        self._status.setStyleSheet("color: #B7B7C2; font-size: 11px;")
        self._status.setToolTip("Short status line—detailed step text from the generator appears here while working.")
        left_lay.addWidget(self._status)

        self._busy = QProgressBar()
        self._busy.setRange(0, 100)
        self._busy.setVisible(False)
        self._busy.setToolTip("Overall progress (0–100%) for the current image job.")
        left_lay.addWidget(self._busy)

        act_card, act_lay = section_card(margins=10, spacing=8)
        act_card.setToolTip("Shortcuts to the main window tabs where image settings live.")
        act_title = section_title("Actions", emphasis=False)
        act_title.setToolTip("Open related tabs on the main window to change the local model or API image setup.")
        act_lay.addWidget(act_title)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._model_btn = styled_outline_button("Model tab", "muted_icon", min_width=88)
        self._api_btn = styled_outline_button("API tab", "muted_icon", min_width=88)
        self._model_btn.setToolTip("Switch to the Model tab: pick local diffusion weights used for this window and video stills.")
        self._api_btn.setToolTip(
            "Switch to the API tab: configure the Image provider, model, and keys used in API mode."
        )
        self._model_btn.clicked.connect(lambda: _switch_main_tab(self._win, "Model"))
        self._api_btn.clicked.connect(lambda: _switch_main_tab(self._win, "API"))
        row.addWidget(self._model_btn)
        row.addWidget(self._api_btn)
        row.addStretch(1)
        act_lay.addLayout(row)
        left_lay.addWidget(act_card)

        prompt_lbl = QLabel("Prompt")
        prompt_lbl.setToolTip("Caption the scene, style, and subject. This text is sent to the image model as-is.")
        left_lay.addWidget(prompt_lbl)
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("Describe the image…")
        self._prompt.setMinimumHeight(96)
        self._prompt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._prompt.setToolTip(
            "Natural-language description of the still you want. Local runs use your Model-tab weights; "
            "API runs use your configured Image model."
        )
        left_lay.addWidget(self._prompt, 1)

        self._steps_panel = QWidget()
        step_row = QHBoxLayout(self._steps_panel)
        step_row.setContentsMargins(0, 0, 0, 0)
        steps_lbl = QLabel("Steps")
        steps_lbl.setToolTip(
            "Discrete inference steps for local diffusion—options depend on the selected model "
            "(turbo models use 1–4; SDXL/SD3/FLUX-dev use higher ranges). Hidden in API mode."
        )
        step_row.addWidget(steps_lbl)
        self._steps_slider = QSlider(Qt.Orientation.Horizontal)
        self._steps_slider.setMinimum(0)
        self._steps_slider.setMaximum(0)
        self._steps_slider.setSingleStep(1)
        self._steps_slider.setPageStep(1)
        self._steps_slider.setToolTip("Drag to pick a step count allowed for the current local image model.")
        self._steps_slider.valueChanged.connect(self._on_steps_slider_changed)
        step_row.addWidget(self._steps_slider, 1)
        self._steps_readout = QLabel("")
        self._steps_readout.setMinimumWidth(40)
        self._steps_readout.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._steps_readout.setStyleSheet("color:#E6E6EA;font-weight:600;")
        self._steps_readout.setToolTip("Current step count sent to the local pipeline.")
        step_row.addWidget(self._steps_readout)
        left_lay.addWidget(self._steps_panel)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._gen_btn = styled_outline_button("Generate", "accent_icon", min_width=88)
        self._save_btn = styled_outline_button("Save as…", "muted_icon", min_width=88)
        self._gen_btn.setToolTip(
            "Run one image from the prompt using your current Model/API image settings. "
            "Disabled while a job is running or if the main pipeline run is active."
        )
        self._save_btn.setToolTip(
            "Copy the last generated PNG to a path you choose. Enabled after a successful generation."
        )
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

        preview_title = QLabel("Preview")
        preview_title.setStyleSheet("color: #9BA6B8; font-size: 12px; font-weight: 600;")
        preview_title.setToolTip("Generated image (scaled to fit; Save as… writes the full file).")
        right_lay.addWidget(preview_title)

        self._preview = QLabel("No image yet.")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(280, 200)
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._preview.setStyleSheet(
            "background-color:#12141c;color:#8A96A3;border:1px solid #343a4d;border-radius:8px;padding:8px;"
        )
        self._preview.setScaledContents(False)
        self._preview.setToolTip(
            "Live preview: scaled to fit (no scroll). Full quality stays on disk for Save as…. Resize the window to see more."
        )
        right_lay.addWidget(self._preview, 1)

        split_lay.addWidget(left, 0)
        split_lay.addWidget(right, 1)
        self.body_layout.addWidget(split_host, 1)

        self._title_lbl.setToolTip(
            "Image playground: quick text-to-image using the same target as the rest of the app. "
            "Press F4 on the main window to focus this dialog."
        )
        self._title_bar.setToolTip("Drag the title bar to move this window.")
        if getattr(self, "_frameless_close_button", None) is not None:
            self._frameless_close_button.setToolTip("Close the image playground window.")

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._did_center:
            self._did_center = True
            self._apply_initial_geometry()
        self._refresh_target()
        self._update_preview_pixmap()

    def _preferred_step_index(self, vals: list[int]) -> int:
        if not vals:
            return 0
        target = 4
        if target in vals:
            return vals.index(target)
        return min(range(len(vals)), key=lambda i: abs(vals[i] - target))

    def _on_steps_slider_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._step_values):
            n = self._step_values[idx]
            self._steps_readout.setText(str(n))
            self._steps_readout.setToolTip(f"Inference steps: {n} (allowed values for this model).")
        else:
            self._steps_readout.setText("")
            self._steps_readout.setToolTip("")

    def _sync_steps_ui_with_model(self) -> None:
        st = getattr(self._win, "settings", None)
        if st is not None and is_api_mode(st):
            self._steps_panel.hide()
            return
        self._steps_panel.show()
        repo = image_model_id_from_ui(self._win) or ""
        vals = t2i_user_step_choices(repo)
        prev: int | None = None
        if self._step_values and 0 <= self._steps_slider.value() < len(self._step_values):
            prev = self._step_values[self._steps_slider.value()]
        self._step_values = list(vals)
        if not self._step_values:
            self._steps_slider.setEnabled(False)
            self._steps_readout.setText("—")
            return
        self._steps_slider.setEnabled(True)
        self._steps_slider.blockSignals(True)
        self._steps_slider.setMaximum(len(self._step_values) - 1)
        if prev is not None:
            idx = min(range(len(self._step_values)), key=lambda i: abs(self._step_values[i] - prev))
        else:
            idx = self._preferred_step_index(self._step_values)
        self._steps_slider.setValue(idx)
        self._steps_slider.blockSignals(False)
        if len(self._step_values) <= 8:
            self._steps_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            self._steps_slider.setTickInterval(1)
        else:
            self._steps_slider.setTickPosition(QSlider.TickPosition.NoTicks)
            self._steps_slider.setTickInterval(0)
        self._on_steps_slider_changed(self._steps_slider.value())

    def _playground_steps(self) -> int:
        if not self._step_values:
            return 4
        i = int(self._steps_slider.value())
        i = max(0, min(i, len(self._step_values) - 1))
        return int(self._step_values[i])

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_preview_pixmap()

    def _update_preview_pixmap(self) -> None:
        if self._preview_full is None or self._preview_full.isNull():
            return
        avail = self._preview.contentsRect().size()
        if avail.width() <= 2 or avail.height() <= 2:
            return
        scaled = self._preview_full.scaled(
            avail.width(),
            avail.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview.setPixmap(scaled)
        self._preview.setText("")

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
            self._sync_steps_ui_with_model()
            return
        _mode, label, _key, err = resolve_image_target(self._win)
        if err:
            self._subtitle.setText(err)
        elif label:
            self._subtitle.setText(label)
        else:
            self._subtitle.setText("")
        self._sync_steps_ui_with_model()

    def _on_generate(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        w = getattr(self._win, "worker", None)
        if w is not None and w.isRunning():
            aquaduct_information(
                self._win,
                "Pipeline running",
                "Wait for the current run to finish before generating an image here.",
            )
            return
        st = getattr(self._win, "settings", None)
        if st is None:
            return
        prompt = self._prompt.toPlainText().strip()
        if not prompt:
            aquaduct_warning(self, "Image playground", "Enter a prompt.")
            return
        _mode, _lab, _key, err = resolve_image_target(self._win)
        if err:
            aquaduct_warning(self._win, "Image playground", err)
            return

        job_dir = self._work_root / "current"
        shutil.rmtree(job_dir, ignore_errors=True)
        job_dir.mkdir(parents=True, exist_ok=True)

        self._gen_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._busy.setVisible(True)
        self._busy.setValue(0)
        self._status.setText("Generating…")
        self._preview_full = None
        self._preview.clear()
        self._preview.setText("…")

        self._worker = ImagePlaygroundWorker(
            prompt=prompt,
            image_model_id=image_model_id_from_ui(self._win),
            steps=self._playground_steps(),
            allow_nsfw=bool(getattr(st, "allow_nsfw", False)),
            art_style_preset_id=str(getattr(st, "art_style_preset_id", None) or "balanced"),
            app_settings=st,
            work_dir=job_dir,
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
        self._last_png = path
        self._busy.setVisible(False)
        self._gen_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._status.setText("Ready.")
        pm = QPixmap(path)
        if pm.isNull():
            self._preview_full = None
            self._preview.setText("Could not load preview.")
            return
        self._preview_full = pm
        self._update_preview_pixmap()

    def _on_worker_fail(self, msg: str) -> None:
        schedule_auxiliary_job_memory_purge()
        self._worker = None
        self._busy.setVisible(False)
        self._gen_btn.setEnabled(True)
        self._preview_full = None
        self._preview.clear()
        self._preview.setText("No image yet.")
        self._status.setText("Failed.")
        aquaduct_warning(self, "Image playground", msg)

    def _on_save_as(self) -> None:
        if not self._last_png:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save image",
            "",
            "PNG (*.png);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            shutil.copy2(self._last_png, path)
            self._status.setText(f"Saved to {path}")
        except OSError as e:
            aquaduct_warning(self, "Save image", str(e))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2500)
        try:
            shutil.rmtree(self._work_root, ignore_errors=True)
        except Exception:
            pass
        try:
            fn = getattr(self._win, "_on_image_playground_closed", None)
            if callable(fn):
                fn()
        except Exception:
            pass
        super().closeEvent(event)
