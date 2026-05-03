from __future__ import annotations

from src.series.source_strategy import resolve_series_source_strategy


def test_auto_news_fresh():
    assert (
        resolve_series_source_strategy("auto", video_format="news", run_content_mode="preset")
        == "fresh_per_ep"
    )


def test_auto_unhinged_lock():
    assert (
        resolve_series_source_strategy("auto", video_format="unhinged", run_content_mode="preset")
        == "lock_first"
    )


def test_custom_locks():
    assert (
        resolve_series_source_strategy("auto", video_format="news", run_content_mode="custom")
        == "lock_first"
    )


def test_explicit():
    assert resolve_series_source_strategy("lock_first", video_format="news") == "lock_first"
    assert resolve_series_source_strategy("fresh_per_ep", video_format="creepypasta") == "fresh_per_ep"
