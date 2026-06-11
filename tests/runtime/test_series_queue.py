from __future__ import annotations

from src.core.config import Paths
from src.runtime.series_queue import resume_series_queue_items
from src.series.store import find_or_create_series, register_episode, series_root_for


def _paths(tmp_path) -> Paths:
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


def test_resume_series_queue_items_after_ep1(tmp_path):
    paths = _paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    slug, _ = find_or_create_series(paths, __import__("src.core.config", fromlist=["AppSettings"]).AppSettings(), display_name="Show", episode_total=3)
    root = series_root_for(paths, slug)
    ep1 = root / "episode_001_A"
    ep1.mkdir(parents=True)
    register_episode(paths, slug=slug, episode_index=1, title="A", episode_project_dir=ep1, recap="done")
    items = resume_series_queue_items(paths=paths, slug=slug)
    assert [int(x["episode_index"]) for x in items] == [2, 3]
    assert all(x["kind"] == "series_episode" for x in items)
