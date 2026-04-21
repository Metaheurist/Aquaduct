"""
VRAM-band inference profiles for local models.

When the GPU policy is **auto** (or **single**), we use
``src.util.cuda_device_policy.effective_vram_gb_for_kind`` (same as fit badges) to
select a **band** and merge resolution / steps / length / token caps on top of
model-specific baselines in ``artist``, ``clips``, and ``brain``.

Env overrides (e.g. ``AQUADUCT_LLM_MAX_INPUT_TOKENS``) still take precedence in ``brain``
where that branch exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.core.config import AppSettings

_BAND_LABELS: tuple[tuple[str, str], ...] = (
    ("lt_8", "<8 GB (light)"),
    ("8_12", "8–12 GB (balanced)"),
    ("12_16", "12–16 GB (comfort)"),
    ("16_24", "16–24 GB (heavy)"),
    ("24_40", "24–40 GB (XL)"),
    ("ge_40", "40+ GB (workstation)"),
    ("unknown", "unknown VRAM (conservative)"),
)


def _norm_repo_id(model_id: str) -> str:
    return (model_id or "").strip().lower()


def vram_gb_to_band(vram_gb: float | None) -> str:
    if vram_gb is None or vram_gb <= 0:
        return "unknown"
    v = float(vram_gb)
    if v < 8.0:
        return "lt_8"
    if v < 12.0:
        return "8_12"
    if v < 16.0:
        return "12_16"
    if v < 24.0:
        return "16_24"
    if v < 40.0:
        return "24_40"
    return "ge_40"


def band_display_name(band: str) -> str:
    for k, lab in _BAND_LABELS:
        if k == band:
            return lab
    return band


def resolve_effective_vram_gb(*, kind: str, settings: AppSettings) -> float | None:
    try:
        from src.models.hardware import list_cuda_gpus
        from src.util.cuda_device_policy import effective_vram_gb_for_kind

        gpus = list_cuda_gpus()
        if not gpus:
            return None
        return effective_vram_gb_for_kind(kind, gpus, settings)
    except Exception:
        return None


@dataclass(frozen=True)
class ScriptProfile:
    label: str
    max_input_tokens: int
    max_new_tokens: int


@dataclass(frozen=True)
class ImageProfile:
    label: str
    width: int
    height: int
    num_inference_steps: int | None
    guidance_scale: float | None


@dataclass(frozen=True)
class VideoProfile:
    label: str
    num_frames: int | None
    height: int | None
    width: int | None
    num_inference_steps: int | None
    # guidance, frame_rate, negative_prompt, decode_*, etc.
    extra: dict[str, Any] = field(default_factory=dict)

    def as_merge_dict(self) -> dict[str, Any]:
        d = {**self.extra}
        for k, v in (
            ("num_frames", self.num_frames),
            ("height", self.height),
            ("width", self.width),
            ("num_inference_steps", self.num_inference_steps),
        ):
            if v is not None:
                d[k] = v
        return d


@dataclass(frozen=True)
class VoiceProfile:
    label: str
    extra: dict[str, Any] = field(default_factory=dict)


def _base_script_bands() -> dict[str, ScriptProfile]:
    return {
        "lt_8": ScriptProfile("script-lt8", 1024, 384),
        "8_12": ScriptProfile("script-8-12", 1536, 512),
        "12_16": ScriptProfile("script-12-16", 2048, 650),
        "16_24": ScriptProfile("script-16-24", 3072, 768),
        "24_40": ScriptProfile("script-24-40", 4096, 900),
        "ge_40": ScriptProfile("script-ge40", 8192, 1024),
        "unknown": ScriptProfile("script-unknown", 1024, 384),
    }


def pick_script_profile(repo_id: str, vram_gb: float | None) -> ScriptProfile:
    b = vram_gb_to_band(vram_gb)
    m = _norm_repo_id(repo_id)
    base = _base_script_bands()
    p = base.get(b) or base["unknown"]
    if m == "deepseek-ai/deepseek-v3":
        return ScriptProfile(f"deepseek-{p.label}", min(p.max_input_tokens, 2048), min(p.max_new_tokens, 512))
    if "miqu" in m or "midnight-miqu" in m:
        mit = 1024 if b in ("lt_8", "unknown", "8_12") else min(p.max_input_tokens, 1536)
        return ScriptProfile(f"miqu-{p.label}", mit, min(p.max_new_tokens, 512))
    if "fimbulvetr" in m:
        return ScriptProfile(f"fimbulvetr-{p.label}", p.max_input_tokens, p.max_new_tokens)
    if m == "qwen/qwen3-14b" or m == "qwen/qwen3-14b-instruct" or ("qwen3" in m and "14" in m.replace(" ", "")):
        return ScriptProfile(f"qwen3-14b-{p.label}", p.max_input_tokens, p.max_new_tokens)
    return ScriptProfile(p.label, p.max_input_tokens, p.max_new_tokens)


def _ip_flux_11() -> dict[str, ImageProfile]:
    return {
        "lt_8": ImageProfile("flux-11-480p", 512, 768, 8, 3.5),
        "8_12": ImageProfile("flux-11-720p", 640, 1024, 12, 3.5),
        "12_16": ImageProfile("flux-11-hd", 768, 1280, 16, 3.5),
        "16_24": ImageProfile("flux-11-pro", 896, 1536, 20, 3.5),
        "24_40": ImageProfile("flux-11-2k", 1024, 1920, 24, 3.5),
        "ge_40": ImageProfile("flux-11-max", 1024, 1920, 24, 3.5),
        "unknown": ImageProfile("flux-11-safe", 512, 768, 8, 3.5),
    }


def _ip_flux_dev() -> dict[str, ImageProfile]:
    return {
        "lt_8": ImageProfile("flux-dev-512", 512, 512, 20, 3.5),
        "8_12": ImageProfile("flux-dev-72", 576, 1024, 24, 3.5),
        "12_16": ImageProfile("flux-dev-hd", 720, 1280, 28, 3.5),
        "16_24": ImageProfile("flux-dev-1k", 832, 1216, 32, 3.5),
        "24_40": ImageProfile("flux-dev-1k+", 1024, 1024, 40, 3.5),
        "ge_40": ImageProfile("flux-dev-full", 1024, 1024, 50, 3.5),
        "unknown": ImageProfile("flux-dev-safe", 512, 512, 20, 3.5),
    }


def _ip_flux_schnell() -> dict[str, ImageProfile]:
    return {
        "lt_8": ImageProfile("flux-s-512", 512, 512, 2, 0.0),
        "8_12": ImageProfile("flux-s-7", 640, 1024, 3, 0.0),
        "12_16": ImageProfile("flux-s-hd", 768, 1280, 4, 0.0),
        "16_24": ImageProfile("flux-s-1k", 1024, 1024, 4, 0.0),
        "24_40": ImageProfile("flux-s-1k+", 1024, 1280, 4, 0.0),
        "ge_40": ImageProfile("flux-s-full", 1024, 1024, 4, 0.0),
        "unknown": ImageProfile("flux-s-safe", 512, 512, 2, 0.0),
    }


def _ip_sd35_large() -> dict[str, ImageProfile]:
    return {
        "lt_8": ImageProfile("sd35-L-64", 512, 512, 22, 7.0),
        "8_12": ImageProfile("sd35-L-8", 768, 768, 25, 7.0),
        "12_16": ImageProfile("sd35-L-10", 832, 1216, 28, 7.0),
        "16_24": ImageProfile("sd35-L-1k", 1024, 1024, 32, 7.0),
        "24_40": ImageProfile("sd35-L-12", 1024, 1280, 40, 7.0),
        "ge_40": ImageProfile("sd35-L-full", 1024, 1024, 50, 7.0),
        "unknown": ImageProfile("sd35-L-safe", 512, 512, 22, 7.0),
    }


def _ip_sd35_medium() -> dict[str, ImageProfile]:
    return {
        "lt_8": ImageProfile("sd35-M-64", 512, 512, 22, 7.0),
        "8_12": ImageProfile("sd35-M-8", 640, 1024, 25, 7.0),
        "12_16": ImageProfile("sd35-M-10", 768, 1024, 28, 7.0),
        "16_24": ImageProfile("sd35-M-1k", 1024, 1024, 32, 7.0),
        "24_40": ImageProfile("sd35-M-12", 1024, 1280, 40, 7.0),
        "ge_40": ImageProfile("sd35-M-full", 1024, 1024, 50, 7.0),
        "unknown": ImageProfile("sd35-M-safe", 512, 512, 22, 7.0),
    }


def _ip_sd35_turbo() -> dict[str, ImageProfile]:
    return {
        "lt_8": ImageProfile("sd35-t-64", 512, 512, 2, 1.0),
        "8_12": ImageProfile("sd35-t-8", 640, 1024, 2, 1.0),
        "12_16": ImageProfile("sd35-t-10", 768, 1024, 3, 1.0),
        "16_24": ImageProfile("sd35-t-1k", 1024, 1024, 4, 1.0),
        "24_40": ImageProfile("sd35-t-12", 1024, 1280, 4, 1.0),
        "ge_40": ImageProfile("sd35-t-full", 1024, 1024, 4, 1.0),
        "unknown": ImageProfile("sd35-t-safe", 512, 512, 2, 1.0),
    }


def _image_table(repo_id: str) -> dict[str, ImageProfile]:
    m = _norm_repo_id(repo_id)
    if "1.1" in m and "ultra" in m and "flux" in m:
        return _ip_flux_11()
    if "schnell" in m and "flux" in m:
        return _ip_flux_schnell()
    if m == "black-forest-labs/flux.1-dev" or ("/flux" in m and "dev" in m and "schnell" not in m and "1.1" not in m):
        return _ip_flux_dev()
    if "stable-diffusion-3.5" in m and "large-turbo" in m:
        return _ip_sd35_turbo()
    if "stable-diffusion-3.5" in m and "large" in m and "turbo" not in m:
        return _ip_sd35_large()
    if "stable-diffusion-3" in m or "stable-diffusion-3.5" in m:
        return _ip_sd35_medium()
    return _ip_flux_dev()


def pick_image_profile(repo_id: str, vram_gb: float | None) -> ImageProfile:
    b = vram_gb_to_band(vram_gb)
    t = _image_table(repo_id)
    return t.get(b) or t.get("unknown") or next(iter(t.values()))


def _ltx2_neg() -> dict[str, Any]:
    return {
        "guidance_scale": 4.0,
        "frame_rate": 24.0,
        "negative_prompt": (
            "shaky, glitchy, low quality, worst quality, deformed, distorted, disfigured, "
            "motion smear, motion artifacts, fused fingers, bad anatomy, weird hand, ugly, "
            "transition, static"
        ),
    }


def _vp_wan() -> dict[str, VideoProfile]:
    g = {"guidance_scale": 5.0}
    return {
        "lt_8": VideoProfile("wan-360p", 12, 320, 576, 30, g),
        "8_12": VideoProfile("wan-420p", 17, 400, 704, 30, g),
        "12_16": VideoProfile("wan-480p", 25, 480, 832, 30, g),
        "16_24": VideoProfile("wan-480p-long", 49, 480, 832, 30, g),
        "24_40": VideoProfile("wan-720p", 65, 720, 1280, 30, g),
        "ge_40": VideoProfile("wan-720p-max", 97, 720, 1280, 30, g),
        "unknown": VideoProfile("wan-safe", 12, 320, 576, 30, g),
    }


def _vp_mochi() -> dict[str, VideoProfile]:
    g = {"guidance_scale": 3.5}
    # Mochi infers resolution from the pipeline; only vary frame count and steps by band.
    return {
        "lt_8": VideoProfile("mochi-32f", 32, None, None, 24, g),
        "8_12": VideoProfile("mochi-64f", 64, None, None, 26, g),
        "12_16": VideoProfile("mochi-120f", 120, None, None, 28, g),
        "16_24": VideoProfile("mochi-180f", 180, None, None, 28, g),
        "24_40": VideoProfile("mochi-240f", 240, None, None, 28, g),
        "ge_40": VideoProfile("mochi-300f", 300, None, None, 28, g),
        "unknown": VideoProfile("mochi-safe", 32, None, None, 24, g),
    }


def _vp_cog() -> dict[str, VideoProfile]:
    g = {"guidance_scale": 6.0}
    # CogVideoX 5B defaults resolution inside the loaded pipeline; band only scales frames / steps.
    return {
        "lt_8": VideoProfile("cog-9f", 9, None, None, 40, g),
        "8_12": VideoProfile("cog-17f", 17, None, None, 45, g),
        "12_16": VideoProfile("cog-25f", 25, None, None, 50, g),
        "16_24": VideoProfile("cog-33f", 33, None, None, 50, g),
        "24_40": VideoProfile("cog-41f", 41, None, None, 50, g),
        "ge_40": VideoProfile("cog-49f", 49, None, None, 50, g),
        "unknown": VideoProfile("cog-safe", 9, None, None, 40, g),
    }


def _vp_hunyuan() -> dict[str, VideoProfile]:
    g = {"guidance_scale": 6.0}
    return {
        "lt_8": VideoProfile("hy-17s", 17, 360, 640, 30, g),
        "8_12": VideoProfile("hy-25s", 25, 480, 848, 32, g),
        "12_16": VideoProfile("hy-33s", 33, 512, 896, 35, g),
        "16_24": VideoProfile("hy-41s", 41, 544, 960, 35, g),
        "24_40": VideoProfile("hy-49s", 49, 544, 960, 35, g),
        "ge_40": VideoProfile("hy-61s", 61, 544, 960, 35, g),
        "unknown": VideoProfile("hy-safe", 17, 400, 704, 30, g),
    }


def _vp_ltx2() -> dict[str, VideoProfile]:
    ex0 = _ltx2_neg()
    return {
        "lt_8": VideoProfile("ltx2-ld", 17, 512, 768, 40, dict(ex0)),
        "8_12": VideoProfile("ltx2-sd", 25, 720, 1280, 40, dict(ex0)),
        "12_16": VideoProfile("ltx2-hd", 33, 1024, 1792, 40, dict(ex0)),
        "16_24": VideoProfile("ltx2-fhd", 49, 1280, 2304, 40, dict(ex0)),
        "24_40": VideoProfile("ltx2-4k", 97, 2176, 3840, 40, dict(ex0)),
        "ge_40": VideoProfile("ltx2-4k-long", 121, 2176, 3840, 40, dict(ex0)),
        "unknown": VideoProfile("ltx2-safe", 17, 512, 768, 40, dict(ex0)),
    }


def _video_table(repo_id: str) -> dict[str, VideoProfile]:
    m = _norm_repo_id(repo_id)
    if "wan" in m and "wan2" in m:
        return _vp_wan()
    if "mochi" in m:
        return _vp_mochi()
    if "cogvideox" in m and "5b" in m:
        return _vp_cog()
    if "hunyuanvideo" in m:
        return _vp_hunyuan()
    if "ltx-2" in m:
        return _vp_ltx2()
    return _vp_cog()


def pick_video_profile(repo_id: str, vram_gb: float | None) -> VideoProfile:
    b = vram_gb_to_band(vram_gb)
    t = _video_table(repo_id)
    return t.get(b) or t.get("unknown") or next(iter(t.values()))


def _voice_bands() -> list[str]:
    return [b for b, _ in _BAND_LABELS]


def _voice_kokoro() -> dict[str, VoiceProfile]:
    ex: dict[str, Any] = {}
    return {b: VoiceProfile(f"kokoro-{b}", ex) for b in _voice_bands()}


def _voice_moss() -> dict[str, VoiceProfile]:
    ex: dict[str, Any] = {}
    return {b: VoiceProfile(f"moss-{b}", ex) for b in _voice_bands()}


def pick_voice_profile(repo_id: str, vram_gb: float | None) -> VoiceProfile:
    b = vram_gb_to_band(vram_gb)
    m = _norm_repo_id(repo_id)
    t = _voice_moss() if "moss" in m and "voice" in m else _voice_kokoro()
    return t.get(b) or t.get("unknown") or next(iter(t.values()))


def merge_t2i_kwargs(base: dict[str, Any], repo_id: str, vram_gb: float | None) -> dict[str, Any]:
    p = pick_image_profile(repo_id, vram_gb)
    out = dict(base)
    out["width"] = p.width
    out["height"] = p.height
    if p.num_inference_steps is not None:
        out["num_inference_steps"] = int(p.num_inference_steps)
    if p.guidance_scale is not None:
        out["guidance_scale"] = float(p.guidance_scale)
    return out


def merge_t2v_kwargs(base: dict[str, Any], repo_id: str, vram_gb: float | None) -> dict[str, Any]:
    p = pick_video_profile(repo_id, vram_gb)
    m = {**base, **p.as_merge_dict()}
    if "ltx-2" in _norm_repo_id(repo_id):
        nf = int(m.get("num_frames", 0) or 0)
        while (nf - 1) % 8 != 0 and nf < 1000:
            nf += 1
        m["num_frames"] = nf
    return m


def merge_t2i_from_settings(model_id: str, base: dict[str, Any], settings: AppSettings) -> dict[str, Any]:
    v = resolve_effective_vram_gb(kind="image", settings=settings)
    return merge_t2i_kwargs(base, model_id, v)


def merge_t2v_from_settings(model_id: str, base: dict[str, Any], settings: AppSettings) -> dict[str, Any]:
    v = resolve_effective_vram_gb(kind="video", settings=settings)
    return merge_t2v_kwargs(base, model_id, v)


def format_inference_profile_report(settings: AppSettings) -> str:
    try:
        from src.util.cuda_device_policy import resolve_device_plan

        from src.models.hardware import list_cuda_gpus

        gpus = list_cuda_gpus()
        plan = resolve_device_plan(gpus, settings) if gpus else None
    except Exception:
        gpus = []
        plan = None
    sm = (getattr(settings, "gpu_selection_mode", "auto") or "auto").strip().lower()
    lines: list[str] = [f"GPU policy={sm!r} | CUDA GPUs detected={len(gpus)}"]
    if plan is not None and gpus:
        lines.append(
            f"device_plan: script→cuda:{plan.llm_device_index} | "
            f"image/video→cuda:{plan.diffusion_device_index} | voice→cuda:{plan.voice_device_index}"
        )
    for role, kind, get_id in (
        ("Script (LLM)", "script", lambda: (settings.llm_model_id or "").strip() or _fallback_llm()),
        ("Image (T2I)", "image", lambda: (settings.image_model_id or "").strip() or _fallback_img()),
        ("Video (T2V)", "video", lambda: (getattr(settings, "video_model_id", None) or "").strip() or _fallback_vid()),
        ("Voice (TTS)", "voice", lambda: (settings.voice_model_id or "").strip() or _fallback_voice()),
    ):
        rid = get_id()
        v = resolve_effective_vram_gb(kind=kind, settings=settings) if gpus else None
        b = vram_gb_to_band(v)
        bname = band_display_name(b)
        vlab = f"{v:.1f} GiB" if v is not None else "n/a"
        if kind == "script":
            sp = pick_script_profile(rid, v)
            lines.append(
                f"{role}: repo={rid!r} | effective VRAM≈{vlab} (band {b} — {bname}) | profile={sp.label!r} | "
                f"max_input_tokens={sp.max_input_tokens} | max_new_tokens={sp.max_new_tokens}"
            )
        elif kind == "image":
            ip = pick_image_profile(rid, v)
            lines.append(
                f"{role}: repo={rid!r} | effective VRAM≈{vlab} (band {b} — {bname}) | profile={ip.label!r} | "
                f"{ip.width}x{ip.height} | steps={ip.num_inference_steps} | guidance={ip.guidance_scale}"
            )
        elif kind == "video":
            vp = pick_video_profile(rid, v)
            d = {k: vp.as_merge_dict().get(k) for k in ("num_frames", "height", "width", "num_inference_steps", "frame_rate", "guidance_scale")}
            lines.append(
                f"{role}: repo={rid!r} | effective VRAM≈{vlab} (band {b} — {bname}) | profile={vp.label!r} | "
                f"{json.dumps({k: v2 for k, v2 in d.items() if v2 is not None}, sort_keys=True)}"
            )
        else:
            voi = pick_voice_profile(rid, v)
            lines.append(
                f"{role}: repo={rid!r} | effective VRAM≈{vlab} (band {b} — {bname}) | profile={voi.label!r}"
            )
    lines.append(
        "Autofit algorithm: per-role VRAM = GPU chosen by policy (auto=max-VRAM card for image/video, "
        "heuristic compute for script when policy is auto) → map to band → merge profile on model baseline."
    )
    return "\n".join(lines)


def _fallback_llm() -> str:
    try:
        from src.core.config import get_models

        return get_models().llm_id
    except Exception:
        return "Qwen/Qwen3-14B"


def _fallback_img() -> str:
    try:
        from src.core.config import get_models

        return get_models().sdxl_turbo_id
    except Exception:
        return "black-forest-labs/FLUX.1-schnell"


def _fallback_vid() -> str:
    return "THUDM/CogVideoX-5b"


def _fallback_voice() -> str:
    try:
        from src.core.config import get_models

        return get_models().kokoro_id
    except Exception:
        return "hexgrad/Kokoro-82M"


def log_inference_profiles_for_run(settings: AppSettings) -> None:
    try:
        text = format_inference_profile_report(settings)
        for line in text.splitlines():
            print(f"[Aquaduct][inference_profile] {line}", flush=True)
    except Exception as e:
        print(f"[Aquaduct][inference_profile] (report failed: {e})", flush=True)
    try:
        from debug import dprint

        dprint("inference_profile", "report", format_inference_profile_report(settings)[:12_000])
    except Exception:
        pass
