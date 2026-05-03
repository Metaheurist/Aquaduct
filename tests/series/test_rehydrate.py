from __future__ import annotations

from dataclasses import replace

from src.core.config import AppSettings, BrandingSettings
from src.series.rehydrate import merge_unlocked_style_from_live, rehydrate_settings_from_series_snapshot
from src.series.store import find_or_create_series, strip_lock_first_from_snapshot


def test_rehydrate_overlays_hf_token(tmp_path):
    from src.core.config import Paths

    paths = Paths(
        root=tmp_path,
        app_data_dir=tmp_path / ".Aquaduct_data",
        data_dir=tmp_path / ".Aquaduct_data" / "data",
        news_cache_dir=tmp_path / ".Aquaduct_data" / "data" / "news_cache",
        runs_dir=tmp_path / ".Aquaduct_data" / "runs",
        videos_dir=tmp_path / ".Aquaduct_data" / "videos",
        pictures_dir=tmp_path / ".Aquaduct_data" / "pictures",
        models_dir=tmp_path / ".Aquaduct_data" / "models",
        cache_dir=tmp_path / ".Aquaduct_data" / ".cache",
        ffmpeg_dir=tmp_path / ".Aquaduct_data" / ".cache" / "ffmpeg",
    )
    paths.videos_dir.mkdir(parents=True)
    snap = AppSettings(hf_token="OLD")
    slug, rec = find_or_create_series(paths, snap, display_name="X", episode_total=2)
    assert slug
    live = replace(AppSettings(), hf_token="NEW_SECRET")
    eff = rehydrate_settings_from_series_snapshot(live=live, snapshot=rec.settings_snapshot)
    assert eff.hf_token == "NEW_SECRET"


def test_strip_series_flags_in_snapshot():
    from dataclasses import asdict

    s = AppSettings()
    d = asdict(s)
    d["series"] = {"series_mode": True, "episode_count": 9, "series_name": "A"}
    out = strip_lock_first_from_snapshot(d)
    assert out["series"]["series_mode"] is False
    assert out["series"]["episode_count"] == 1


def test_merge_unlocked_style_overlays_live_models():
    base = AppSettings(
        art_style_preset_id="old",
        image_model_id="img_old",
        voice_model_id="v_old",
        active_character_id="c1",
        branding=BrandingSettings(),
    )
    live = replace(
        base,
        art_style_preset_id="newstyle",
        image_model_id="img_new",
        voice_model_id="v_new",
        active_character_id="c2",
    )
    m = merge_unlocked_style_from_live(base=base, live=live)
    assert m.art_style_preset_id == "newstyle"
    assert m.image_model_id == "img_new"
    assert m.voice_model_id == "v_new"
    assert m.active_character_id == "c2"
