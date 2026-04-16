"""
Persist per-repo Hugging Face integrity outcomes so the Model tab can show
Verified / Missing files / Corrupt instead of only “on disk” by size.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.model_manager import ModelIntegrityReport

INTEGRITY_CACHE_FILENAME = "model_integrity_status.json"

VALID_STATES = frozenset({"ok", "missing", "corrupt", "missing_and_corrupt", "error"})


def integrity_cache_path(data_dir: Path) -> Path:
    return Path(data_dir) / INTEGRITY_CACHE_FILENAME


def classify_integrity_status(rpt: ModelIntegrityReport) -> str:
    """Map a Hub verify report to a small string for UI + JSON cache."""
    if rpt.error:
        return "error"
    if rpt.ok:
        return "ok"
    has_m = bool(rpt.missing_paths)
    has_c = bool(rpt.mismatches)
    if has_m and has_c:
        return "missing_and_corrupt"
    if has_c:
        return "corrupt"
    if has_m:
        return "missing"
    return "error"


def load_integrity_cache(data_dir: Path) -> dict[str, str]:
    p = integrity_cache_path(data_dir)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks = str(k).strip()
        vs = str(v).strip()
        if ks and vs in VALID_STATES:
            out[ks] = vs
    return out


def save_integrity_cache(data_dir: Path, status_by_repo: dict[str, str]) -> None:
    p = integrity_cache_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        str(k).strip(): str(v).strip()
        for k, v in status_by_repo.items()
        if str(k).strip() and str(v).strip() in VALID_STATES
    }
    p.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")


def merge_integrity_cache(existing: dict[str, str], updates: dict[str, str]) -> dict[str, str]:
    out = dict(existing)
    for k, v in updates.items():
        ks = str(k).strip()
        if not ks:
            continue
        vs = str(v).strip()
        if vs in VALID_STATES:
            out[ks] = vs
    return out


# Worst-first: lower index = show that badge when combining multiple repos (e.g. image + video).
_INTEGRITY_RANK = (
    "error",
    "missing_and_corrupt",
    "corrupt",
    "missing",
    "ok",
)


def worst_integrity_status(states: list[str]) -> str:
    """
    Pick the worst label among non-empty states (for script/video/voice rows that pull multiple repos).
    Unknown / unseen states are ignored if at least one known state exists.
    """
    rank = {s: i for i, s in enumerate(_INTEGRITY_RANK)}
    best_i = 999
    worst = "ok"
    for s in states:
        s = str(s).strip()
        if s not in rank:
            continue
        i = rank[s]
        if i < best_i:
            best_i = i
            worst = s
    return worst if best_i < 999 else ""
