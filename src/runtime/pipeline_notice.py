"""Optional UI notices during ``run_once`` (VRAM warnings, etc.) — set from PipelineWorker thread."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar

_NoticeCb = Callable[[str, str], None]
_pipeline_notice_cb: ContextVar[_NoticeCb | None] = ContextVar("pipeline_notice_cb", default=None)


@contextmanager
def pipeline_notice_scope(cb: _NoticeCb | None):
    """While active, :func:`emit_pipeline_notice` forwards (title, message) to ``cb`` (e.g. Qt signal)."""
    if cb is None:
        yield
        return
    tok = _pipeline_notice_cb.set(cb)
    try:
        yield
    finally:
        _pipeline_notice_cb.reset(tok)


def emit_pipeline_notice(title: str, message: str) -> None:
    cb = _pipeline_notice_cb.get()
    if cb is None:
        return
    try:
        cb(str(title).strip() or "Notice", str(message).strip())
    except Exception:
        pass
