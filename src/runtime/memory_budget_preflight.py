"""Conservative RAM/VRAM budgeting before heavyweight loads."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def hf_cache_size_estimate_gib(repo_id: str | None, *, hf_cache_root: Path | None = None) -> float | None:
    """Rough size from bundled ``hf_model_sizes.json`` when present (best-effort)."""
    if not repo_id:
        return None
    roots: list[Path] = []
    if hf_cache_root is not None:
        roots.append(Path(hf_cache_root))
    try:
        from src.core.config import get_paths

        roots.append(get_paths().cache_dir)
    except Exception:
        roots.append(Path(".Aquaduct_data") / ".cache")
    fname = Path("hf_model_sizes.json")
    for r in roots:
        path = Path(r) / fname if r.name != fname.name else r
        try:
            if not path.is_file():
                continue
            import json

            blob = json.loads(path.read_text(encoding="utf-8"))
            sz = blob.get(str(repo_id).strip()) if isinstance(blob, dict) else None
            if sz is None:
                continue
            return float(sz) / (1024**3)
        except Exception:
            continue
    return None


def analyze_stage_memory_budget(
    *,
    stage_label: str,
    role: str,
    repo_id: str | None,
    settings: Any,  # noqa: ARG001
    hf_cache_root: Path | None = None,
) -> tuple[str | None, str | None]:
    """
    Returns ``(warning, hard_block_message)``.
    Warn when free RAM is below heuristic peak; optionally emit ``hard_block_message`` when
    the deficit is catastrophic (frontier checkpoints on tight hosts — avoids silent OS kills),
    or when ``AQUADUCT_MEMORY_PREFLIGHT_ERROR_ON_WARN_ROLES`` applies (default ``script``).

    Hub snapshot size is scaled by the role's resolved quantization when ``settings`` is provided.
    """
    if os.environ.get("AQUADUCT_MEMORY_PREFLIGHT", "1").strip().lower() in ("0", "false", "no", "off"):
        return None, None
    try:
        import psutil

        avail_gb = psutil.virtual_memory().available / (1024**3)
    except Exception:
        avail_gb = None
    sz_hub = hf_cache_size_estimate_gib(repo_id, hf_cache_root=hf_cache_root)
    if avail_gb is None or sz_hub is None:
        return None, None

    sz = float(sz_hub)
    q_suffix = ""
    if settings is not None:
        try:
            from src.models.quantization import (
                host_ram_hf_snapshot_scale,
                mode_label,
                resolve_quant_mode,
            )

            r0 = role.strip().lower()
            if r0 in ("script", "image", "video"):
                qm = resolve_quant_mode(role=r0, settings=settings)  # type: ignore[arg-type]
                sc = float(host_ram_hf_snapshot_scale(role=r0, mode=qm))
                sz = float(sz_hub) * sc
                if sc < 0.999:
                    q_suffix = f" — adjusted for {mode_label(qm)} load (~×{sc:.2f} vs Hub snapshot)"
        except Exception:
            sz = float(sz_hub)

    need = sz * float(os.environ.get("AQUADUCT_HOST_RAM_PREFLIGHT_FACTOR", "2.0"))
    floor = float(os.environ.get("AQUADUCT_HOST_RAM_FLOOR_GIB", "5.0"))
    threshold_gib = max(floor, need)
    hard_env = os.environ.get("AQUADUCT_MEMORY_PREFLIGHT_FAIL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    warn: str | None = None
    if avail_gb + 1e-6 < threshold_gib:
        warn = (
            f"{stage_label} ({role}): low host RAM (~{avail_gb:.1f} GiB available) versus rough model footprint "
            f"~{sz:.1f} GiB (+temp buffers){q_suffix}. Prefer a lighter model variant, enable CPU offload, or close apps."
        )

    block: str | None = None
    if warn is None:
        return None, None
    raw_fail = os.environ.get("AQUADUCT_MEMORY_PREFLIGHT_FAIL_ROLES", "video")
    fs = str(raw_fail).strip().lower()
    if fs == "":
        roles_force: set[str] = set()
    else:
        roles_force = {x.strip() for x in fs.replace(";", ",").split(",") if x.strip()}
        if not roles_force:
            roles_force = {"video"}

    if hard_env:
        block = warn
        return warn, block

    min_vid = float(os.environ.get("AQUADUCT_MEMORY_BLOCK_MIN_VIDEO_GIB", "30"))
    min_img = float(os.environ.get("AQUADUCT_MEMORY_BLOCK_MIN_IMAGE_GIB", "20"))
    min_script = float(os.environ.get("AQUADUCT_MEMORY_BLOCK_MIN_SCRIPT_GIB", "20"))
    frac = float(os.environ.get("AQUADUCT_MEMORY_SEVERE_SHORTFALL_FRAC", "0.35"))
    r = role.strip().lower()
    tier_ok = False
    if r == "video" and sz >= min_vid:
        tier_ok = True
    elif r == "image" and sz >= min_img:
        tier_ok = True
    elif r == "script" and sz >= min_script:
        tier_ok = True
    catastrophic = tier_ok and (r in roles_force) and (avail_gb + 1e-6) < frac * threshold_gib
    if catastrophic:
        block = (
            f"{stage_label}: refusing run — catastrophic host RAM shortfall (~{avail_gb:.1f} GiB free vs "
            f"~{threshold_gib:.1f} GiB heuristic threshold for footprint ~{sz:.1f} GiB snapshot). Loading this "
            "checkpoint can exhaust Windows RAM and terminate Python with no traceback. Pick a lighter model, "
            "raise free RAM (close apps), use video quantization CPU offload where supported, "
            "or see docs/pipeline/crash-resilience.md. Escape hatch (not recommended): set "
            'AQUADUCT_MEMORY_PREFLIGHT_FAIL_ROLES="" to disable fatal shortfall gating.'
        )
        return warn, block

    # Any-host-RAM shortfall (default: script): large LLM loads often OOM-kill Python on Windows without a traceback
    # when free RAM is below this heuristic — even if not "catastrophic" vs the fractional gate above.
    raw_we = os.environ.get("AQUADUCT_MEMORY_PREFLIGHT_ERROR_ON_WARN_ROLES", "script")
    ws = str(raw_we).strip().lower()
    if ws == "":
        roles_warn_err: set[str] = set()
    else:
        roles_warn_err = {x.strip() for x in ws.replace(";", ",").split(",") if x.strip()}
        if not roles_warn_err:
            roles_warn_err = {"script"}
    if block is None and r in roles_warn_err:
        block = (
            f"{stage_label}: refusing run — host RAM shortfall for current settings (~{avail_gb:.1f} GiB free vs "
            f"~{threshold_gib:.1f} GiB heuristic need from ~{sz:.1f} GiB adjusted snapshot){q_suffix}. Loading can "
            "exhaust Windows RAM and terminate Python with no traceback. Close other apps, use lighter models or "
            "stronger quantization, or see docs/pipeline/crash-resilience.md. To allow the run anyway (not "
            'recommended): set AQUADUCT_MEMORY_PREFLIGHT_ERROR_ON_WARN_ROLES=""'
        )

    return warn, block


def check_stage_memory_budget(
    *,
    stage_label: str,
    role: str,
    repo_id: str | None,
    settings: Any,
    hf_cache_root: Path | None = None,
) -> list[str]:
    """Backward-compatible list of warnings (empty when none)."""
    w, _b = analyze_stage_memory_budget(
        stage_label=stage_label,
        role=role,
        repo_id=repo_id,
        settings=settings,
        hf_cache_root=hf_cache_root,
    )
    return [w] if w else []


def check_stage_memory_hard_blocks(
    *,
    stage_label: str,
    role: str,
    repo_id: str | None,
    settings: Any,
    hf_cache_root: Path | None = None,
) -> list[str]:
    """Fatal preflight strings — same heuristics as :func:`analyze_stage_memory_budget`."""
    _w, b = analyze_stage_memory_budget(
        stage_label=stage_label,
        role=role,
        repo_id=repo_id,
        settings=settings,
        hf_cache_root=hf_cache_root,
    )
    return [b] if b else []
