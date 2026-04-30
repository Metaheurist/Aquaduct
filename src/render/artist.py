from __future__ import annotations

import os
import shutil
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.core.config import AppSettings
from src.core.models_dir import get_models_dir
from src.models.model_manager import resolve_pretrained_load_path
from src.models.torch_dtypes import torch_float16
from src.settings.art_style_presets import ArtStylePreset, art_style_preset_by_id
from src.render.clips import _maybe_enable_slice_inference
from src.util.diffusion_placement import place_diffusion_pipeline
from src.util.memory_budget import release_between_stages
from src.util.utils_vram import vram_guard


@dataclass(frozen=True)
class GeneratedImage:
    path: Path
    prompt: str


def _split_prompt_negative(raw: str) -> tuple[str, str | None]:
    s = (raw or "").strip()
    if "\nNEGATIVE:" in s:
        pos, neg = s.split("\nNEGATIVE:", 1)
        return pos.strip(), (neg.strip() or None)
    return s, None


def _join_prompt_negative(pos: str, neg: str | None) -> str:
    pos = (pos or "").strip()
    if neg and neg.strip():
        return f"{pos}\nNEGATIVE: {neg.strip()}"
    return pos


def _apply_art_style_affixes(raw: str, preset: ArtStylePreset | None) -> str:
    if preset is None:
        return raw
    pos, neg = _split_prompt_negative(raw)
    affix = preset.prompt_affix.strip()
    if affix and affix.lower() not in pos.lower():
        pos = f"{affix}, {pos}"
    extra = preset.negative_affix.strip()
    if extra:
        neg = f"{neg}, {extra}" if neg else extra
    return _join_prompt_negative(pos, neg)


def _blend_reference_images(paths: list[Path], size: tuple[int, int]) -> Image.Image:
    """Average the last few frames in RGB for img2img style continuity."""
    import numpy as np

    w, h = size
    imgs: list[Image.Image] = []
    for p in paths:
        try:
            im = Image.open(p).convert("RGB")
            imgs.append(im.resize((w, h), Image.Resampling.LANCZOS))
        except Exception:
            continue
    if not imgs:
        return Image.new("RGB", (w, h), (128, 128, 128))
    if len(imgs) == 1:
        return imgs[0]
    arr = np.mean([np.asarray(x, dtype=np.float32) for x in imgs], axis=0)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def apply_regenerated_image(regen: list[GeneratedImage], out_path: Path) -> None:
    """Copy or keep a single-image ``generate_images`` result at ``out_path``.

    Do **not** use ``Path.replace`` here: it renames/moves. When the new file path
    equals ``out_path``, ``replace`` can delete the file on Windows. When they
    differ, copy then remove the temp file.
    """
    if not regen:
        return
    src = regen[0].path
    try:
        if src.resolve() == out_path.resolve():
            return
        shutil.copy2(src, out_path)
        try:
            src.unlink()
        except OSError:
            pass
    except Exception:
        pass


def _maybe_disable_safety_checker(pipe, *, allow_nsfw: bool) -> None:
    """When ``allow_nsfw`` is True, disable the diffusion safety classifier (no blacked-out frames)."""
    if not allow_nsfw:
        return
    try:
        pipe.safety_checker = None
    except Exception:
        pass
    try:
        pipe.feature_extractor = None
    except Exception:
        pass


def _place_pipe_on_device(
    pipe,
    cuda_device_index: int | None = None,
    *,
    quant_mode: str | None = None,
) -> None:
    """Move pipeline to GPU/CPU using shared heuristics (VRAM, RAM, optional offload).

    ``quant_mode='cpu_offload'`` forces ``model``-level CPU offload regardless of env policy.
    """
    qm = (quant_mode or "").strip().lower()
    if qm == "cpu_offload":
        place_diffusion_pipeline(pipe, cuda_device_index=cuda_device_index, force_offload="model")
    else:
        place_diffusion_pipeline(pipe, cuda_device_index=cuda_device_index)
    try:
        from debug import debug_enabled, dprint

        if debug_enabled("artist"):
            dprint(
                "artist",
                "diffusion placement",
                f"cuda={cuda_device_index!r}",
                f"quant={qm!r}",
                f"offload={('model' if qm == 'cpu_offload' else None)!r}",
            )
    except Exception:
        pass


