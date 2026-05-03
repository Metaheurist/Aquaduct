"""Optional AI spatial upscaling before final export resolution (Real-ESRGAN-class).

Policy (``spatial_upscale_mode=auto`` on :class:`~src.core.config.VideoSettings`):

1. Try **PyTorch Real-ESRGAN** on CUDA when ``torch`` + ``realesrgan`` / ``basicsr`` import and
   a checkpoint is available (see :func:`pytorch_realesrgan_available`).
2. Else try **realesrgan-ncnn-vulkan** when the binary exists and env does not disable it.
3. On failure or ``off``, callers keep the original path; MoviePy/PIL still resizes in the editor.

This module never raises for expected failures — it logs and returns the source path.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path
from typing import Literal

log = logging.getLogger("aquaduct.spatial_upscale")

SpatialMode = Literal["off", "auto"]

VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

REALESRGAN_X4_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
)

# Estimated headroom for Real-ESRGAN at 1080p-class frames (conservative).
SPATIAL_VRAM_BUDGET_MB = 2500


@dataclass(frozen=True)
class SpatialUpscaleResult:
    output_path: Path
    mode_used: Literal["off", "torch", "ncnn"]


def pytorch_realesrgan_available() -> bool:
    try:
        import importlib

        importlib.import_module("torch")
        importlib.import_module("basicsr.archs.rrdbnet_arch")
        importlib.import_module("realesrgan")
        return True
    except Exception:
        return False


def spatial_vram_budget_ok(*, free_vram_mb: int | None) -> bool:
    if free_vram_mb is None:
        return False
    return int(free_vram_mb) >= SPATIAL_VRAM_BUDGET_MB


def needs_spatial_upscale(sw: int, sh: int, tw: int, th: int) -> bool:
    """Run super-resolution only when the source does not already cover the export rectangle."""
    if sw <= 0 or sh <= 0 or tw <= 0 or th <= 0:
        return False
    return not (sw >= tw and sh >= th)


def _fit_crop_box(iw: int, ih: int, out_w: int, out_h: int) -> tuple[int, int, int, int]:
    target = out_w / out_h
    cur = iw / ih
    if cur > target:
        new_w = int(ih * target)
        left = (iw - new_w) // 2
        return left, 0, left + new_w, ih
    new_h = int(iw / target)
    top = (ih - new_h) // 2
    return 0, top, iw, top + new_h


def _cover_resize_rgb(img, tw: int, th: int):  # PIL Image
    """Center-crop to aspect of tw×th, then resize to exact tw×th (LANCZOS)."""
    from PIL import Image

    resample = getattr(Image, "Resampling", Image).LANCZOS
    iw, ih = img.size
    l, t, r, b = _fit_crop_box(iw, ih, tw, th)
    img = img.crop((l, t, r, b))
    return img.resize((tw, th), resample)


def _cache_weights_dir() -> Path:
    try:
        from src.core.config import get_paths

        d = Path(get_paths().app_data_dir) / "realesrgan"
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        p = Path(".Aquaduct_data") / "realesrgan"
        p.mkdir(parents=True, exist_ok=True)
        return p


def ensure_realesrgan_x4_weights() -> Path | None:
    dest = _cache_weights_dir() / "RealESRGAN_x4plus.pth"
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return dest
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("Downloading Real-ESRGAN x4+ weights to %s", dest)
        urllib.request.urlretrieve(REALESRGAN_X4_URL, str(dest))
    except Exception as exc:
        log.warning("Could not download RealESRGAN weights: %s", exc)
        return None
    return dest if dest.is_file() else None


def _ffmpeg_bin(ffmpeg_dir: Path) -> Path:
    from src.render.utils_ffmpeg import ensure_ffmpeg

    return Path(ensure_ffmpeg(ffmpeg_dir))


def _ffprobe_bin(ffmpeg_bin: Path) -> str:
    p = Path(ffmpeg_bin)
    probe = p.parent / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if probe.is_file():
        return str(probe)
    w = shutil.which("ffprobe.exe" if os.name == "nt" else "ffprobe")
    return str(w) if w else "ffprobe"


def _ffprobe_wh_fps(ffmpeg_bin: Path, src: Path) -> tuple[int, int, float] | None:
    cmd = [
        _ffprobe_bin(ffmpeg_bin),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate",
        "-of",
        "csv=p=0",
        str(src),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        parts = [x.strip() for x in proc.stdout.strip().split(",")]
        if len(parts) < 3:
            return None
        w, h = int(parts[0]), int(parts[1])
        fr = parts[2]
        if "/" in fr:
            a, b = fr.split("/", 1)
            fps = float(a) / max(1.0, float(b))
        else:
            fps = float(fr) if fr else 24.0
        return w, h, max(1.0, fps)
    except Exception:
        return None


def _resolve_ncnn_exe() -> Path | None:
    if os.environ.get("AQUADUCT_DISABLE_REALESRGAN_NCNN", "").strip().lower() in ("1", "true", "yes", "on"):
        return None
    env = os.environ.get("AQUADUCT_REALESRGAN_NCNN", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
    w = shutil.which("realesrgan-ncnn-vulkan")
    if w:
        return Path(w)
    nw = shutil.which("realesrgan-ncnn-vulkan.exe")
    if nw:
        return Path(nw)
    try:
        from src.core.config import get_paths

        for name in ("realesrgan-ncnn-vulkan.exe", "realesrgan-ncnn-vulkan"):
            cand = get_paths().ffmpeg_dir.parent / name
            if cand.is_file():
                return cand
            cand2 = get_paths().app_data_dir / "tools" / name
            if cand2.is_file():
                return cand2
    except Exception:
        pass
    return None


def ncnn_spatial_available() -> bool:
    """True when ``realesrgan-ncnn-vulkan`` resolves (binary path)."""

    return _resolve_ncnn_exe() is not None


def _ncnn_model_name() -> str:
    return os.environ.get("AQUADUCT_REALESRGAN_NCNN_MODEL", "realesrgan-x4plus").strip() or "realesrgan-x4plus"


def _clip_timeout_s() -> float | None:
    raw = os.environ.get("AQUADUCT_SPATIAL_UPSCALE_CLIP_TIMEOUT_S", "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def _job_max_s() -> float | None:
    raw = os.environ.get("AQUADUCT_SPATIAL_UPSCALE_JOB_MAX_S", "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def _mux_audio(video_ns: Path, audio_src: Path, dst: Path, ffmpeg_bin: Path) -> bool:
    cmd = [
        str(ffmpeg_bin),
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_ns),
        "-i",
        str(audio_src),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(dst),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
        return proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 0
    except Exception as exc:
        log.warning("mux audio failed: %s", exc)
        return False


def _upscale_video_ncnn(
    src: Path,
    dst: Path,
    *,
    tw: int,
    th: int,
    ffmpeg_dir: Path,
    deadline: float | None,
) -> bool:
    exe = _resolve_ncnn_exe()
    if exe is None:
        return False
    ffmpeg_bin = _ffmpeg_bin(ffmpeg_dir)
    probe = _ffprobe_wh_fps(ffmpeg_bin, src)
    if not probe:
        return False
    sw, sh, fps = probe
    model = _ncnn_model_name()
    scale = int(os.environ.get("AQUADUCT_REALESRGAN_NCNN_SCALE", "4") or "4")
    scale = max(2, min(4, scale))

    try:
        with tempfile.TemporaryDirectory(prefix="aq_sr_") as tmp:
            from PIL import Image

            tdir = Path(tmp)
            frames_in = tdir / "in"
            frames_out = tdir / "out"
            frames_in.mkdir()
            frames_out.mkdir()
            ext = subprocess.run(
                [
                    str(ffmpeg_bin),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(src),
                    str(frames_in / "%06d.png"),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
            if ext.returncode != 0:
                return False
            inputs = sorted(frames_in.glob("*.png"))
            if not inputs:
                return False
            for i, fp in enumerate(inputs):
                if deadline is not None and time.monotonic() > deadline:
                    log.warning("spatial ncnn: clip timeout at frame %s/%s", i + 1, len(inputs))
                    return False
                outp = frames_out / fp.name
                cmd = [
                    str(exe),
                    "-i",
                    str(fp),
                    "-o",
                    str(outp),
                    "-n",
                    model,
                    "-s",
                    str(scale),
                ]
                try:
                    pr = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
                    if pr.returncode != 0 or not outp.is_file():
                        log.warning(
                            "ncnn upscale failed frame %s: %s",
                            fp.name,
                            (pr.stderr or "").strip()[:200],
                        )
                        return False
                except subprocess.TimeoutExpired:
                    log.warning("ncnn timeout on %s", fp.name)
                    return False

            vid_ns = tdir / "sr_noaudio.mp4"
            enc = subprocess.run(
                [
                    str(ffmpeg_bin),
                    "-y",
                    "-loglevel",
                    "error",
                    "-framerate",
                    str(fps),
                    "-i",
                    str(frames_out / "%06d.png"),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    str(vid_ns),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
            if enc.returncode != 0 or not vid_ns.is_file():
                return False

            out_list = sorted(frames_out.glob("*.png"))
            first = out_list[0] if out_list else None
            if first:
                with Image.open(first) as im0:
                    w0, h0 = im0.size
                if needs_spatial_upscale(w0, h0, tw, th) or (w0, h0) != (tw, th):
                    tuned = tdir / "sr_tuned"
                    tuned.mkdir()
                    for fp in sorted(frames_out.glob("*.png")):
                        if deadline is not None and time.monotonic() > deadline:
                            return False
                        with Image.open(fp) as im:
                            rgb = im.convert("RGB")
                            out = _cover_resize_rgb(rgb, tw, th)
                            out.save(tuned / fp.name, format="PNG")
                    vid_ns2 = tdir / "sr_noaudio2.mp4"
                    enc2 = subprocess.run(
                        [
                            str(ffmpeg_bin),
                            "-y",
                            "-loglevel",
                            "error",
                            "-framerate",
                            str(fps),
                            "-i",
                            str(tuned / "%06d.png"),
                            "-c:v",
                            "libx264",
                            "-preset",
                            "veryfast",
                            "-crf",
                            "18",
                            "-pix_fmt",
                            "yuv420p",
                            str(vid_ns2),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=600,
                    )
                    if enc2.returncode == 0 and vid_ns2.is_file():
                        vid_ns = vid_ns2

            if _mux_audio(vid_ns, src, dst, ffmpeg_bin):
                return True
            try:
                shutil.copy2(vid_ns, dst)
                return dst.is_file()
            except OSError:
                return False
    except Exception as exc:
        log.warning("ncnn pipeline failed: %s", exc)
        return False


def _upscale_video_torch(
    src: Path,
    dst: Path,
    *,
    tw: int,
    th: int,
    ffmpeg_dir: Path,
    cuda_device_index: int | None,
    deadline: float | None,
) -> bool:
    if not pytorch_realesrgan_available():
        return False
    wpath = ensure_realesrgan_x4_weights()
    if wpath is None:
        return False

    import cv2
    import torch
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    ffmpeg_bin = _ffmpeg_bin(ffmpeg_dir)
    probe = _ffprobe_wh_fps(ffmpeg_bin, src)
    if not probe:
        return False
    sw, sh, fps = probe

    if not torch.cuda.is_available():
        return False
    di = int(cuda_device_index) if cuda_device_index is not None else 0
    dev = f"cuda:{max(0, di)}"

    tile = int(os.environ.get("AQUADUCT_REALESRGAN_TILE", "256") or "256")
    tile = max(64, min(1024, tile))

    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    upsampler = RealESRGANer(
        scale=4,
        model_path=str(wpath),
        model=model,
        tile=tile,
        tile_pad=10,
        pre_pad=0,
        half=True,
        device=dev,
    )

    try:
        with tempfile.TemporaryDirectory(prefix="aq_sr_t_") as tmp:
            tdir = Path(tmp)
            frames_in = tdir / "in"
            frames_in.mkdir()
            ext = subprocess.run(
                [
                    str(ffmpeg_bin),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(src),
                    str(frames_in / "%06d.png"),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
            if ext.returncode != 0:
                return False
            frames_out = tdir / "out"
            frames_out.mkdir()
            inputs = sorted(frames_in.glob("*.png"))
            if not inputs:
                return False
            from PIL import Image

            for i, fp in enumerate(inputs):
                if deadline is not None and time.monotonic() > deadline:
                    log.warning("spatial torch: clip timeout at frame %s", i + 1)
                    return False
                img = cv2.imread(str(fp), cv2.IMREAD_UNCHANGED)
                if img is None:
                    return False
                if img.ndim == 2:
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                elif img.shape[2] == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                try:
                    out_bgr, _ = upsampler.enhance(img, outscale=4)
                except torch.cuda.OutOfMemoryError:
                    upsampler.tile = max(64, upsampler.tile // 2)
                    log.info("Real-ESRGAN OOM — retrying with tile=%s", upsampler.tile)
                    try:
                        torch.cuda.empty_cache()
                        out_bgr, _ = upsampler.enhance(img, outscale=4)
                    except Exception as exc:
                        log.warning("Real-ESRGAN enhance failed: %s", exc)
                        return False
                except Exception as exc:
                    log.warning("Real-ESRGAN enhance failed: %s", exc)
                    return False
                cv2.imwrite(str(frames_out / fp.name), out_bgr)
            tuned = tdir / "tuned"
            tuned.mkdir()
            for fp in sorted(frames_out.glob("*.png")):
                if deadline is not None and time.monotonic() > deadline:
                    return False
                with Image.open(fp) as im:
                    rgb = im.convert("RGB")
                    out = _cover_resize_rgb(rgb, tw, th)
                    out.save(tuned / fp.name, format="PNG")

            vid_ns = tdir / "sr_noaudio.mp4"
            enc = subprocess.run(
                [
                    str(ffmpeg_bin),
                    "-y",
                    "-loglevel",
                    "error",
                    "-framerate",
                    str(fps),
                    "-i",
                    str(tuned / "%06d.png"),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    str(vid_ns),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
            if enc.returncode != 0 or not vid_ns.is_file():
                return False
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            if _mux_audio(vid_ns, src, dst, ffmpeg_bin):
                return True
            try:
                shutil.copy2(vid_ns, dst)
                return dst.is_file()
            except OSError:
                return False
    except Exception as exc:
        log.warning("torch SR pipeline failed: %s", exc)
        return False


def _pil_save_format(path: Path) -> str:
    s = path.suffix.lower()
    if s in (".jpg", ".jpeg"):
        return "JPEG"
    if s == ".webp":
        return "WEBP"
    return "PNG"


def _upscale_image_file(
    src: Path,
    dst: Path,
    *,
    tw: int,
    th: int,
    ffmpeg_dir: Path,
    cuda_device_index: int | None,
) -> bool:
    from PIL import Image

    fmt = _pil_save_format(dst)
    with Image.open(src) as im0:
        rgb0 = im0.convert("RGB")
        sw, sh = rgb0.size
    if not needs_spatial_upscale(sw, sh, tw, th):
        try:
            with Image.open(src) as im1:
                _cover_resize_rgb(im1.convert("RGB"), tw, th).save(dst, format=fmt)
            return True
        except Exception:
            return False

    tmp_v = dst.parent / f"{dst.stem}.sr_tmp.mp4"
    tmp_v2 = dst.parent / f"{dst.stem}.sr_1f.mp4"
    still = dst.parent / f"{dst.stem}_1f.png"
    try:
        ffmpeg_bin = _ffmpeg_bin(ffmpeg_dir)
        with Image.open(src) as im0:
            im0.convert("RGB").save(still, format="PNG")
        subprocess.run(
            [
                str(ffmpeg_bin),
                "-y",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-i",
                str(still),
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(tmp_v),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if _upscale_video_torch(
            tmp_v, tmp_v2, tw=tw, th=th, ffmpeg_dir=ffmpeg_dir, cuda_device_index=cuda_device_index, deadline=None
        ):
            subprocess.run(
                [
                    str(ffmpeg_bin),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(tmp_v2),
                    "-frames:v",
                    "1",
                    str(dst.with_suffix(".png")),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            p = dst.with_suffix(".png")
            if p.is_file():
                with Image.open(p) as imf:
                    imf.convert("RGB").save(dst, format=fmt)
                try:
                    p.unlink()
                except OSError:
                    pass
                return True
        if _upscale_video_ncnn(tmp_v, tmp_v2, tw=tw, th=th, ffmpeg_dir=ffmpeg_dir, deadline=None):
            subprocess.run(
                [
                    str(ffmpeg_bin),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(tmp_v2),
                    "-frames:v",
                    "1",
                    str(dst.with_suffix(".png")),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            p = dst.with_suffix(".png")
            if p.is_file():
                with Image.open(p) as imf:
                    imf.convert("RGB").save(dst, format=fmt)
                try:
                    p.unlink()
                except OSError:
                    pass
                return True
    except Exception as exc:
        log.warning("image SR failed: %s", exc)
    finally:
        for p in (tmp_v, tmp_v2, still):
            try:
                if p.is_file():
                    p.unlink()
            except OSError:
                pass

    try:
        with Image.open(src) as im1:
            _cover_resize_rgb(im1.convert("RGB"), tw, th).save(dst, format=fmt)
        return True
    except Exception:
        return False


def upscale_clip_file(
    src: Path,
    *,
    target_w: int,
    target_h: int,
    mode: str,
    ffmpeg_dir: Path,
    cuda_device_index: int | None = None,
    free_vram_mb: int | None = None,
) -> SpatialUpscaleResult:
    """Upscale a video clip toward ``target_w``×``target_h`` when ``mode == auto``."""
    src = Path(src)
    if mode.strip().lower() != "auto" or not src.is_file():
        return SpatialUpscaleResult(output_path=src, mode_used="off")

    ffmpeg_bin = _ffmpeg_bin(ffmpeg_dir)
    pr = _ffprobe_wh_fps(ffmpeg_bin, src)
    if not pr:
        return SpatialUpscaleResult(output_path=src, mode_used="off")
    sw, sh, _fps = pr
    if not needs_spatial_upscale(sw, sh, target_w, target_h):
        return SpatialUpscaleResult(output_path=src, mode_used="off")

    clip_deadline = None
    ct = _clip_timeout_s()
    if ct is not None:
        clip_deadline = time.monotonic() + ct

    dst_tmp = src.with_suffix(".sr.mp4")
    bak = src.with_suffix(".pre_sr.mp4")
    try_torch = False
    try:
        import torch

        try_torch = (
            pytorch_realesrgan_available()
            and torch.cuda.is_available()
            and (free_vram_mb is None or spatial_vram_budget_ok(free_vram_mb=free_vram_mb))
        )
    except Exception:
        pass
    if try_torch:
        if _upscale_video_torch(
            src,
            dst_tmp,
            tw=target_w,
            th=target_h,
            ffmpeg_dir=ffmpeg_dir,
            cuda_device_index=cuda_device_index,
            deadline=clip_deadline,
        ):
            try:
                if bak.exists():
                    bak.unlink()
                src.rename(bak)
                dst_tmp.rename(src)
            except OSError as exc:
                log.warning("could not replace clip with SR version: %s", exc)
                try:
                    if dst_tmp.is_file():
                        dst_tmp.unlink()
                except OSError:
                    pass
                try:
                    if bak.is_file():
                        bak.rename(src)
                except OSError:
                    pass
                return SpatialUpscaleResult(output_path=src, mode_used="off")
            try:
                if bak.is_file():
                    bak.unlink()
            except OSError:
                pass
            return SpatialUpscaleResult(output_path=src, mode_used="torch")

    if _upscale_video_ncnn(
        src,
        dst_tmp,
        tw=target_w,
        th=target_h,
        ffmpeg_dir=ffmpeg_dir,
        deadline=clip_deadline,
    ):
        try:
            if bak.exists():
                bak.unlink()
            src.rename(bak)
            dst_tmp.rename(src)
        except OSError as exc:
            log.warning("could not replace clip with ncnn SR: %s", exc)
            try:
                if dst_tmp.is_file():
                    dst_tmp.unlink()
            except OSError:
                pass
            try:
                if bak.is_file():
                    bak.rename(src)
            except OSError:
                pass
            return SpatialUpscaleResult(output_path=src, mode_used="off")
        try:
            if bak.is_file():
                bak.unlink()
        except OSError:
            pass
        return SpatialUpscaleResult(output_path=src, mode_used="ncnn")

    try:
        if dst_tmp.is_file():
            dst_tmp.unlink()
    except OSError:
        pass
    return SpatialUpscaleResult(output_path=src, mode_used="off")


def upscale_clips_inplace(
    clip_paths: list[Path],
    *,
    target_w: int,
    target_h: int,
    mode: str,
    ffmpeg_dir: Path,
    cuda_device_index: int | None = None,
    on_clip_progress: Callable[[int, int], None] | None = None,
) -> list[SpatialUpscaleResult]:
    """Apply :func:`upscale_clip_file` to each path; ignores failures per clip."""
    if mode.strip().lower() != "auto":
        return [SpatialUpscaleResult(output_path=Path(p), mode_used="off") for p in clip_paths]

    free_vram_mb: int | None = None
    try:
        import torch

        if torch.cuda.is_available():
            free_b, _ = torch.cuda.mem_get_info()  # type: ignore[no-untyped-call]
            free_vram_mb = int(free_b) // (1024 * 1024)
    except Exception:
        free_vram_mb = None

    job_deadline = None
    jm = _job_max_s()
    if jm is not None:
        job_deadline = time.monotonic() + jm

    results: list[SpatialUpscaleResult] = []
    n_paths = len(clip_paths)
    for i, p in enumerate(clip_paths):
        if job_deadline is not None and time.monotonic() > job_deadline:
            log.warning("spatial upscale job max time exceeded — skipping remaining clips")
            break
        if on_clip_progress is not None and n_paths:
            try:
                on_clip_progress(i + 1, n_paths)
            except Exception:
                pass
        results.append(
            upscale_clip_file(
                Path(p),
                target_w=target_w,
                target_h=target_h,
                mode=mode,
                ffmpeg_dir=ffmpeg_dir,
                cuda_device_index=cuda_device_index,
                free_vram_mb=free_vram_mb,
            )
        )
    while len(results) < len(clip_paths):
        results.append(
            SpatialUpscaleResult(output_path=Path(clip_paths[len(results)]), mode_used="off")
        )
    return results


def maybe_spatial_upscale_path(
    path: Path,
    *,
    target_w: int,
    target_h: int,
    mode: str,
    ffmpeg_dir: Path,
    cuda_device_index: int | None = None,
) -> Path:
    """Upscale *path* (video or image) when ``mode=auto`` and below export size; else return *path*."""
    path = Path(path)
    if mode.strip().lower() != "auto" or not path.is_file():
        return path
    suf = path.suffix.lower()
    free_vram_mb: int | None = None
    try:
        import torch

        if torch.cuda.is_available():
            free_b, _ = torch.cuda.mem_get_info()  # type: ignore[no-untyped-call]
            free_vram_mb = int(free_b) // (1024 * 1024)
    except Exception:
        free_vram_mb = None

    if suf in VIDEO_SUFFIXES:
        r = upscale_clip_file(
            path,
            target_w=target_w,
            target_h=target_h,
            mode=mode,
            ffmpeg_dir=ffmpeg_dir,
            cuda_device_index=cuda_device_index,
            free_vram_mb=free_vram_mb,
        )
        return r.output_path

    if suf in IMAGE_SUFFIXES:
        work = path.parent / f"{path.stem}_aq_sr{path.suffix}"
        if _upscale_image_file(
            path,
            work,
            tw=target_w,
            th=target_h,
            ffmpeg_dir=ffmpeg_dir,
            cuda_device_index=cuda_device_index,
        ):
            try:
                path.unlink()
                work.replace(path)
            except OSError:
                try:
                    if work.is_file():
                        work.unlink()
                except OSError:
                    pass
        return path
    return path
