from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.core.config import AppSettings

import re

QuantMode = Literal["auto", "bf16", "fp16", "int8", "nf4_4bit", "cpu_offload"]
QuantRole = Literal["script", "image", "video", "voice"]


def _norm_mode(raw: object, *, default: QuantMode = "auto") -> QuantMode:
    s = str(raw or "").strip().lower()
    if s in ("auto", "bf16", "fp16", "int8", "nf4_4bit", "cpu_offload"):
        return s  # type: ignore[return-value]
    if s in ("4bit", "bnb4", "nf4"):
        return "nf4_4bit"
    if s in ("8bit", "bnb8", "int-8"):
        return "int8"
    if s in ("offload", "cpu-offload", "cpu"):
        return "cpu_offload"
    return default


def mode_label(mode: QuantMode) -> str:
    return {
        "auto": "Auto",
        "bf16": "BF16",
        "fp16": "FP16",
        "int8": "INT8",
        "nf4_4bit": "NF4 4-bit",
        "cpu_offload": "CPU offload",
    }.get(mode, str(mode))


@dataclass(frozen=True)
class ModeOption:
    mode: QuantMode
    label: str
    enabled: bool
    tooltip: str


def supported_quant_modes(*, role: QuantRole, repo_id: str = "") -> tuple[ModeOption, ...]:
    """
    Mode list for a role. This is conservative and does not assume optional quant backends exist.
    Runtime loaders should still feature-detect and fall back if a requested mode is unsupported.
    """
    r = (role or "script").strip().lower()
    rid = (repo_id or "").strip().lower()

    if r == "script":
        return (
            ModeOption("auto", "Auto (fit this GPU)", True, "Pick the best mode based on effective VRAM for the Script role."),
            ModeOption("bf16", "BF16 (quality)", True, "Full-precision-ish (bf16) on CUDA when supported; may OOM on smaller GPUs."),
            ModeOption("fp16", "FP16 (quality)", True, "Half precision weights; may still OOM depending on model size and prompt length."),
            ModeOption("int8", "INT8 (lower VRAM)", True, "Bitsandbytes 8-bit (if installed). Falls back automatically on failure."),
            ModeOption("nf4_4bit", "NF4 4-bit (lowest VRAM)", True, "Bitsandbytes 4-bit NF4. Best for tight VRAM; small quality hit."),
        )

    if r in ("image", "video"):
        # Diffusers quantization varies by pipeline; keep offload + dtype as stable choices.
        return (
            ModeOption("auto", "Auto (dtype + offload)", True, "Pick dtype/offload based on effective VRAM for this role."),
            ModeOption("bf16", "BF16 (quality)", True, "Prefer bf16 on CUDA for frontier pipelines (FLUX/SD3 family)."),
            ModeOption("fp16", "FP16 (default)", True, "Standard diffusion fp16 load when supported."),
            ModeOption(
                "int8",
                "INT8 (experimental)",
                True,
                "Experimental: diffusion quantization support depends on installed diffusers/torch stack. Will fall back on failure.",
            ),
            ModeOption("cpu_offload", "CPU offload (VRAM saver)", True, "Force CPU offload placement (slower, lower peak VRAM)."),
        )

    # voice
    if "kokoro" in rid:
        return (
            ModeOption("auto", "Auto", True, "Kokoro uses its own pipeline; quant modes are mostly ignored."),
            ModeOption("fp16", "FP16 (ignored)", False, "Not supported for Kokoro pipeline; kept for consistency."),
            ModeOption("bf16", "BF16 (ignored)", False, "Not supported for Kokoro pipeline; kept for consistency."),
            ModeOption("int8", "INT8 (ignored)", False, "Not supported for Kokoro pipeline; kept for consistency."),
            ModeOption("nf4_4bit", "NF4 4-bit (ignored)", False, "Not supported for Kokoro pipeline; kept for consistency."),
        )
    return (
        ModeOption("auto", "Auto", True, "Pick the best mode for this role (usually dtype-based)."),
        ModeOption("bf16", "BF16", True, "Use bf16 on CUDA when supported."),
        ModeOption("fp16", "FP16", True, "Use fp16 on CUDA when supported."),
        ModeOption("int8", "INT8 (experimental)", True, "Experimental: depends on backend support; will fall back."),
        ModeOption("nf4_4bit", "NF4 4-bit (experimental)", True, "Experimental: depends on backend support; will fall back."),
    )