def _image_quant_mode_from_settings(app_settings: AppSettings | None) -> str:
    if app_settings is None:
        return "auto"
    return str(getattr(app_settings, "image_quant_mode", "auto") or "auto")


def _fallback_image(prompt: str, out_path: Path, *, size: int = 1024) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (size, size), (10, 10, 16))
    d = ImageDraw.Draw(img)
    # Best-effort font
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()
    txt = (prompt[:220] + "…") if len(prompt) > 220 else prompt
    d.text((40, 36), "PLACEHOLDER (diffusion failed)", fill=(255, 90, 90), font=font)
    d.text((40, 88), "Enable AQUADUCT_ALLOW_PLACEHOLDER_IMAGES=1 to allow these slides.", fill=(140, 140, 150), font=font)
    d.text((40, 140), txt, fill=(240, 240, 240), font=font)
    img.save(out_path)


def _norm_repo_id(model_id: str) -> str:
    return (model_id or "").strip().lower()


def _is_frontier_t2i_repo(mid: str) -> bool:
    """FLUX / SD3 checkpoints ship without ``variant=fp16`` folders; prefer BF16 on CUDA."""
    if "flux" in mid or "/flux." in mid:
        return True
    if "stable-diffusion-3" in mid or "stable-diffusion-3.5" in mid:
        return True
    return False


def _diffusion_dtype_for_quant(quant_mode: str | None, _fp16):
    """Pick a torch dtype for a diffusion pipeline given the requested quant mode."""
    import torch

    qm = (quant_mode or "").strip().lower()
    if qm == "bf16":
        try:
            return torch.bfloat16
        except Exception:
            return _fp16
    if qm in ("fp16", "int8", "nf4_4bit", "cpu_offload"):
        return _fp16
    return None  # "auto" / unknown -> let caller choose model-aware default


