"""Round-trip ``series`` block in ui_settings / AppSettings."""

from __future__ import annotations

from src.core.config import AppSettings, SeriesSettings
from src.settings.ui_settings import app_settings_from_dict


def test_series_roundtrip_via_dict():
    s = AppSettings(
        series=SeriesSettings(
            series_mode=True,
            series_name="My Arc",
            episode_count=5,
            lock_style=True,
            carry_recap=False,
            source_strategy="lock_first",
            continue_on_failure=True,
        )
    )
    from dataclasses import asdict

    d2 = asdict(s)
    s2 = app_settings_from_dict(d2)
    assert s2.series.series_mode is True
    assert s2.series.series_name == "My Arc"
    assert s2.series.episode_count == 5
    assert s2.series.carry_recap is False
    assert s2.series.source_strategy == "lock_first"
    assert s2.series.continue_on_failure is True


def test_series_defaults_restored():
    s2 = app_settings_from_dict({})
    assert s2.series.series_mode is False
    assert s2.series.episode_count == 1
