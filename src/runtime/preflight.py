from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.core.config import AppSettings, get_models
from src.core.models_dir import models_dir_for_app
from src.models.model_manager import model_has_local_snapshot
from src.runtime.model_backend import api_preflight_errors, is_api_mode
from src.render.utils_ffmpeg import find_ffmpeg
from src.runtime.preflight_host_hints import preflight_cpu_busy_warnings, preflight_heavy_repo_ram_warnings
from debug import dprint


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


def _preflight_smoothness_warnings(settings: AppSettings) -> list[str]:
    """Validate Phase 2 smoothness preset against available resources.

    - ``off``    -- silent.
    - ``ffmpeg`` -- always supported (we ship ffmpeg). No warning.
    - ``rife``   -- warn (and let the runtime fall back) when the optional
      package is missing or VRAM headroom looks too tight.
    """
    out: list[str] = []
    v = getattr(settings, "video", None)
    mode = str(getattr(v, "smoothness_mode", "off") or "off").strip().lower()
    if mode != "rife":
        return out
    if is_api_mode(settings):
        out.append(
            "Smoothness 'rife' is for local renders only — API-mode runs ignore the setting "
            "(cloud T2V already encodes at high fps). The pipeline will skip smoothing."
        )
        return out
    try:
        from src.render.temporal_smooth import (
            RIFE_VRAM_BUDGET_MB,
            rife_available,
            rife_vram_budget_ok,
        )
    except Exception:
        return out
    if not rife_available():
        out.append(
            "Smoothness 'rife' is selected but the optional package isn't installed; the pipeline "
            "will fall back to FFmpeg minterpolate. Install ``rife_ncnn_vulkan_python`` to enable RIFE."
        )
        return out
    free_mb: int | None = None
    try:
        import torch

        if torch.cuda.is_available():
            free_b, _ = torch.cuda.mem_get_info()  # type: ignore[no-untyped-call]
            free_mb = int(free_b) // (1024 * 1024)
    except Exception:
        free_mb = None
    if not rife_vram_budget_ok(free_vram_mb=free_mb):
        out.append(
            f"Smoothness 'rife' needs ≥{RIFE_VRAM_BUDGET_MB} MB free VRAM; pipeline will fall back "
            "to FFmpeg minterpolate. Free GPU memory or pick 'ffmpeg' to silence this warning."
        )
    return out


