from __future__ import annotations

import threading

import pytest

from src.runtime.pipeline_control import PipelineCancelled, PipelineRunControl


def test_checkpoint_raises_when_cancelled() -> None:
    rc = PipelineRunControl()
    rc.request_cancel()
    with pytest.raises(PipelineCancelled):
        rc.checkpoint()


def test_pause_blocks_until_resume() -> None:
    rc = PipelineRunControl()
    rc.request_pause()
    out: list[str] = []

    def worker() -> None:
        try:
            rc.checkpoint()
            out.append("ok")
        except PipelineCancelled:
            out.append("cancelled")

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    assert out == []
    rc.request_resume()
    t.join(timeout=2.0)
    assert out == ["ok"]


def test_pause_unblocks_on_cancel() -> None:
    rc = PipelineRunControl()
    rc.request_pause()
    err: list[str] = []

    def worker() -> None:
        try:
            rc.checkpoint()
        except PipelineCancelled:
            err.append("x")

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    rc.request_cancel()
    t.join(timeout=2.0)
    assert err == ["x"]
