from __future__ import annotations

from src.core.config import AppSettings, Paths
from src.series.store import (
    allocate_series_slug,
    append_series_bible,
    find_or_create_series,
    load_series_record,
    persist_locked_sources,
    read_series_bible,
    register_episode,
    series_bible_path,
    series_root_for,
)


def _fake_paths(tmp_path) -> Paths:
    ada = tmp_path / ".Aquaduct_data"
    return Paths(
        root=tmp_path,
        app_data_dir=ada,
        data_dir=ada / "data",
        news_cache_dir=ada / "data" / "news_cache",
        runs_dir=ada / "runs",
        videos_dir=ada / "videos",
        pictures_dir=ada / "pictures",
        models_dir=ada / "models",
        cache_dir=ada / ".cache",
        ffmpeg_dir=ada / ".cache" / "ffmpeg",
    )


def test_allocate_series_slug_collision(tmp_path):
    paths = _fake_paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    (paths.videos_dir / "My_Show").mkdir()
    s = allocate_series_slug(paths.videos_dir, "My Show")
    assert s == "My_Show_2"


def test_find_or_create_series_writes_json_and_bible(tmp_path):
    paths = _fake_paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    app = AppSettings()
    slug, rec = find_or_create_series(paths, app, display_name="Test Series", episode_total=3)
    assert slug
    root = series_root_for(paths, slug)
    assert (root / "series.json").is_file()
    assert series_bible_path(root).is_file()
    loaded = load_series_record(root)
    assert loaded is not None
    assert loaded.episode_total == 3
    assert loaded.settings_snapshot.get("video_format") == "news"


def test_register_episode_and_bible_append(tmp_path):
    paths = _fake_paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    app = AppSettings()
    slug, _ = find_or_create_series(paths, app, display_name="Arc", episode_total=2)
    root = series_root_for(paths, slug)
    ep_dir = root / "episode_001_Hello"
    ep_dir.mkdir(parents=True)
    out = register_episode(
        paths,
        slug=slug,
        episode_index=1,
        title="Hello",
        episode_project_dir=ep_dir,
        recap="First recap.",
    )
    assert out is not None
    assert len(out.episodes) == 1
    bible = read_series_bible(root)
    assert "Episode 1" in bible
    assert "First recap" in bible
    append_series_bible(root, episode_idx=2, title="Two", recap="Second.")
    bible2 = read_series_bible(root)
    assert "Episode 2" in bible2


def test_persist_locked_sources(tmp_path):
    paths = _fake_paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    slug, _ = find_or_create_series(paths, AppSettings(), display_name="L", episode_total=1)
    persist_locked_sources(
        paths,
        slug,
        sources=[{"title": "A", "url": "https://x"}],
        article_excerpt="Body text",
    )
    rec = load_series_record(series_root_for(paths, slug))
    assert rec and rec.locked_sources == [{"title": "A", "url": "https://x"}]
    assert "Body text" in (rec.locked_article_excerpt or "")
