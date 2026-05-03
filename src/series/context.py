"""Per-episode context passed into ``run_once`` for video series."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SeriesContext:
    series_slug: str
    episode_index: int
    episode_total: int
    is_first: bool
    source_strategy_resolved: Literal["lock_first", "fresh_per_ep"]
    previous_episode_dir: str | None
    series_bible_text: str
    lock_style: bool
    carry_recap: bool
    continue_on_failure: bool
