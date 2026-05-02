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


def check_stage_memory_budget(
    *,
    stage_label: str,
    role: str,
    repo_id: str | None,
    settings: Any,
    hf_cache_root: Path | None = None,
) -> list[str]:
    """
    Emit human-readable warnings (no hard abort) comparing required vs available host RAM.

    Required model bytes are heuristic; complements VRAM watchdogs that run nearer torch loads.
    """
    warns: list[str] = []
    if os.environ.get("AQUADUCT_MEMORY_PREFLIGHT", "1").strip().lower() in ("0", "false", "no", "off"):
        return warns
    try:
        import psutil

        avail_gb = psutil.virtual_memory().available / (1024**3)
    except Exception:
        avail_gb = None
    sz = hf_cache_size_estimate_gib(repo_id, hf_cache_root=hf_cache_root)
    if avail_gb is not None and sz is not None:
        # Large safetensors reads can spike 1–2× archive size transiently — leave headroom factor.
        need = sz * float(os.environ.get("AQUADUCT_HOST_RAM_PREFLIGHT_FACTOR", "2.0"))
        floor = float(os.environ.get("AQUADUCT_HOST_RAM_FLOOR_GIB", "5.0"))
        if avail_gb + 1e-6 < max(floor, need):
            warns.append(
                f"{stage_label} ({role}): low host RAM (~{avail_gb:.1f} GiB available) versus rough model footprint "
                f"~{sz:.1f} GiB (+temp buffers). Prefer a lighter model variant, enable CPU offload, or close apps."
            )
    return warns
