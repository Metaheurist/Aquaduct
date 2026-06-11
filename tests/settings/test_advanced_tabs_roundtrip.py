"""advanced_tabs field roundtrip in ui_settings."""

from __future__ import annotations

from dataclasses import replace

from src.core.config import AppSettings
from src.settings.ui_settings import app_settings_from_dict, save_settings


def test_advanced_tabs_roundtrip(tmp_path, monkeypatch):
    from src.settings import ui_settings

    path = tmp_path / "ui_settings.json"
    monkeypatch.setattr(ui_settings, "settings_path", lambda: path)

    s = AppSettings(advanced_tabs={"pipeline": True, "video": False})
    assert save_settings(s)

    loaded = ui_settings.load_settings()
    assert loaded.advanced_tabs == {"pipeline": True, "video": False}


def test_advanced_tabs_from_dict_defaults_empty():
    s = app_settings_from_dict({})
    assert s.advanced_tabs == {}


def test_app_settings_from_dict_tolerates_null_nested_sections():
    s = app_settings_from_dict({"branding": None, "video": None, "picture": None})
    assert s.branding.palette_id == "default"
    assert s.video.width == 1080
    assert s.picture.output_type == "single_image"