def manual_quant_modes_low_to_high(*, role: QuantRole, repo_id: str = "") -> tuple[QuantMode, ...]:
    """
    Enabled manual modes only (no ``auto``), ordered **low VRAM → higher quality** for the Model tab slider.

    Kokoro voice rows typically return an empty tuple because every manual option is disabled there.
    """
    opts = supported_quant_modes(role=role, repo_id=repo_id)
    by_mode: dict[QuantMode, ModeOption] = {o.mode: o for o in opts}
    r = (role or "script").strip().lower()
    rid = (repo_id or "").strip().lower()

    if r in ("image", "video"):
        order: tuple[QuantMode, ...] = ("cpu_offload", "int8", "fp16", "bf16")
    elif r == "voice" and "kokoro" in rid:
        return ()
    else:
        # script, or non-Kokoro voice (MOSS, etc.)
        order = ("nf4_4bit", "int8", "fp16", "bf16")

    out: list[QuantMode] = []
    for m in order:
        o = by_mode.get(m)
        if o is not None and o.enabled and m != "auto":
            out.append(m)
    return tuple(out)


def index_of_manual_mode(modes: tuple[QuantMode, ...], mode: QuantMode | str) -> int:
    """Index of ``mode`` in ``modes``, or ``0`` if unknown / auto / missing."""
    m = _norm_mode(mode)
    if m == "auto" or not modes:
        return 0
    try:
        return modes.index(m)  # type: ignore[arg-type]
    except ValueError:
        return 0


def manual_mode_at_index(modes: tuple[QuantMode, ...], index: int) -> QuantMode:
    if not modes:
        return "auto"
    i = max(0, min(int(index), len(modes) - 1))
    return modes[i]


def normalize_settings_quant_modes(settings: AppSettings) -> AppSettings:
    """
    Normalize quant mode strings in AppSettings. Callers can use this to sanitize
    older settings payloads when coming from untrusted JSON sources.
    """
    from dataclasses import replace

    return replace(
        settings,
        script_quant_mode=_norm_mode(getattr(settings, "script_quant_mode", "auto")),
        image_quant_mode=_norm_mode(getattr(settings, "image_quant_mode", "auto")),
        video_quant_mode=_norm_mode(getattr(settings, "video_quant_mode", "auto")),
        voice_quant_mode=_norm_mode(getattr(settings, "voice_quant_mode", "auto")),
        auto_quant_downgrade_on_failure=bool(getattr(settings, "auto_quant_downgrade_on_failure", True)),
    )


@dataclass(frozen=True)
class PredictedVram:
    low_gb: float | None
    high_gb: float | None
    rationale: str

    def display(self, *, mode: QuantMode) -> str:
        if self.low_gb is None or self.high_gb is None:
            return "—"
        if abs(self.high_gb - self.low_gb) < 0.2:
            return f"~ {self.high_gb:.0f} GB ({mode_label(mode)})"
        return f"~ {self.low_gb:.0f}-{self.high_gb:.0f} GB ({mode_label(mode)})"


