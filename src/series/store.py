"""Filesystem store for video series: ``videos/<slug>/series.json`` + ``series_bible.md``."""

from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.core.config import AppSettings, Paths, safe_title_to_dirname


SERIES_JSON_NAME = "series.json"
BIBLE_NAME = "series_bible.md"


def series_root_for(paths: Paths, slug: str) -> Path:
    return paths.videos_dir / slug


def series_json_path(series_dir: Path) -> Path:
    return series_dir / SERIES_JSON_NAME


def series_bible_path(series_dir: Path) -> Path:
    return series_dir / BIBLE_NAME


def _slug_base(name: str) -> str:
    s = safe_title_to_dirname(name.strip() or "series")
    return s if s else "series"


def allocate_series_slug(videos_dir: Path, desired_name: str) -> str:
    """Return a Windows-safe directory name under ``videos_dir`` that does not yet exist."""
    base = _slug_base(desired_name)
    candidate = base
    n = 1
    while (videos_dir / candidate).exists():
        n += 1
        candidate = f"{base}_{n}"
    return candidate


@dataclass
class SeriesEpisodeEntry:
    index: int
    subdir: str
    title: str
    recap: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "subdir": self.subdir, "title": self.title, "recap": self.recap}

    @staticmethod
    def from_dict(d: Any) -> SeriesEpisodeEntry | None:
        if not isinstance(d, dict):
            return None
        try:
            idx = int(d.get("index", 0))
            sub = str(d.get("subdir", "") or "")
            title = str(d.get("title", "") or "")
            recap = str(d.get("recap", "") or "")
        except (TypeError, ValueError):
            return None
        if not sub:
            return None
        return SeriesEpisodeEntry(index=idx, subdir=sub, title=title, recap=recap)


@dataclass
class SeriesRecord:
    """On-disk series metadata (``series.json``)."""

    slug: str
    name: str
    video_format: str
    art_style_preset_id: str
    episode_total: int
    settings_snapshot: dict[str, Any]
    episodes: list[SeriesEpisodeEntry] = field(default_factory=list)
    locked_sources: list[dict[str, str]] | None = None
    locked_article_excerpt: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "slug": self.slug,
            "name": self.name,
            "video_format": self.video_format,
            "art_style_preset_id": self.art_style_preset_id,
            "episode_total": self.episode_total,
            "settings_snapshot": self.settings_snapshot,
            "episodes": [e.to_dict() for e in self.episodes],
            "locked_sources": self.locked_sources,
            "locked_article_excerpt": self.locked_article_excerpt,
            "created_at": self.created_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    @staticmethod
    def from_dict(data: Any) -> SeriesRecord | None:
        if not isinstance(data, dict):
            return None
        slug = str(data.get("slug", "") or "")
        if not slug:
            return None
        eps_raw = data.get("episodes", [])
        episodes: list[SeriesEpisodeEntry] = []
        if isinstance(eps_raw, list):
            for item in eps_raw:
                e = SeriesEpisodeEntry.from_dict(item)
                if e:
                    episodes.append(e)
        ls = data.get("locked_sources")
        locked_sources: list[dict[str, str]] | None = None
        if isinstance(ls, list):
            locked_sources = [x for x in ls if isinstance(x, dict)]
        snap = data.get("settings_snapshot")
        if not isinstance(snap, dict):
            snap = {}
        return SeriesRecord(
            slug=slug,
            name=str(data.get("name", "") or slug),
            video_format=str(data.get("video_format", "news") or "news"),
            art_style_preset_id=str(data.get("art_style_preset_id", "balanced") or "balanced"),
            episode_total=int(data.get("episode_total", 1) or 1),
            settings_snapshot=snap,
            episodes=episodes,
            locked_sources=locked_sources,
            locked_article_excerpt=str(data.get("locked_article_excerpt", "") or ""),
            created_at=str(data.get("created_at", "") or ""),
        )


def read_series_bible(series_dir: Path) -> str:
    p = series_bible_path(series_dir)
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def append_series_bible(series_dir: Path, *, episode_idx: int, title: str, recap: str) -> None:
    series_dir.mkdir(parents=True, exist_ok=True)
    p = series_bible_path(series_dir)
    block = f"\n### Episode {episode_idx}: {title}\n\n{recap.strip()}\n\n"
    try:
        prev = p.read_text(encoding="utf-8") if p.is_file() else ""
    except OSError:
        prev = ""
    header = "# Series bible\n\nRolling recap and continuity notes.\n"
    body = (prev.strip() + block) if prev.strip() else header + block
    p.write_text(body, encoding="utf-8")


