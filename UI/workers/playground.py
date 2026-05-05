from __future__ import annotations

import traceback
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import AppSettings
from src.models.hf_access import ensure_hf_token_in_env, humanize_hf_hub_error
from src.render.artist import generate_images
from src.render.clips import generate_clips, is_image_to_video_motion_model
from src.runtime.api_generation import cloud_video_mp4_paths, generate_still_png_bytes
from src.runtime.model_backend import is_api_mode
from src.util.cuda_device_policy import resolve_diffusion_cuda_device_index
from src.util.memory_budget import release_between_stages

from UI.workers.common import _reraise_system_interrupt


class ImagePlaygroundWorker(QThread):
    """User prompt to one PNG (F4 image playground); local ``generate_images`` or API still."""

    progress = pyqtSignal(int, str)
    done = pyqtSignal(str)  # absolute path to png
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        prompt: str,
        image_model_id: str,
        steps: int,
        allow_nsfw: bool,
        art_style_preset_id: str,
        app_settings: AppSettings | None,
        work_dir: Path,
    ) -> None:
        super().__init__()
        self.prompt = str(prompt or "").strip()
        self.image_model_id = str(image_model_id or "").strip()
        self.steps = max(1, min(50, int(steps)))
        self.allow_nsfw = bool(allow_nsfw)
        self.art_style_preset_id = str(art_style_preset_id or "balanced").strip() or "balanced"
        self.app_settings = app_settings
        self.work_dir = Path(work_dir)

    def run(self) -> None:
        try:
            if not self.prompt:
                self.failed.emit("Enter a prompt.")
                return
            st = self.app_settings
            self.work_dir.mkdir(parents=True, exist_ok=True)

            if st is not None and is_api_mode(st):
                self.progress.emit(15, "API: requesting image…")
                png = generate_still_png_bytes(settings=st, prompt=self.prompt)
                out_png = self.work_dir / "generated.png"
                out_png.write_bytes(png)
                self.progress.emit(100, "Done")
                self.done.emit(str(out_png.resolve()))
                return

            if not self.image_model_id:
                self.failed.emit("No image model selected on the Model tab.")
                return

            ensure_hf_token_in_env(
                hf_token=str(getattr(st, "hf_token", "") or "") if st is not None else "",
                hf_api_enabled=bool(getattr(st, "hf_api_enabled", True)) if st is not None else True,
            )
            self.progress.emit(5, "Preparing GPU…")
            cuda_ix = resolve_diffusion_cuda_device_index(st)
            release_between_stages(
                "image_playground_before_image",
                cuda_device_index=cuda_ix,
                variant="prepare_diffusion",
            )
            self.progress.emit(10, "Loading diffusion / generating (first load may take a while)…")

            def _img_prog(pct_in: int, msg: str) -> None:
                p = float(max(0, min(100, int(pct_in))))
                v = int(12.0 + 83.0 * (p / 100.0))
                self.progress.emit(max(12, min(97, v)), msg or "Generating…")

            gen = generate_images(
                sdxl_turbo_model_id=self.image_model_id,
                prompts=[self.prompt],
                out_dir=self.work_dir,
                max_images=1,
                steps=self.steps,
                allow_nsfw=self.allow_nsfw,
                on_image_progress=_img_prog,
                art_style_preset_id=self.art_style_preset_id,
                use_style_continuity=False,
                cuda_device_index=cuda_ix,
                inference_settings=st,
            )
            if not gen:
                self.failed.emit("Image generation returned no files.")
                return
            self.progress.emit(100, "Done")
            self.done.emit(str(Path(gen[0].path).resolve()))
        except BaseException as e:
            _reraise_system_interrupt(e)
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class VideoPlaygroundWorker(QThread):
    """User prompt and optional source image → one MP4 (F6); local ``generate_clips`` or API ``cloud_video_mp4_paths``."""

    progress = pyqtSignal(int, str)
    done = pyqtSignal(str)  # absolute path to mp4
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        prompt: str,
        video_model_id: str,
        app_settings: AppSettings | None,
        work_dir: Path,
        init_image_path: Path | str | None = None,
    ) -> None:
        super().__init__()
        self.prompt = str(prompt or "").strip()
        self.video_model_id = str(video_model_id or "").strip()
        self.app_settings = app_settings
        self.work_dir = Path(work_dir)
        self.init_image_path = Path(init_image_path).expanduser() if init_image_path else None

    def run(self) -> None:
        try:
            st = self.app_settings
            self.work_dir.mkdir(parents=True, exist_ok=True)
            vs = getattr(st, "video", None) if st is not None else None
            fps = int(getattr(vs, "fps", 30) or 30) if vs is not None else 30
            sec = float(getattr(vs, "clip_seconds", 4.0) or 4.0) if vs is not None else 4.0
            pro_sec = float(getattr(vs, "pro_clip_seconds", 4.0) or 4.0) if vs is not None else 4.0

            if st is not None and is_api_mode(st):
                if not self.prompt:
                    self.failed.emit("Enter a prompt.")
                    return
                self.progress.emit(12, "API: requesting video…")
                paths = cloud_video_mp4_paths(
                    settings=st,
                    prompts=[self.prompt],
                    out_dir=self.work_dir,
                    pro_clip_seconds=pro_sec,
                )
                if not paths:
                    self.failed.emit("API video returned no files.")
                    return
                self.progress.emit(100, "Done")
                self.done.emit(str(Path(paths[0]).resolve()))
                return

            if not self.video_model_id:
                self.failed.emit("No video model selected on the Model tab.")
                return

            init_resolved: Path | None = None
            if self.init_image_path is not None:
                try:
                    cand = self.init_image_path.expanduser()
                    if cand.is_file():
                        init_resolved = cand.resolve()
                except OSError:
                    init_resolved = None

            i2v = is_image_to_video_motion_model(self.video_model_id)
            if i2v and init_resolved is None:
                self.failed.emit("Choose a source image for this image-to-video checkpoint.")
                return
            if not i2v and not self.prompt:
                self.failed.emit("Enter a prompt.")
                return

            ensure_hf_token_in_env(
                hf_token=str(getattr(st, "hf_token", "") or "") if st is not None else "",
                hf_api_enabled=bool(getattr(st, "hf_api_enabled", True)) if st is not None else True,
            )
            self.progress.emit(5, "Preparing GPU…")
            cuda_ix = resolve_diffusion_cuda_device_index(st)
            release_between_stages(
                "video_playground_before_video",
                cuda_device_index=cuda_ix,
                variant="prepare_diffusion",
            )
            if i2v:
                self.progress.emit(
                    10,
                    "Loading image-to-video model (first load may take a while)…",
                )
            else:
                self.progress.emit(
                    10,
                    "Loading text-to-video model (first load may take a while)…",
                )

            def _spatial(c: int, t: int) -> None:
                pct = 15 + int(70.0 * float(c) / max(1.0, float(t)))
                self.progress.emit(min(95, pct), f"Spatial upscale {c}/{t}…")

            gen = generate_clips(
                video_model_id=self.video_model_id,
                prompts=[self.prompt],
                init_images=[init_resolved] if init_resolved is not None else None,
                out_dir=self.work_dir,
                max_clips=1,
                fps=max(1, fps),
                seconds_per_clip=max(0.5, sec),
                cuda_device_index=cuda_ix,
                inference_settings=st,
                on_spatial_upscale_progress=_spatial,
            )
            if not gen:
                self.failed.emit("Video generation returned no files.")
                return
            self.progress.emit(100, "Done")
            self.done.emit(str(Path(gen[0].path).resolve()))
        except BaseException as e:
            _reraise_system_interrupt(e)
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


# Backwards compatibility (older imports).
StandaloneImageGenWorker = ImagePlaygroundWorker
