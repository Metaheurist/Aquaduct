from __future__ import annotations

from typing import Literal

from src.core.config import SeriesSourceStrategy, VideoFormat


def resolve_series_source_strategy(
    strategy: SeriesSourceStrategy | str | None,
    *,
    video_format: str | VideoFormat | None,
    run_content_mode: str | None = "preset",
) -> Literal["lock_first", "fresh_per_ep"]:
    """
    Map UI strategy + format to a concrete policy.

    - **auto**: news / health_advice → fresh headline per episode; other formats + custom brief → lock to episode 1 sources.
    """
    s = str(strategy or "auto").strip().lower()
    if s == "lock_first":
        return "lock_first"
    if s == "fresh_per_ep":
        return "fresh_per_ep"
    rc = str(run_content_mode or "preset").strip().lower()
    if rc == "custom":
        return "lock_first"
    vf = str(video_format or "news").strip().lower()
    if vf in ("news", "health_advice"):
        return "fresh_per_ep"
    return "lock_first"