def predict_vram_gb(*, role: QuantRole, repo_id: str, base_low_gb: float | None, base_high_gb: float | None, mode: QuantMode) -> PredictedVram:
    """
    Coarse VRAM estimate based on an existing heuristic hint plus a quant multiplier.
    This is intentionally conservative and should be presented as an estimate only.
    """
    if base_low_gb is None or base_high_gb is None:
        return PredictedVram(None, None, "Base VRAM estimate unavailable.")
    m = _norm_mode(mode)
    r = (role or "script").strip().lower()

    # Multipliers: relative to fp16/bf16 baseline.
    # LLM weights dominate; diffusion activations dominate more often, so changes are smaller.
    if r == "script":
        mult = {
            "auto": 1.0,
            "bf16": 1.0,
            "fp16": 1.0,
            "int8": 0.62,
            "nf4_4bit": 0.38,
            "cpu_offload": 1.0,
        }.get(m, 1.0)
        why = "LLM weight memory scales with quantization; prompt length still matters."
    else:
        mult = {
            "auto": 1.0,
            "bf16": 1.0,
            "fp16": 1.0,
            "int8": 0.85,
            "nf4_4bit": 0.85,
            "cpu_offload": 0.70,
        }.get(m, 1.0)
        why = "Diffusion peak VRAM includes activations; quant/offload effects are smaller and model-dependent."

    lo = max(0.0, float(base_low_gb) * float(mult))
    hi = max(lo, float(base_high_gb) * float(mult))
    rid = (repo_id or "").strip()
    if rid:
        why = f"{why} Repo: {rid}."
    return PredictedVram(lo, hi, why)


def parse_vram_hint_gb(text: str) -> tuple[float | None, float | None]:
    """
    Parse a ``vram_requirement_hint()``-style string into a (low, high) range.

    Examples:
    - "~ 6-8 GB VRAM" -> (6, 8)
    - "~ 10-14 GB VRAM" -> (10, 14)
    - "~ 24-40+ GB VRAM" -> (24, 40)
    """
    s = str(text or "").strip().lower()
    if not s or s == "--" or s == "—":
        return None, None
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", s)]
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], nums[0]
    return nums[0], nums[1]


def pick_auto_mode(*, role: QuantRole, repo_id: str, vram_gb: float | None, cuda_ok: bool) -> QuantMode:
    """
    Choose a best-effort mode given an effective VRAM budget.
    """
    if not cuda_ok or vram_gb is None or vram_gb <= 0:
        if role in ("image", "video"):
            return "cpu_offload"
        return "fp16"
    v = float(vram_gb)
    r = (role or "script").strip().lower()

    if r == "script":
        # Prefer quality when plenty of headroom.
        if v >= 24:
            return "bf16"
        if v >= 16:
            return "fp16"
        if v >= 10:
            return "int8"
        return "nf4_4bit"
    # diffusion/video/voice
    if v >= 16:
        return "bf16"
    if v >= 10:
        return "fp16"
    return "cpu_offload"


def resolve_quant_mode(*, role: QuantRole, settings: AppSettings) -> QuantMode:
    """
    Return a concrete quant mode for a role, resolving ``auto`` via the effective per-role VRAM
    budget (which itself respects the user's GPU policy / single-pinned device).
    """
    attr = {
        "script": "script_quant_mode",
        "image": "image_quant_mode",
        "video": "video_quant_mode",
        "voice": "voice_quant_mode",
    }.get((role or "script").strip().lower(), "script_quant_mode")
    raw = getattr(settings, attr, "auto")
    mode = _norm_mode(raw)
    if mode != "auto":
        try:
            from debug import dprint

            dprint("models", "resolve_quant_mode", f"role={role!r}", f"mode={mode!r}", "explicit")
        except Exception:
            pass
        return mode
    try:  # Best-effort: pull the same per-role VRAM the rest of the app uses.
        from src.models.inference_profiles import resolve_effective_vram_gb

        v = resolve_effective_vram_gb(kind=role, settings=settings)
    except Exception:
        v = None
    resolved = pick_auto_mode(role=role, repo_id="", vram_gb=v, cuda_ok=v is not None and v > 0)
    try:
        from debug import dprint

        dprint("models", "resolve_quant_mode", f"role={role!r}", f"mode={resolved!r}", "auto")
    except Exception:
        pass
    return resolved

