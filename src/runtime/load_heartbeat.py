"""Periodic console heartbeats during long synchronous model loads."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any


def _tick_interval_s() -> float:
    try:
        return max(10.0, float(os.environ.get("AQUADUCT_LOAD_HEARTBEAT_INTERVAL_S", "30")))
    except Exception:
        return 30.0


class StalledLoadError(RuntimeError):
    """Raised when ``AQUADUCT_LOAD_FATAL_TIMEOUT_S`` elapsed (best-effort; see docs)."""


RESOURCE_GRAPH_LAST_LINE = ""
RESOURCE_GRAPH_LAST_MONO = 0.0


def set_load_heartbeat_notice(txt: str) -> None:
    """Record the latest heartbeat line for UI surfaces (Resource Graph footer)."""
    global RESOURCE_GRAPH_LAST_LINE, RESOURCE_GRAPH_LAST_MONO
    RESOURCE_GRAPH_LAST_LINE = (txt or "").strip()
    RESOURCE_GRAPH_LAST_MONO = time.monotonic()


def get_load_heartbeat_footer_text(*, max_age_s: float = 180.0) -> str:
    """Return recent heartbeat text or empty when stale."""
    age = time.monotonic() - RESOURCE_GRAPH_LAST_MONO
    if RESOURCE_GRAPH_LAST_LINE and age <= max_age_s:
        return RESOURCE_GRAPH_LAST_LINE
    return ""


def _fatal_timeout_seconds() -> float:
    raw = (
        os.environ.get("AQUADUCT_LOAD_FATAL_TIMEOUT_S", "").strip()
        or os.environ.get("AQUADUCT_LOAD_TIMEOUT_S", "").strip()
    )
    try:
        return float(raw) if raw.replace(".", "", 1).isdigit() else 0.0
    except Exception:
        return 0.0


@contextmanager
def diffusion_load_watch(
    *,
    label: str,
    stage: str = "model_load",
    beat: Callable[[str], None] | None = None,
) -> Any:
    """
    Daemon thread emits beats while this context is entered.

    Fatal timeout is optional (default **disabled**) because interrupting synchronous ``from_pretrained``
    from another thread cannot be done safely cross-platform without cancellation support.
    Set ``AQUADUCT_LOAD_FATAL_TIMEOUT_S`` or ``AQUADUCT_LOAD_TIMEOUT_S`` > 0 to log a stalled-load watchdog
    after that many seconds (**note**: the HF load continues in-flight; callers may salvage via outer retries).
    """
    stop = threading.Event()
    t0 = time.monotonic()

    def _beats() -> None:
        fatal = _fatal_timeout_seconds()
        interval = _tick_interval_s()
        msg_fn = beat
        if msg_fn is None:
            try:
                from debug import pipeline_console as _pc

                def _msg(txt: str) -> None:
                    _pc(txt, stage=stage)

                msg_fn = _msg
            except Exception:

                def _msg(txt: str) -> None:
                    print(f"[Aquaduct][load:{stage}] {txt}", flush=True)

                msg_fn = _msg

        _orig_emit = msg_fn

        def _emit(txt: str) -> None:
            try:
                set_load_heartbeat_notice(txt)
            except Exception:
                pass
            _orig_emit(txt)

        msg_fn = _emit

        while not stop.wait(interval):
            elapsed = time.monotonic() - t0
            try:
                import psutil

                rss = psutil.Process().memory_info().rss / (1024**3)
                msg_fn(f"Still loading {label!r} — {elapsed:.0f}s elapsed; host RSS≈{rss:.1f} GiB …")
            except Exception:
                msg_fn(f"Still loading {label!r} — {elapsed:.0f}s elapsed …")
            if fatal > 0 and elapsed >= fatal:
                try:
                    from debug import pipeline_console as _warn

                    _warn(
                        f"Load watchdog: {elapsed:.0f}s ≥ fatal timeout ({fatal}s) — {label!r}. "
                        "Outer retry ladders may downgrade settings.",
                        stage=stage,
                    )
                except Exception:
                    pass
                # Raising won't stop synchronous load; surfaced for tests / external monitors.
                return

    th = threading.Thread(target=_beats, daemon=True)
    th.start()
    try:
        yield
    finally:
        stop.set()
        th.join(timeout=1.5)