def _try_diffusers_quant_config(quant_mode: str | None):
    """Best-effort: build a diffusers ``BitsAndBytesConfig`` for ``int8``/``nf4_4bit``.

    Returns ``None`` when the installed ``diffusers`` build does not expose quantization
    integration, or when ``bitsandbytes`` is unavailable. Callers must always provide a
    safe dtype-only fallback path.
    """
    qm = (quant_mode or "").strip().lower()
    if qm not in ("int8", "nf4_4bit"):
        return None
    try:  # diffusers >=0.30 exposes BitsAndBytesConfig under diffusers.quantizers
        from diffusers import BitsAndBytesConfig as _BnB  # type: ignore

        if qm == "nf4_4bit":
            return _BnB(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
        return _BnB(load_in_8bit=True)
    except Exception:
        return None


def _load_auto_t2i_pipeline(
    model_id: str,
    load_path: str,
    _fp16,
    *,
    quant_mode: str | None = None,
    on_status: Callable[[str], None] | None = None,
):
    import torch
    from diffusers import AutoPipelineForText2Image

    def _status(msg: str) -> None:
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    mid = _norm_repo_id(model_id)
    is_frontier = _is_frontier_t2i_repo(mid)

    # Resolve dtype: explicit quant_mode takes priority; else legacy frontier/non-frontier defaults.
    qdt = _diffusion_dtype_for_quant(quant_mode, _fp16)
    default_dt = (torch.bfloat16 if torch.cuda.is_available() else _fp16) if is_frontier else _fp16
    dt = qdt if qdt is not None else default_dt

    # Attempt experimental quant only when explicitly requested AND diffusers supports it.
    quant_cfg = _try_diffusers_quant_config(quant_mode)
    if quant_cfg is not None:
        _status(f"Loading image pipeline ({(quant_mode or '').upper()}, experimental)…")
        try:
            return AutoPipelineForText2Image.from_pretrained(
                load_path, torch_dtype=dt, low_cpu_mem_usage=True, quantization_config=quant_cfg
            )
        except Exception as e:
            _status(f"Experimental {quant_mode} failed for image ({type(e).__name__}); falling back to dtype path…")

    if is_frontier:
        try:
            return AutoPipelineForText2Image.from_pretrained(
                load_path, torch_dtype=dt, low_cpu_mem_usage=True
            )
        except TypeError:
            return AutoPipelineForText2Image.from_pretrained(load_path, torch_dtype=dt)
    try:
        return AutoPipelineForText2Image.from_pretrained(
            load_path,
            torch_dtype=dt,
            variant="fp16",
            low_cpu_mem_usage=True,
        )
    except OSError:
        try:
            return AutoPipelineForText2Image.from_pretrained(
                load_path, torch_dtype=dt, low_cpu_mem_usage=True
            )
        except TypeError:
            return AutoPipelineForText2Image.from_pretrained(load_path, torch_dtype=dt)
    except TypeError:
        return AutoPipelineForText2Image.from_pretrained(load_path, torch_dtype=dt)


def _load_auto_i2i_pipeline(
    model_id: str,
    load_path: str,
    _fp16,
    *,
    quant_mode: str | None = None,
    on_status: Callable[[str], None] | None = None,
):
    import torch
    from diffusers import AutoPipelineForImage2Image

    def _status(msg: str) -> None:
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    mid = _norm_repo_id(model_id)
    is_frontier = _is_frontier_t2i_repo(mid)

    qdt = _diffusion_dtype_for_quant(quant_mode, _fp16)
    default_dt = (torch.bfloat16 if torch.cuda.is_available() else _fp16) if is_frontier else _fp16
    dt = qdt if qdt is not None else default_dt

    quant_cfg = _try_diffusers_quant_config(quant_mode)
    if quant_cfg is not None:
        _status(f"Loading image pipeline ({(quant_mode or '').upper()}, experimental)…")
        try:
            return AutoPipelineForImage2Image.from_pretrained(
                load_path, torch_dtype=dt, low_cpu_mem_usage=True, quantization_config=quant_cfg
            )
        except Exception as e:
            _status(f"Experimental {quant_mode} failed for image ({type(e).__name__}); falling back to dtype path…")

    if is_frontier:
        try:
            return AutoPipelineForImage2Image.from_pretrained(
                load_path, torch_dtype=dt, low_cpu_mem_usage=True
            )
        except TypeError:
            return AutoPipelineForImage2Image.from_pretrained(load_path, torch_dtype=dt)
    try:
        return AutoPipelineForImage2Image.from_pretrained(
            load_path,
            torch_dtype=dt,
            variant="fp16",
            low_cpu_mem_usage=True,
        )
    except OSError:
        try:
            return AutoPipelineForImage2Image.from_pretrained(
                load_path, torch_dtype=dt, low_cpu_mem_usage=True
            )
        except TypeError:
            return AutoPipelineForImage2Image.from_pretrained(load_path, torch_dtype=dt)
    except TypeError:
        return AutoPipelineForImage2Image.from_pretrained(load_path, torch_dtype=dt)


def _apply_flux_negative_cfg(model_id: str, call_kw: dict) -> None:
    """FLUX uses ``true_cfg_scale`` when a negative prompt is present (guidance may be 0 for Schnell)."""
    mid = _norm_repo_id(model_id)
    if "flux" not in mid or not call_kw.get("negative_prompt"):
        return
    if call_kw.get("true_cfg_scale") is not None:
        return
    call_kw["true_cfg_scale"] = 4.0 if "schnell" in mid else 3.5


# Curated text-to-image repo ids from ``model_manager.model_options`` (video → image models).
# Keep in sync when adding or renaming Hub entries used for ``generate_images``.
CURATED_TEXT2IMAGE_REPO_IDS: frozenset[str] = frozenset(
    {
        "black-forest-labs/flux.1.1-pro-ultra",
        "black-forest-labs/flux.1-dev",
        "black-forest-labs/flux.1-schnell",
        "stabilityai/stable-diffusion-3.5-large",
        "stabilityai/stable-diffusion-3.5-medium",
        "stabilityai/stable-diffusion-3.5-large-turbo",
    }
)


def is_curated_text2image_repo(repo_id: str) -> bool:
    return _norm_repo_id(repo_id) in CURATED_TEXT2IMAGE_REPO_IDS


def _preset_sdxl_turbo(steps: int) -> dict:
    st = max(1, int(steps))
    return {
        "guidance_scale": 0.0,
        "num_inference_steps": st,
        "height": 1024,
        "width": 1024,
    }


def _preset_sd15(steps: int) -> dict:
    st = max(1, int(steps))
    return {
        "guidance_scale": 7.5,
        "num_inference_steps": max(25, st),
        "height": 512,
        "width": 512,
    }


def _preset_sdxl_base(steps: int) -> dict:
    st = max(1, int(steps))
    return {
        "guidance_scale": 7.0,
        "num_inference_steps": max(20, st),
        "height": 1024,
        "width": 1024,
    }


def _preset_flux_schnell(steps: int) -> dict:
    st = max(1, int(steps))
    return {
        "guidance_scale": 0.0,
        "num_inference_steps": max(1, min(st, 4)),
        "height": 1024,
        "width": 1024,
    }


def _preset_flux_dev(steps: int) -> dict:
    st = max(1, int(steps))
    return {
        "guidance_scale": 3.5,
        "num_inference_steps": max(20, min(st, 50)),
        "height": 1024,
        "width": 1024,
    }


def _preset_flux_11_pro_ultra(steps: int) -> dict:
    """BFL 1.1 [pro] ultra: faster sampling than full FLUX.1-dev-class stacks; still uses CFG for negatives."""
    st = max(1, int(steps))
    return {
        "guidance_scale": 3.5,
        "num_inference_steps": max(4, min(st, 24)),
        "height": 1024,
        "width": 1024,
    }


def _preset_sd3_medium(steps: int) -> dict:
    st = max(1, int(steps))
    return {
        "guidance_scale": 7.0,
        "num_inference_steps": max(20, min(st, 50)),
        "height": 1024,
        "width": 1024,
    }


def _preset_sd35_large_turbo(steps: int) -> dict:
    """ADD-distilled 3.5 family; default to a small step count (model card: ~4)."""
    st = max(1, int(steps))
    return {
        "guidance_scale": 1.0,
        "num_inference_steps": max(1, min(st, 4)),
        "height": 1024,
        "width": 1024,
    }


# Exact repo id → preset. Unknown user-typed ids fall through to heuristics below.
_IMAGE_T2I_PRESETS: dict[str, Callable[[int], dict]] = {
    "black-forest-labs/flux.1.1-pro-ultra": _preset_flux_11_pro_ultra,
    "black-forest-labs/flux.1-dev": _preset_flux_dev,
    "black-forest-labs/flux.1-schnell": _preset_flux_schnell,
    "stabilityai/stable-diffusion-3.5-large": _preset_sd3_medium,
    "stabilityai/stable-diffusion-3.5-medium": _preset_sd3_medium,
    "stabilityai/stable-diffusion-3.5-large-turbo": _preset_sd35_large_turbo,
}


def _diffusion_kw_for_model(model_id: str, *, steps: int) -> dict:
    """
    Hyperparameters for ``AutoPipelineForText2Image.__call__``.

    SDXL-Turbo (and similar distilled models) are trained for **CFG = 0** and 1–4 steps.
    **SD 1.5** and **SDXL Base** need **non-zero guidance** and **many more steps**; using
    Turbo settings on them yields **noise-like** outputs.
    """
    key = _norm_repo_id(model_id)
    preset = _IMAGE_T2I_PRESETS.get(key)
    if preset is not None:
        return preset(steps)

    mid = key
    st = max(1, int(steps))

    if (
        "sdxl-turbo" in mid
        or mid.rstrip("/").endswith("/turbo")
        or "lcm" in mid
        or "lightning" in mid
    ):
        return _preset_sdxl_turbo(st)

    if "stable-diffusion-v1-5" in mid or "stable-diffusion-v1-4" in mid or "/v1-4" in mid or "/v1-5" in mid:
        return _preset_sd15(st)

    if "flux" in mid:
        if "1.1" in mid and "ultra" in mid:
            return _preset_flux_11_pro_ultra(st)
        if "schnell" in mid:
            return _preset_flux_schnell(st)
        return _preset_flux_dev(st)

    if "3.5" in mid and "large-turbo" in mid:
        return _preset_sd35_large_turbo(st)

    if "stable-diffusion-3" in mid:
        return _preset_sd3_medium(st)

    if "xl" in mid or "sdxl" in mid:
        return _preset_sdxl_base(st)

    return {
        "guidance_scale": 7.5,
        "num_inference_steps": max(25, st),
        "height": 1024,
        "width": 1024,
    }


def _t2i_call_kw(model_id: str, *, steps: int, app_settings: AppSettings | None) -> dict:
    base = _diffusion_kw_for_model(model_id, steps=steps)
    if app_settings is None:
        return base
    from src.models.inference_profiles import merge_t2i_from_settings

    return merge_t2i_from_settings(model_id, base, app_settings)


def _try_sdxl_turbo(
    model_id: str,
    prompts: list[str],
    out_dir: Path,
    *,
    steps: int = 1,
    allow_nsfw: bool = False,
    on_image_progress: Callable[[int, str], None] | None = None,
    cuda_device_index: int | None = None,
    app_settings: AppSettings | None = None,
) -> list[GeneratedImage]:
    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    qm = _image_quant_mode_from_settings(app_settings)
    pipe = _load_auto_t2i_pipeline(model_id, load_path, _fp16, quant_mode=qm)
    _maybe_disable_safety_checker(pipe, allow_nsfw=allow_nsfw)
    _place_pipe_on_device(pipe, cuda_device_index=cuda_device_index, quant_mode=qm)
    _maybe_enable_slice_inference(pipe)

    n = len(prompts)
    results: list[GeneratedImage] = []
    for i, p in enumerate(prompts, start=1):
        if on_image_progress:
            on_image_progress(int(100 * (i - 1) / max(1, n)), f"Image {i}/{n} (inference)…")
        kw = _t2i_call_kw(model_id, steps=steps, app_settings=app_settings)
        pos, neg = _split_prompt_negative(p)
        call_kw: dict = {"prompt": pos, **kw}
        if neg:
            call_kw["negative_prompt"] = neg
        _apply_flux_negative_cfg(model_id, call_kw)
        img = pipe(**call_kw).images[0]
        out_path = out_dir / f"img_{i:03d}.png"
        img.save(out_path)
        results.append(GeneratedImage(path=out_path, prompt=p))
        if on_image_progress:
            on_image_progress(int(100 * i / max(1, n)), f"Image {i}/{n} saved")

    del pipe
    release_between_stages("after_sdxl_turbo_batch", cuda_device_index=cuda_device_index, variant="cheap")
    return results


def _try_sdxl_turbo_seeded(
    model_id: str,
    prompts: list[str],
    seeds: list[int],
    out_dir: Path,
    *,
    steps: int = 1,
    allow_nsfw: bool = False,
    on_image_progress: Callable[[int, str], None] | None = None,
    cuda_device_index: int | None = None,
    app_settings: AppSettings | None = None,
) -> list[GeneratedImage]:
    import torch

    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    qm = _image_quant_mode_from_settings(app_settings)
    pipe = _load_auto_t2i_pipeline(model_id, load_path, _fp16, quant_mode=qm)
    _maybe_disable_safety_checker(pipe, allow_nsfw=allow_nsfw)
    _place_pipe_on_device(pipe, cuda_device_index=cuda_device_index, quant_mode=qm)
    _maybe_enable_slice_inference(pipe)

    n = len(prompts)
    results: list[GeneratedImage] = []
    for i, (p, seed) in enumerate(zip(prompts, seeds), start=1):
        if on_image_progress:
            on_image_progress(int(100 * (i - 1) / max(1, n)), f"Image {i}/{n} (inference)…")
        dev = "cuda" if str(pipe.device).startswith("cuda") else "cpu"
        gen = torch.Generator(device=dev).manual_seed(int(seed))
        kw = _t2i_call_kw(model_id, steps=steps, app_settings=app_settings)
        pos, neg = _split_prompt_negative(p)
        call_kw: dict = {"prompt": pos, "generator": gen, **kw}
        if neg:
            call_kw["negative_prompt"] = neg
        _apply_flux_negative_cfg(model_id, call_kw)
        img = pipe(**call_kw).images[0]
        out_path = out_dir / f"img_{i:03d}.png"
        img.save(out_path)
        results.append(GeneratedImage(path=out_path, prompt=p))
        if on_image_progress:
            on_image_progress(int(100 * i / max(1, n)), f"Image {i}/{n} saved")

    del pipe
    release_between_stages("after_sdxl_turbo_seeded_batch", cuda_device_index=cuda_device_index, variant="cheap")
    return results


def _try_sdxl_reference_chain(
    model_id: str,
    prompts: list[str],
    seeds: list[int],
    out_dir: Path,
    *,
    preset: ArtStylePreset,
    steps: int = 1,
    allow_nsfw: bool = False,
    on_image_progress: Callable[[int, str], None] | None = None,
    external_reference: Path | None = None,
    external_reference_strength: float = 0.55,
    cuda_device_index: int | None = None,
    app_settings: AppSettings | None = None,
) -> list[GeneratedImage]:
    """
    Img2img chain: frame 0 uses full denoise from random init (strength=1.0); later frames blend the
    average of up to 3 previous outputs for style continuity.
    """
    import numpy as np
    import torch

    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    qm = _image_quant_mode_from_settings(app_settings)
    pipe = _load_auto_i2i_pipeline(model_id, load_path, _fp16, quant_mode=qm)
    _maybe_disable_safety_checker(pipe, allow_nsfw=allow_nsfw)
    _place_pipe_on_device(pipe, cuda_device_index=cuda_device_index, quant_mode=qm)
    _maybe_enable_slice_inference(pipe)

    kw_base = _t2i_call_kw(model_id, steps=steps, app_settings=app_settings)
    w = int(kw_base.get("width", 1024))
    h = int(kw_base.get("height", 1024))
    kw_i2i = {k: v for k, v in kw_base.items() if k not in ("width", "height")}

    n = len(prompts)
    results: list[GeneratedImage] = []
    for i, (p, seed) in enumerate(zip(prompts, seeds), start=1):
        if on_image_progress:
            on_image_progress(int(100 * (i - 1) / max(1, n)), f"Image {i}/{n} (style-continuous)…")
        pos, neg = _split_prompt_negative(p)
        dev = "cuda" if str(pipe.device).startswith("cuda") else "cpu"
        gen = torch.Generator(device=dev).manual_seed(int(seed))
        if i == 1:
            if external_reference is not None and Path(external_reference).exists():
                try:
                    init = Image.open(external_reference).convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
                    strength = float(external_reference_strength)
                    strength = max(0.15, min(0.95, strength))
                except Exception:
                    init = Image.fromarray(np.random.randint(0, 256, (h, w, 3), dtype=np.uint8))
                    strength = 1.0
            else:
                init = Image.fromarray(np.random.randint(0, 256, (h, w, 3), dtype=np.uint8))
                strength = 1.0
        else:
            prev_paths = [results[j - 1].path for j in range(max(1, i - 3), i)]
            init = _blend_reference_images(prev_paths, (w, h))
            strength = float(preset.reference_strength)
        call_kw: dict = {**kw_i2i, "image": init, "strength": strength, "prompt": pos, "generator": gen}
        if neg:
            call_kw["negative_prompt"] = neg
        _apply_flux_negative_cfg(model_id, call_kw)
        img = pipe(**call_kw).images[0]
        out_path = out_dir / f"img_{i:03d}.png"
        img.save(out_path)
        results.append(GeneratedImage(path=out_path, prompt=p))
        if on_image_progress:
            on_image_progress(int(100 * i / max(1, n)), f"Image {i}/{n} saved")

    del pipe
    release_between_stages("after_sdxl_reference_chain_batch", cuda_device_index=cuda_device_index, variant="cheap")
    return results


def _try_external_ref_then_txt2img(
    model_id: str,
    prompts: list[str],
    seeds: list[int],
    out_dir: Path,
    external_reference: Path,
    external_strength: float,
    *,
    steps: int = 1,
    allow_nsfw: bool = False,
    on_image_progress: Callable[[int, str], None] | None = None,
    cuda_device_index: int | None = None,
    app_settings: AppSettings | None = None,
) -> list[GeneratedImage]:
    """First frame: img2img from external reference; remaining frames: text-to-image."""
    import torch

    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    stg = float(external_strength)
    stg = max(0.15, min(0.95, stg))

    qm = _image_quant_mode_from_settings(app_settings)
    pipe_i2i = _load_auto_i2i_pipeline(model_id, load_path, _fp16, quant_mode=qm)
    _maybe_disable_safety_checker(pipe_i2i, allow_nsfw=allow_nsfw)
    _place_pipe_on_device(pipe_i2i, cuda_device_index=cuda_device_index, quant_mode=qm)
    _maybe_enable_slice_inference(pipe_i2i)
    kw_base = _t2i_call_kw(model_id, steps=steps, app_settings=app_settings)
    w = int(kw_base.get("width", 1024))
    h = int(kw_base.get("height", 1024))
    kw_i2i = {k: v for k, v in kw_base.items() if k not in ("width", "height")}

    results: list[GeneratedImage] = []
    n = len(prompts)
    if n < 1:
        del pipe_i2i
        release_between_stages(
            "after_external_ref_empty_batch",
            cuda_device_index=cuda_device_index,
            variant="cheap",
        )
        return results

    if on_image_progress:
        on_image_progress(0, "Image 1/{n} (reference img2img)…".replace("{n}", str(n)))
    try:
        init = Image.open(external_reference).convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        del pipe_i2i
        release_between_stages(
            "after_external_ref_load_fail",
            cuda_device_index=cuda_device_index,
            variant="cheap",
        )
        raise
    p0, seed0 = prompts[0], seeds[0]
    pos, neg = _split_prompt_negative(p0)
    dev = "cuda" if str(pipe_i2i.device).startswith("cuda") else "cpu"
    gen = torch.Generator(device=dev).manual_seed(int(seed0))
    call_kw: dict = {**kw_i2i, "image": init, "strength": stg, "prompt": pos, "generator": gen}
    if neg:
        call_kw["negative_prompt"] = neg
    _apply_flux_negative_cfg(model_id, call_kw)
    img0 = pipe_i2i(**call_kw).images[0]
    out0 = out_dir / "img_001.png"
    img0.save(out0)
    results.append(GeneratedImage(path=out0, prompt=p0))
    del pipe_i2i
    release_between_stages(
        "after_external_ref_img2img_stage",
        cuda_device_index=cuda_device_index,
        variant="cheap",
    )

    if n <= 1:
        if on_image_progress:
            on_image_progress(100, "Image 1/1 saved")
        return results

    pipe_txt = _load_auto_t2i_pipeline(model_id, load_path, _fp16, quant_mode=qm)
    _maybe_disable_safety_checker(pipe_txt, allow_nsfw=allow_nsfw)
    _place_pipe_on_device(pipe_txt, cuda_device_index=cuda_device_index, quant_mode=qm)
    _maybe_enable_slice_inference(pipe_txt)
    dev = "cuda" if str(pipe_txt.device).startswith("cuda") else "cpu"

    for i in range(2, n + 1):
        if on_image_progress:
            on_image_progress(int(100 * (i - 1) / max(1, n)), f"Image {i}/{n} (txt2img)…")
        p, sd = prompts[i - 1], seeds[i - 1]
        pos, neg = _split_prompt_negative(p)
        gen = torch.Generator(device=dev).manual_seed(int(sd))
        kw = _t2i_call_kw(model_id, steps=steps, app_settings=app_settings)
        call_kw2: dict = {"prompt": pos, "generator": gen, **kw}
        if neg:
            call_kw2["negative_prompt"] = neg
        _apply_flux_negative_cfg(model_id, call_kw2)
        img = pipe_txt(**call_kw2).images[0]
        outp = out_dir / f"img_{i:03d}.png"
        img.save(outp)
        results.append(GeneratedImage(path=outp, prompt=p))
        if on_image_progress:
            on_image_progress(int(100 * i / max(1, n)), f"Image {i}/{n} saved")

    del pipe_txt
    release_between_stages(
        "after_external_ref_txt2img_batch",
        cuda_device_index=cuda_device_index,
        variant="cheap",
    )
    return results


def generate_images(
    *,
    sdxl_turbo_model_id: str,
    prompts: list[str],
    out_dir: Path,
    max_images: int | None = None,
    seeds: list[int] | None = None,
    steps: int = 1,
    allow_nsfw: bool = False,
    on_image_progress: Callable[[int, str], None] | None = None,
    art_style_preset_id: str | None = None,
    use_style_continuity: bool = True,
    external_reference_image: Path | None = None,
    external_reference_strength: float = 0.55,
    cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
) -> list[GeneratedImage]:
    """
    Generates images for the provided prompts.

    When ``use_style_continuity`` and more than one prompt, uses img2img with the average of the
    last up to three frames as a style reference (disabled with env ``AQUADUCT_DISABLE_STYLE_REF_CHAIN=1``).
    Falls back to plain text2img if the reference pipeline fails to load.

    On diffusion failure, raises ``RuntimeError`` so the run does not silently
    continue with text-only placeholders. Set env ``AQUADUCT_ALLOW_PLACEHOLDER_IMAGES=1``
    to restore the old placeholder behavior (development only).
    """
    from debug import dprint

    dprint("artist", "generate_images", f"model={sdxl_turbo_model_id!r}", f"n_prompts={len(prompts)}", f"max={max_images}")
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts = [p.strip() for p in prompts if p.strip()]
    if not prompts:
        prompts = ["high-contrast cyberpunk UI, neon, sharp, cinematic, 9:16 composition"]
    if max_images is not None and max_images > 0:
        prompts = prompts[:max_images]

    preset = art_style_preset_by_id(art_style_preset_id)
    prompts = [_apply_art_style_affixes(p, preset) for p in prompts]

    if seeds is not None:
        seeds_eff = [int(s) for s in seeds][: len(prompts)]
        if len(seeds_eff) < len(prompts):
            seeds_eff = seeds_eff + [int(seeds_eff[-1]) + i + 1 for i in range(len(prompts) - len(seeds_eff))]
    else:
        seeds_eff = [9000 + i * 1337 for i in range(len(prompts))]

    disable_chain = os.environ.get("AQUADUCT_DISABLE_STYLE_REF_CHAIN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    try_chain = bool(use_style_continuity) and len(prompts) > 1 and not disable_chain
    ext_path = external_reference_image if external_reference_image and Path(external_reference_image).exists() else None
    ext_strength = float(external_reference_strength)

    with vram_guard():
        try:
            if try_chain:
                try:
                    r = _try_sdxl_reference_chain(
                        sdxl_turbo_model_id,
                        prompts,
                        seeds_eff,
                        out_dir,
                        preset=preset,
                        steps=steps,
                        allow_nsfw=allow_nsfw,
                        on_image_progress=on_image_progress,
                        external_reference=ext_path,
                        external_reference_strength=ext_strength,
                        cuda_device_index=cuda_device_index,
                        app_settings=inference_settings,
                    )
                    dprint("artist", "generate_images done (style chain)", f"count={len(r)}")
                    return r
                except Exception as e_chain:
                    dprint("artist", "reference chain failed; fallback txt2img", str(e_chain))

            if ext_path is not None and len(prompts) >= 1:
                try:
                    r = _try_external_ref_then_txt2img(
                        sdxl_turbo_model_id,
                        prompts,
                        seeds_eff,
                        out_dir,
                        ext_path,
                        ext_strength,
                        steps=steps,
                        allow_nsfw=allow_nsfw,
                        on_image_progress=on_image_progress,
                        cuda_device_index=cuda_device_index,
                        app_settings=inference_settings,
                    )
                    dprint("artist", "generate_images done (external ref + txt2img)", f"count={len(r)}")
                    return r
                except Exception as e_hy:
                    dprint("artist", "external ref hybrid failed; fallback txt2img", str(e_hy))

            r = _try_sdxl_turbo_seeded(
                sdxl_turbo_model_id,
                prompts,
                seeds_eff,
                out_dir,
                steps=steps,
                allow_nsfw=allow_nsfw,
                on_image_progress=on_image_progress,
                cuda_device_index=cuda_device_index,
                app_settings=inference_settings,
            )
            dprint("artist", "generate_images done", f"count={len(r)}")
            return r
        except Exception as e:
            tb = traceback.format_exc()
            dprint("artist", "generate_images diffusion failed", str(e), tb[:8000])
            allow_ph = os.environ.get("AQUADUCT_ALLOW_PLACEHOLDER_IMAGES", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if not allow_ph:
                raise RuntimeError(
                    "Diffusion image generation failed — the pipeline will not use text-only placeholder slides. "
                    "Check that the image model is installed under models/, PyTorch matches your GPU, and VRAM is sufficient. "
                    f"Original error: {e}"
                ) from e
            results: list[GeneratedImage] = []
            nfb = len(prompts)
            for i, p in enumerate(prompts, start=1):
                if on_image_progress:
                    on_image_progress(int(100 * (i - 1) / max(1, nfb)), f"Placeholder {i}/{nfb}…")
                out_path = out_dir / f"img_{i:03d}.png"
                _fallback_image(p, out_path)
                results.append(GeneratedImage(path=out_path, prompt=p))
                if on_image_progress:
                    on_image_progress(int(100 * i / max(1, nfb)), f"Placeholder {i}/{nfb}")
            dprint("artist", "generate_images fallback placeholders", f"count={len(results)}")
            return results

