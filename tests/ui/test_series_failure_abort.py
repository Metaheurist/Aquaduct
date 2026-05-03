"""Series run failure: remaining ``series_episode`` rows for the same slug are dropped (see MainWindow._on_failed)."""

from __future__ import annotations

from src.core.config import AppSettings
from src.series.store import drop_queued_series_items_for_slug


def test_series_failure_drops_remaining_episodes_for_slug_only():
    q: list = [
        {"kind": "series_episode", "series_slug": "show_a", "episode_index": 2},
        {"kind": "pipeline", "settings": AppSettings()},
        {"kind": "series_episode", "series_slug": "show_a", "episode_index": 3},
        {"kind": "series_episode", "series_slug": "show_b", "episode_index": 2},
    ]
    removed = drop_queued_series_items_for_slug(q, "show_a")
    assert removed == 2
    assert len(q) == 2
    assert q[0]["kind"] == "pipeline"
    assert q[1]["series_slug"] == "show_b"
