"""
Categorized debug logging to stderr.

Enable via **in-repo booleans** (``MODULE_DEBUG_FLAGS``), **environment**, or **CLI**:

- ``MODULE_DEBUG_FLAGS`` — set any key to ``True`` in this file to enable that category
  without setting env (union with env/CLI).
- ``AQUADUCT_DEBUG=all`` — every category
- ``AQUADUCT_DEBUG=pipeline,brain,models`` — comma-separated list
- ``AQUADUCT_DEBUG_PIPELINE=1`` — per-category toggles (name in UPPER)

Boolean flags are **additive**: categories with ``MODULE_DEBUG_FLAGS[c]`` True are merged in
after env/CLI resolution so they stay on unless you clear the flag in this file.

If ``AQUADUCT_DEBUG`` is unset or empty, in-repo flags still apply (union). A future
``AQUADUCT_DEBUG_ONLY_ENV=1``-style switch could restrict activation to env/CLI only; the default
remains **simple OR** for developer experience.

**Categories**

- ``pipeline`` — ``main.run_once`` orchestration
- ``crawler`` — news fetch / item selection
- ``brain`` — LLM script generation
- ``voice`` — TTS / captions JSON
- ``artist`` — image generation
- ``editor`` — micro-clip assembly + final concat
- ``clips`` — video clip generation
- ``storyboard`` — storyboard + manifest
- ``story_pipeline`` — multi-stage story review stages
- ``audio`` — polish, music ducking, SFX mix
- ``models`` — Hugging Face downloads / ``model_manager``
- ``preflight`` — preflight checks
- ``branding`` — palette / prompt styling
- ``topics`` — topic discovery worker
- ``workers`` — UI worker boundaries (pipeline / preview / batch)
- ``ui`` — main window shell actions
- ``tasks`` — Tasks tab queue / removals / refresh
- ``config`` — settings load/save
- ``openai`` — OpenAI-compatible HTTP client (API mode / keys redacted)
- ``inference_profile`` — VRAM band / profile report logging
- ``story_context`` — Firecrawl / web context for scripts

CLI (merged with env):

- ``python main.py --once --debug brain,pipeline``
- ``python -m UI --debug ui,workers``

See ``debug/README.md`` and ``debug/<category>/README.md`` per section.

"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Final

# Canonical category names (order stable for docs / tests).
DEBUG_CATEGORIES: Final[tuple[str, ...]] = (
    "pipeline",
    "crawler",
    "brain",
    "voice",
    "artist",
    "editor",
    "clips",
    "storyboard",
    "story_pipeline",
    "audio",
    "models",
    "preflight",
    "branding",
    "topics",
    "workers",
    "ui",
    "tasks",
    "config",
    "openai",
    "inference_profile",
    "story_context",
)

# Flip to True to enable that category without AQUADUCT_DEBUG (union with env/CLI).
MODULE_DEBUG_FLAGS: dict[str, bool] = {c: False for c in DEBUG_CATEGORIES}

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
    "api": "openai",
    "profile": "inference_profile",
    "ctx": "story_context",
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


def _module_flag_enabled() -> set[str]:
    return {c for c in DEBUG_CATEGORIES if MODULE_DEBUG_FLAGS.get(c, False)}


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
    merged.update(_module_flag_enabled())
    return frozenset(merged)


def active_categories() -> frozenset[str]:
    """Frozen set of enabled category names."""
    global _active_cache
    if _active_cache is None:
        _active_cache = _recompute_active()
    return _active_cache


def invalidate_debug_cache() -> None:
    """Call after changing CLI override, env, or ``MODULE_DEBUG_FLAGS`` in tests."""
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
    print(line, file=sys.stderr, flush=True)
    try:
        from src.util.repo_logs import append_debug_log

        append_debug_log(line)
    except Exception:
        pass


def debug_categories_line() -> str:
    """Human-readable list for help text."""
    return ", ".join(DEBUG_CATEGORIES)
