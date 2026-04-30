from __future__ import annotations

import os

from src.core.config import AppSettings


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def preflight_cpu_busy_warnings() -> list[str]:
    """Soft warning when system-wide CPU utilization is high before a run."""
    if not _truthy("AQUADUCT_CPU_PREFLIGHT"):
        return []
    try:
        import psutil

        psutil.cpu_percent(interval=None)
        pct = float(psutil.cpu_percent(interval=0.12))
    except Exception:
        return []
    try:
        thr = float(os.environ.get("AQUADUCT_CPU_PREFLIGHT_PCT", "90"))
    except Exception:
        thr = 90.0
    if pct < thr:
        return []
    return [
        f"Host CPU load is high (~{pct:.0f}% combined). Local runs may be slow or jittery during load — consider closing CPU-heavy apps."
    ]


def _repo_heavy_for_host_ram(repo_id: str, cached_bytes: int | None, *, heavy_bytes: int) -> bool:
    """True if Hub byte total or id heuristics suggest a RAM-heavy local load."""
    rid = (repo_id or "").strip().lower()
    if not rid:
        return False
    if cached_bytes is not None and cached_bytes >= heavy_bytes:
        return True
    if any(x in rid for x in ("wan-ai", "wan2.2", "wan2_2", "hunyuanvideo")):
        return True
    if "mochi" in rid:
        return True
    if "cogvideox" in rid:
        return True
    if "ltx-2" in rid or "ltx-video" in rid or rid.startswith("lightricks/ltx"):
        return True
    if "flux" in rid and ("dev" in rid or "ultra" in rid or "pro-ultra" in rid):
        return True
    if "stable-diffusion-3.5-large" in rid:
        return True
    if "deepseek" in rid and "v3" in rid:
        return True
    if "midnight-miqu" in rid:
        return True
    return False


def _cache_lookup(cache: dict[str, int], repo_id: str) -> int | None:
    r = (repo_id or "").strip()
    if not r:
        return None
    if r in cache:
        return cache[r]
    rl = r.lower()
    for k, v in cache.items():
        if str(k).strip().lower() == rl:
            return int(v)
    return None


def preflight_heavy_repo_ram_warnings(settings: AppSettings) -> list[str]:
    """
    When free host RAM is below a threshold and a selected **local** repo looks large
    (HF size cache and/or frontier id heuristics), emit a targeted warning.
    """
    if not _truthy("AQUADUCT_PREFLIGHT_HEAVY_REPO_RAM"):
        return []
    from src.runtime.model_backend import is_api_mode

    if is_api_mode(settings):
        return []
    try:
        import psutil

        vm = psutil.virtual_memory()
        avail_gb = float(vm.available) / (1024.0**3)
    except Exception:
        return []
    try:
        free_thr = float(os.environ.get("AQUADUCT_PREFLIGHT_HEAVY_REPO_RAM_FREE_GIB", "8"))
    except Exception:
        free_thr = 8.0
    if avail_gb >= free_thr:
        return []
    try:
        hub_gib = float(os.environ.get("AQUADUCT_PREFLIGHT_HEAVY_REPO_HUB_GIB", "6"))
    except Exception:
        hub_gib = 6.0
    heavy_bytes = int(hub_gib * (1024**3))

    from src.core.config import get_models, get_paths
    from src.models import model_manager as _mm

    cache = _mm.load_hf_size_cache(get_paths().cache_dir / "hf_model_sizes.json")
    models = get_models()
    mm = str(getattr(settings, "media_mode", "video") or "video").strip().lower()

    llm = (settings.llm_model_id or "").strip() or models.llm_id
    img = (settings.image_model_id or "").strip() or models.sdxl_turbo_id
    rows: list[tuple[str, str]] = [("Script", llm), ("Image", img)]
    if mm != "photo":
        voice = (settings.voice_model_id or "").strip() or models.kokoro_id
        vid = (getattr(settings, "video_model_id", "") or "").strip()
        rows.extend([("Voice", voice), ("Video", vid)])

    heavy_labels: list[str] = []
    for label, rid in rows:
        r = (rid or "").strip()
        if not r:
            continue
        sz = _cache_lookup(cache, r)
        if _repo_heavy_for_host_ram(r, sz, heavy_bytes=heavy_bytes):
            heavy_labels.append(f"{label} ({r})")

    if not heavy_labels:
        return []
    return [
        f"Host RAM ~{avail_gb:.1f} GiB free; selected local model(s) are large or frontier-class: {', '.join(heavy_labels)}. "
        "Expect high host RAM while weights load — close other apps or use lighter repos."
    ]
