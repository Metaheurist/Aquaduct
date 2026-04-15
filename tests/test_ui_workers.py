from __future__ import annotations

import pytest


@pytest.mark.qt
def test_pipeline_batch_worker_emits_done_when_no_items(qtbot, monkeypatch):
    from UI.workers import PipelineBatchWorker
    from src.config import AppSettings

    # Force run_once to always return None
    import UI.workers as wmod

    monkeypatch.setattr(wmod.pipeline_main, "run_once", lambda **kwargs: None)

    w = PipelineBatchWorker(AppSettings(topic_tags=[]), quantity=2)
    done_msgs = []
    w.done.connect(lambda msg: done_msgs.append(msg))
    w.start()
    qtbot.waitSignal(w.done, timeout=8000)
    qtbot.waitUntil(lambda: len(done_msgs) == 1, timeout=8000)
    assert "No new items" in done_msgs[0] or "Ran out" in done_msgs[0]

