from __future__ import annotations

from pathlib import Path

from src.core.config import AppSettings, Paths
from src.series.recap import fallback_recap_from_script
from src.series.store import find_or_create_series, register_episode, series_root_for
from UI.services.library_fs import scan_finished_videos


def _paths(tmp_path: Path) -> Paths:
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


def test_fallback_recap_first_last_sentences():
    text = "First bit. Second bit. Middle noise here! Fourth. Last end."
    out = fallback_recap_from_script(text)
    assert "First bit" in out or "First bit." in out
    assert "Last end" in out


def test_library_scan_finds_nested_series_episodes(tmp_path):
    paths = _paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    app = AppSettings()
    slug, _ = find_or_create_series(paths, app, display_name="My Show", episode_total=2)
    root = series_root_for(paths, slug)
    ep = root / "episode_001_Alpha"
    ep.mkdir(parents=True)
    (ep / "final.mp4").write_bytes(b"x" * 12_000)

    rows = scan_finished_videos(paths.videos_dir)
    assert len(rows) == 1
    assert "Series:" in rows[0].title
    assert "My Show" in rows[0].title
    assert "Ep 1" in rows[0].title
    assert rows[0].path.resolve() == ep.resolve()


def test_register_episode_paths_match_nested_layout(tmp_path):
    paths = _paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    app = AppSettings()
    slug, _ = find_or_create_series(paths, app, display_name="Arc", episode_total=1)
    root = series_root_for(paths, slug)
    ep_dir = root / "episode_001_Title"
    ep_dir.mkdir(parents=True)
    (ep_dir / "script.txt").write_text("A. B. C. D.", encoding="utf-8")
    rec = register_episode(
        paths,
        slug=slug,
        episode_index=1,
        title="Title",
        episode_project_dir=ep_dir,
        recap="Recap text.",
    )
    assert rec is not None
    assert rec.episodes[0].subdir == "episode_001_Title"