def load_series_record(series_dir: Path) -> SeriesRecord | None:
    path = series_json_path(series_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return SeriesRecord.from_dict(data)


def save_series_record(series_dir: Path, record: SeriesRecord) -> None:
    series_dir.mkdir(parents=True, exist_ok=True)
    path = series_json_path(series_dir)
    tmp = series_dir / f".{SERIES_JSON_NAME}.{uuid.uuid4().hex}.tmp"
    payload = json.dumps(record.to_dict(), indent=2, ensure_ascii=False)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def next_episode_index(record: SeriesRecord) -> int:
    if not record.episodes:
        return 1
    return max(e.index for e in record.episodes) + 1


def find_or_create_series(
    paths: Paths,
    settings: AppSettings,
    *,
    display_name: str,
    episode_total: int,
) -> tuple[str, SeriesRecord]:
    """
    Allocate a new series folder + ``series.json`` with a frozen ``settings_snapshot``.

    Returns ``(slug, record)``.
    """
    slug = allocate_series_slug(paths.videos_dir, display_name)
    series_dir = series_root_for(paths, slug)
    series_dir.mkdir(parents=True, exist_ok=True)

    # Strip ephemeral / non-persistent fields for the snapshot (mirrors save_settings).
    snap = asdict(settings)
    for k in (
        "resource_retry_resolution_scale",
        "resource_retry_frames_scale",
        "recovery_swapped_voice_model_id",
        "recovery_swapped_video_model_id",
        "recovery_swapped_image_model_id",
        "resume_partial_project_directory",
        "_force_cpu_diffusion",
    ):
        snap.pop(k, None)

    record = SeriesRecord(
        slug=slug,
        name=(display_name.strip() or slug),
        video_format=str(settings.video_format or "news"),
        art_style_preset_id=str(settings.art_style_preset_id or "balanced"),
        episode_total=max(1, int(episode_total)),
        settings_snapshot=snap,
        episodes=[],
        locked_sources=None,
        locked_article_excerpt="",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    save_series_record(series_dir, record)
    bible = series_bible_path(series_dir)
    if not bible.is_file():
        bible.write_text(
            "# Series bible\n\nRolling recap and continuity notes.\n",
            encoding="utf-8",
        )
    return slug, record


def episode_subdir_name(episode_index: int, title: str) -> str:
    """``episode_001_SlugTitle`` under the series root."""
    slug = (safe_title_to_dirname(title) or "untitled")[:60]
    return f"episode_{episode_index:03d}_{slug}"


def register_episode(
    paths: Paths,
    *,
    slug: str,
    episode_index: int,
    title: str,
    episode_project_dir: Path,
    recap: str,
) -> SeriesRecord | None:
    """Append episode metadata + bible; returns updated record or None if missing series."""
    series_dir = series_root_for(paths, slug)
    record = load_series_record(series_dir)
    if record is None:
        return None
    try:
        rel = episode_project_dir.relative_to(series_dir)
        subdir = rel.as_posix()
    except ValueError:
        subdir = episode_project_dir.name

    # Dedupe by index
    record.episodes = [e for e in record.episodes if e.index != episode_index]
    record.episodes.append(
        SeriesEpisodeEntry(index=episode_index, subdir=subdir, title=title, recap=recap.strip())
    )
    record.episodes.sort(key=lambda e: e.index)
    save_series_record(series_dir, record)
    append_series_bible(series_dir, episode_idx=episode_index, title=title, recap=recap)
    return record


def latest_episode_dir(paths: Paths, record: SeriesRecord) -> Path | None:
    """Directory of the most recently registered episode (by index)."""
    if not record.episodes:
        return None
    last = max(record.episodes, key=lambda e: e.index)
    return series_root_for(paths, record.slug) / last.subdir


def persist_locked_sources(
    paths: Paths,
    slug: str,
    *,
    sources: list[dict[str, str]] | None,
    article_excerpt: str = "",
) -> None:
    """After episode 1 sources are known, store them on ``series.json``."""
    series_dir = series_root_for(paths, slug)
    record = load_series_record(series_dir)
    if record is None:
        return
    if sources:
        record.locked_sources = [dict(x) for x in sources if isinstance(x, dict)]
    if article_excerpt.strip():
        record.locked_article_excerpt = article_excerpt.strip()[:8000]
    save_series_record(series_dir, record)


def drop_queued_series_items_for_slug(queue: list[dict[str, Any]], slug: str) -> int:
    """Remove pending ``series_episode`` rows matching ``slug``. Returns number removed."""
    s = str(slug or "").strip()
    if not s:
        return 0
    before = len(queue)
    queue[:] = [
        q
        for q in queue
        if not (
            isinstance(q, dict)
            and str(q.get("kind") or "") == "series_episode"
            and str(q.get("series_slug") or "").strip() == s
        )
    ]
    return before - len(queue)


def strip_lock_first_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Remove series UI flags from frozen snapshot so rehydrated jobs do not re-enqueue series."""
    out = deepcopy(snapshot)
    ser = out.get("series")
    if isinstance(ser, dict):
        ser = {**ser, "series_mode": False, "episode_count": 1}
        out["series"] = ser
    return out
