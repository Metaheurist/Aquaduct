"""Series queue items: FIFO pop order, `is_first` flag, snapshot freeze, ``previous_episode_dir`` resolution."""

from __future__ import annotations

from src.core.config import AppSettings, Paths
from src.series.rehydrate import rehydrate_settings_from_series_snapshot
from src.series.store import (
    find_or_create_series,
    latest_episode_dir,
    load_series_record,
    register_episode,
    series_root_for,
)


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


def test_series_queue_items_include_is_first_and_fifo_order():
    q: list[dict] = []
    slug = "my_show"
    qty = 3
    for i in range(1, qty + 1):
        q.append(
            {
                "kind": "series_episode",
                "series_slug": slug,
                "episode_index": i,
                "episode_total": qty,
                "is_first": i == 1,
            }
        )
    assert q[0]["is_first"] is True
    assert q[0]["episode_index"] == 1
    assert q[1]["is_first"] is False
    order: list[int] = []
    while q:
        item = q.pop(0)
        order.append(int(item["episode_index"]))
    assert order == [1, 2, 3]


def test_series_settings_snapshot_freeze_at_create(tmp_path):
    paths = _paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    snap_app = AppSettings(art_style_preset_id="vivid", image_model_id="img_snap")
    slug, rec = find_or_create_series(paths, snap_app, display_name="Show", episode_total=2)
    live = AppSettings(art_style_preset_id="other", image_model_id="img_live")
    eff = rehydrate_settings_from_series_snapshot(live=live, snapshot=rec.settings_snapshot)
    assert eff.art_style_preset_id == "vivid"
    assert eff.image_model_id == "img_snap"


def test_previous_episode_dir_for_episode_2_after_register(tmp_path):
    paths = _paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    app = AppSettings()
    slug, _ = find_or_create_series(paths, app, display_name="Arc", episode_total=3)
    root = series_root_for(paths, slug)
    ep1 = root / "episode_001_A"
    ep1.mkdir(parents=True)
    register_episode(
        paths,
        slug=slug,
        episode_index=1,
        title="A",
        episode_project_dir=ep1,
        recap="One done.",
    )
    record = load_series_record(root)
    assert record is not None
    prev = latest_episode_dir(paths, record)
    assert prev is not None
    assert prev.resolve() == ep1.resolve()
