from __future__ import annotations

import pytest


def test_migrates_legacy_repo_layout_into_app_data(monkeypatch, tmp_path):
    import src.app_dirs as ad

    monkeypatch.setattr(ad, "_migrated", False)
    monkeypatch.setattr(ad, "installation_dir", lambda: tmp_path)

    (tmp_path / "ui_settings.json").write_text('{"x": 1}', encoding="utf-8")
    legacy_data = tmp_path / "data"
    legacy_data.mkdir()
    (legacy_data / "marker.txt").write_text("ok", encoding="utf-8")

    ada = ad.application_data_dir()

    assert ada == tmp_path / ".Aquaduct_data"
    assert (ada / "ui_settings.json").read_text(encoding="utf-8") == '{"x": 1}'
    assert (ada / "data" / "marker.txt").read_text(encoding="utf-8") == "ok"
    assert not (tmp_path / "ui_settings.json").is_file()
    assert not legacy_data.exists()


def test_get_paths_uses_app_data_subdirs(monkeypatch, tmp_path):
    import src.app_dirs as ad
    from src.config import get_paths

    monkeypatch.setattr(ad, "_migrated", False)
    monkeypatch.setattr(ad, "installation_dir", lambda: tmp_path)

    p = get_paths()
    assert p.app_data_dir == tmp_path / ".Aquaduct_data"
    assert p.data_dir == p.app_data_dir / "data"
    assert p.cache_dir == p.app_data_dir / ".cache"
    assert p.runs_dir == p.app_data_dir / "runs"
