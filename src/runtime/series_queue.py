"""Helpers for resuming multi-episode series from ``series.json``."""

from __future__ import annotations

from typing import Any

from src.core.config import Paths
from src.series.store import load_series_record, next_episode_index, series_root_for


def resume_series_queue_items(*, paths: Paths, slug: str) -> list[dict[str, Any]]:
    """
    Build FIFO ``series_episode`` queue rows for unfinished episodes.

    Uses ``next_episode_index`` on the on-disk record so partially completed
    series resume at the correct episode number.
    """
    s = str(slug or "").strip()
    if not s:
        return []
    series_dir = series_root_for(paths, s)
    record = load_series_record(series_dir)
    if record is None:
        return []
    start = next_episode_index(record)
    total = max(1, int(record.episode_total))
    if start > total:
        return []
    out: list[dict[str, Any]] = []
    for i in range(start, total + 1):
        out.append(
            {
                "kind": "series_episode",
                "series_slug": s,
                "episode_index": i,
                "episode_total": total,
                "is_first": i == 1,
            }
        )
    return out


def resume_series_queue(*, paths: Paths, slug: str, queue: list[dict[str, Any]]) -> int:
    """
    Append resume items for ``slug`` to ``queue`` (in place). Returns count added.
    Skips if pending rows for the same slug already exist.
    """
    s = str(slug or "").strip()
    if not s:
        return 0
    for q in queue:
        if isinstance(q, dict) and str(q.get("kind") or "") == "series_episode":
            if str(q.get("series_slug") or "").strip() == s:
                return 0
    items = resume_series_queue_items(paths=paths, slug=s)
    if not items:
        return 0
    queue.extend(items)
    return len(items)
