"""
Categorized debug logging to stderr.

Enable via **environment** (before or in ``.env``):

- ``AQUADUCT_DEBUG=all`` — every category below
- ``AQUADUCT_DEBUG=pipeline,brain,models`` — comma-separated list
- ``AQUADUCT_DEBUG_PIPELINE=1`` — per-category toggles (same name in UPPER)

**Categories**

- ``pipeline`` — ``main.run_once`` orchestration steps
- ``crawler`` — news fetch / item selection
- ``brain`` — LLM script generation
- ``voice`` — TTS / captions JSON
- ``artist`` — image generation
- ``editor`` — micro-clip assembly + final concat
- ``clips`` — video clip generation (img→vid path)
- ``storyboard`` — storyboard + manifest
- ``audio`` — polish, music ducking, SFX mix
- ``models`` — Hugging Face downloads / ``model_manager``
- ``preflight`` — preflight checks
- ``branding`` — palette / prompt styling
- ``topics`` — topic discovery worker
- ``workers`` — generic UI worker boundaries (pipeline / preview / batch)
- ``ui`` — main window actions (runs, downloads, save)
- ``config`` — settings load/save (light touch)

CLI (merged with env):

- ``python main.py --once --debug brain,pipeline``
- ``python -m UI --debug ui,workers``

"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Final

# Canonical flags (also used for AQUADUCT_DEBUG_<NAME> env suffix).
DEBUG_CATEGORIES: Final[tuple[str, ...]] = (
    "pipeline",
    "crawler",
    "brain",
    "voice",
    "artist",
    "editor",
    "clips",
    "storyboard",
    "audio",
    "models",
    "preflight",
    "branding",
    "topics",
    "workers",
    "ui",
    "config",
)

_ALIASES: Final[dict[str, str]] = {
    "run": "pipeline",
    "llm": "brain",
    "tts": "voice",
    "diffusion": "artist",
    "images": "artist",
    "hf": "models",
    "download": "models",
    "ffmpeg": "editor",
    "assembly": "editor",
    "video": "clips",
    "sb": "storyboard",
}

_CAT_SET: Final[frozenset[str]] = frozenset(DEBUG_CATEGORIES)

_cli_extra: str = ""
_active_cache: frozenset[str] | None = None


def _truthy(val: str) -> bool:
    s = val.strip().lower()
    return s in ("1", "true", "yes", "on", "all", "*")


def _parse_csv(spec: str) -> set[str]:
    spec = (spec or "").strip().lower()
    out: set[str] = set()
    if not spec:
        return out
    if spec in ("all", "*", "1", "true", "yes"):
        out.update(DEBUG_CATEGORIES)
        return out
    for part in spec.replace(";", ",").split(","):
        p = part.strip()
        if not p:
            continue
        p = _ALIASES.get(p, p)
        if p in _CAT_SET:
            out.add(p)
    return out


def _recompute_active() -> frozenset[str]:
    merged: set[str] = set()
    main_spec = (os.environ.get("AQUADUCT_DEBUG") or "").strip()
    low = main_spec.lower()
    if low in ("all", "*", "1", "true", "yes"):
        merged.update(DEBUG_CATEGORIES)
    else:
        merged.update(_parse_csv(main_spec))

    for c in DEBUG_CATEGORIES:
        ev = os.environ.get(f"AQUADUCT_DEBUG_{c.upper()}", None)
        if ev is None:
            continue
        if _truthy(ev):
            merged.add(c)
        elif ev.strip() and ev.strip().lower() in ("0", "false", "no", "off"):
            merged.discard(c)

    merged.update(_parse_csv(_cli_extra))
    return frozenset(merged)


def active_categories() -> frozenset[str]:
    """Frozen set of enabled category names."""
    global _active_cache
    if _active_cache is None:
        _active_cache = _recompute_active()
    return _active_cache


def invalidate_debug_cache() -> None:
    """Call after changing CLI override or env in tests."""
    global _active_cache
    _active_cache = None


def apply_cli_debug(spec: str) -> None:
    """Merge a comma list (or ``all``) from CLI ``--debug``."""
    global _cli_extra, _active_cache
    _cli_extra = spec or ""
    _active_cache = None


def debug_enabled(category: str) -> bool:
    return category.lower().strip() in active_categories()


def dprint(category: str, *parts: object, ts: bool = True) -> None:
    """
    Print one debug line to stderr if ``category`` is enabled.
    Also appends the same line to ``logs/debug.log`` when enabled.
    *parts* are passed through ``str()`` like ``print``.
    """
    cat = category.lower().strip()
    if cat not in _CAT_SET or cat not in active_categories():
        return
    prefix = f"[Aquaduct:{cat}]"
    if ts:
        prefix = f"{datetime.now().isoformat(timespec='seconds')} {prefix}"
    line = prefix + " " + " ".join(str(p) for p in parts)
    print(prefix, *parts, file=sys.stderr, flush=True)
    try:
        from src.repo_logs import append_debug_log

        append_debug_log(line)
    except Exception:
        pass


def debug_categories_line() -> str:
    """Human-readable list for help text."""
    return ", ".join(DEBUG_CATEGORIES)