def _check_imports(mods: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for m in mods:
        try:
            __import__(m)
        except Exception:
            missing.append(m)
    return missing


def local_hf_model_snapshot_errors(settings: AppSettings, *, models_dir: Path | None = None) -> list[str]:
    """
    When **Model execution** is **Local**, require on-disk Hugging Face snapshots for the roles
    the pipeline will load (same defaults as ``run_once``).

    Photo mode: Script (LLM) + Image only. Video mode: LLM + Image + Voice + Video (Pro pipeline).
    """
    if is_api_mode(settings):
        return []

    md = models_dir if models_dir is not None else models_dir_for_app(settings)
    models = get_models()
    out: list[str] = []

    def check(label: str, repo: str) -> None:
        rid = (repo or "").strip()
        if not rid:
            out.append(f"Local mode: pick a {label} model on the Model tab.")
            return
        if not model_has_local_snapshot(rid, models_dir=md):
            out.append(
                f"Local mode: {label} model is not downloaded — {rid}. Download it on the Model tab before running."
            )

    llm = (settings.llm_model_id or "").strip() or models.llm_id
    img = (settings.image_model_id or "").strip() or models.sdxl_turbo_id
    voice = (settings.voice_model_id or "").strip() or models.kokoro_id
    vid = (getattr(settings, "video_model_id", "") or "").strip()

    mm = str(getattr(settings, "media_mode", "video") or "video").strip().lower()
    if mm == "photo":
        check("Script (LLM)", llm)
        check("Image", img)
        return out

    check("Script (LLM)", llm)
    check("Image", img)
    check("Voice", voice)
    check("Video (motion)", vid)
    return out


def preflight_check(*, settings: AppSettings, strict: bool = True) -> PreflightResult:
    """
    Validates environment + settings before starting a run.

    If strict=True, any missing requirement returns ok=False (caller should not run).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Settings sanity
    v = settings.video
    if is_api_mode(settings):
        errors.extend(api_preflight_errors(settings))
    else:
        errors.extend(local_hf_model_snapshot_errors(settings))

    if v.width <= 0 or v.height <= 0:
        errors.append(f"Invalid resolution: {v.width}×{v.height}.")
    if not (1 <= int(v.fps) <= 120):
        errors.append(f"Invalid FPS: {v.fps}.")
    pro_on = bool(getattr(v, "pro_mode", False))
    if pro_on and not is_api_mode(settings):
        # Pro mode runs scene-by-scene video (text-to-video and/or image→keyframes→video). Slideshow must be OFF.
        if bool(getattr(v, "use_image_slideshow", True)):
            errors.append("Pro mode disables slideshow stitching — turn off 'Generate images and stitch (slideshow mode)'.")
        vid = str(getattr(settings, "video_model_id", "") or "").strip()
        if not vid:
            errors.append("Pro mode requires a Video (motion) model on the Model tab (e.g. ZeroScope or Stable Video Diffusion).")
        pc = float(getattr(v, "pro_clip_seconds", 0) or 0)
        if pc <= 0:
            errors.append("Pro mode: scene length (seconds) must be > 0.")
        if v.clip_seconds <= 0 and not bool(getattr(v, "use_image_slideshow", True)):
            # Clip seconds isn't used by pro, but keep legacy sanity.
            pass
    elif pro_on and is_api_mode(settings):
        pc = float(getattr(v, "pro_clip_seconds", 0) or 0)
        if pc <= 0:
            errors.append("Pro mode: scene length (seconds) must be > 0.")
        if bool(getattr(v, "use_image_slideshow", True)):
            errors.append("API Pro mode: turn off slideshow — Pro uses cloud text-to-video clips.")
    elif v.use_image_slideshow:
        if v.images_per_video < 1:
            errors.append("Images per video must be >= 1 for slideshow mode.")
        if v.microclip_min_s <= 0 or v.microclip_max_s <= 0 or v.microclip_max_s < v.microclip_min_s:
            errors.append("Micro-scene min/max seconds must be > 0 and max >= min.")
    else:
        if not is_api_mode(settings):
            if v.clips_per_video < 1:
                errors.append("Scenes per video must be >= 1 for motion mode (slideshow off).")
            if v.clip_seconds <= 0:
                errors.append("Seconds per scene must be > 0 for motion mode (slideshow off).")

    # Branding watermark sanity (optional)
    try:
        b = getattr(settings, "branding", None)
        if b and bool(getattr(b, "watermark_enabled", False)):
            p = str(getattr(b, "watermark_path", "") or "").strip()
            if not p:
                errors.append("Watermark is enabled but no logo file is selected.")
            else:
                from pathlib import Path

                wp = Path(p)
                if not wp.exists() or not wp.is_file():
                    errors.append(f"Watermark logo file not found: {p}")
    except Exception:
        pass

    # Python deps required to run end-to-end
    if is_api_mode(settings):
        core_mods = [
            "requests",
            "bs4",
            "lxml",
            "numpy",
            "soundfile",
            "PIL",
            "moviepy",
            "huggingface_hub",
        ]
    else:
        core_mods = [
            "requests",
            "bs4",
            "lxml",
            "numpy",
            "soundfile",
            "PIL",
            "moviepy",
            "huggingface_hub",
            "torch",
            "transformers",
            "accelerate",
            "diffusers",
            "sentencepiece",
            "tiktoken",
            "google.protobuf",  # required by transformers' SentencePieceExtractor (CogVideoX / T5-class video tokenizers)
        ]
        # Video motion (scene) mode needs imageio writer in our implementation
        if not v.use_image_slideshow:
            core_mods.append("imageio")

    missing = _check_imports(core_mods)
    if missing:
        errors.append("Missing Python packages: " + ", ".join(missing))

    allow_cpu_torch = (
        os.environ.get("AQUADUCT_ALLOW_CPU_TORCH_WITH_NVIDIA", "").strip().lower() in ("1", "true", "yes", "on")
    )
    if strict and not is_api_mode(settings) and "torch" not in missing and not allow_cpu_torch:
        try:
            from src.models import torch_install as ti

            if ti.pytorch_cpu_wheel_with_nvidia_gpu_present():
                errors.append(ti.cuda_torch_required_message_for_nvidia_host())
        except Exception:
            pass

    # FFmpeg must be present. (We do NOT auto-download during preflight to avoid hanging the UI.)
    try:
        from src.core.config import get_paths

        paths = get_paths()
        if not find_ffmpeg(paths.ffmpeg_dir):
            errors.append(
                "FFmpeg is not under .Aquaduct_data/.cache/ffmpeg yet. In the desktop app, click Run once — it downloads in the "
                "background on first launch (internet required). CLI: the next `python main.py --once` downloads it "
                "before the pipeline starts. Or install FFmpeg yourself and ensure ffmpeg.exe is discoverable."
            )
    except Exception as e:
        errors.append(f"FFmpeg not available: {e}")

    # Optional host RAM hint for local runs (large checkpoint loads).
    if os.environ.get("AQUADUCT_HOST_RAM_PREFLIGHT", "").strip().lower() in ("1", "true", "yes", "on"):
        if not is_api_mode(settings):
            try:
                import psutil

                vm = psutil.virtual_memory()
                avail_gb = float(vm.available) / (1024.0**3)
                if avail_gb < 4.0:
                    warnings.append(
                        f"Low host RAM headroom (~{avail_gb:.1f} GiB free). Large local models can spike system RAM "
                        "during load — close other apps or use lighter profiles."
                    )
            except Exception:
                pass

    warnings.extend(preflight_heavy_repo_ram_warnings(settings))
    warnings.extend(preflight_cpu_busy_warnings())
    warnings.extend(_preflight_smoothness_warnings(settings))

    if not is_api_mode(settings):
        try:
            from src.runtime.memory_budget_preflight import (
                check_stage_memory_budget,
                check_stage_memory_hard_blocks,
            )

            m = get_models()
            llm = (settings.llm_model_id or "").strip() or m.llm_id
            img = (settings.image_model_id or "").strip() or m.sdxl_turbo_id
            vid = (getattr(settings, "video_model_id", "") or "").strip()
            stages: list[tuple[str, str, str]] = [
                ("Script load", llm, "script"),
                ("Image load", img, "image"),
            ]
            if vid:
                stages.append(("Video load", vid, "video"))
            for lbl, rid, rol in stages:
                warnings.extend(
                    check_stage_memory_budget(stage_label=lbl, role=rol, repo_id=rid or None, settings=settings)
                )
                errors.extend(
                    check_stage_memory_hard_blocks(stage_label=lbl, role=rol, repo_id=rid or None, settings=settings)
                )
        except Exception:
            pass

    # HF token: not always required, but large/gated repos need it.
    def _hf_token_effective() -> str:
        tok = str(getattr(settings, "hf_token", "") or "").strip()
        if tok and bool(getattr(settings, "hf_api_enabled", True)):
            return tok
        return str(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN") or "").strip()

    ht = _hf_token_effective()
    if not is_api_mode(settings) and not ht:
        models = get_models()
        llm = (settings.llm_model_id or "").strip() or models.llm_id
        img = (settings.image_model_id or "").strip() or models.sdxl_turbo_id
        vid = (getattr(settings, "video_model_id", "") or "").strip()

        def _maybe_gated(rid: str) -> bool:
            r = (rid or "").lower()
            needles = (
                "meta-llama",
                "llama-3",
                "llama-2",
                "black-forest-labs/flux.1-dev",
                "wan-ai",
                "gpt-oss",
                "moonshotai",
                "deepseek",
            )
            return any(n in r for n in needles)

        if any(_maybe_gated(x) for x in (llm, img, vid)):
            warnings.append(
                "Hugging Face token is not set — some frontier/gated checkpoints (Llama/Wan/FLUX gated families, …) "
                "may fail to download. Add your HF token on the Settings → API tab or set HF_TOKEN in the environment."
            )
        else:
            warnings.append(
                "No HF token configured (optional) — downloads can be slower or rate limited. Set HF_TOKEN env or paste on Settings → API."
            )

    if strict:
        result = PreflightResult(ok=(len(errors) == 0), errors=errors, warnings=warnings)
        dprint("preflight", f"strict ok={result.ok}", f"errors={len(result.errors)}", f"warnings={len(result.warnings)}")
        return result

    # Non-strict mode: downgrade errors into warnings (best-effort runs)
    if errors:
        warnings.extend(errors)
        errors = []
    result = PreflightResult(ok=True, errors=errors, warnings=warnings)
    dprint("preflight", f"non-strict ok={result.ok}", f"warnings={len(result.warnings)}")
    return result

