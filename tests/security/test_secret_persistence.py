"""Secrets must never reach disk in plaintext, and every redaction path must cover every secret field."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import replace
from pathlib import Path

import pytest

from src.core.config import AppSettings, Paths
from src.settings.secrets_crypto import SECRET_FIELDS

# Settings whose names look secret but hold public identifiers or timestamps.
_NOT_SECRET = {"tiktok_client_key", "tiktok_token_expires_at", "youtube_token_expires_at"}
_SECRET_NAME = re.compile(r"(key|token|secret|password)", re.IGNORECASE)


def _settings_with_all_secrets() -> tuple[AppSettings, dict[str, str]]:
    values = {f: f"PLAINTEXT-{f}-0123456789" for f in SECRET_FIELDS}
    return replace(AppSettings(), **values), values


def _assert_no_plaintext(path: Path, values: dict[str, str]) -> None:
    raw = path.read_text(encoding="utf-8")
    leaked = [f for f, v in values.items() if v in raw]
    assert not leaked, f"plaintext secrets written to {path.name}: {leaked}"


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


def test_secret_fields_cover_every_secret_looking_setting() -> None:
    names = {f.name for f in dataclasses.fields(AppSettings) if _SECRET_NAME.search(f.name)}
    missing = sorted(names - set(SECRET_FIELDS) - _NOT_SECRET)
    assert not missing, f"add to SECRET_FIELDS (or _NOT_SECRET if public): {missing}"
    unknown = sorted(set(SECRET_FIELDS) - {f.name for f in dataclasses.fields(AppSettings)})
    assert not unknown, f"SECRET_FIELDS entries not on AppSettings: {unknown}"


def test_save_settings_encrypts_every_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.settings import ui_settings

    monkeypatch.setattr(ui_settings, "application_data_dir", lambda: tmp_path)
    settings, values = _settings_with_all_secrets()
    assert ui_settings.save_settings(settings)
    _assert_no_plaintext(ui_settings.settings_path(), values)

    loaded = ui_settings.load_settings()
    for field, value in values.items():
        assert getattr(loaded, field) == value


def test_pipeline_queue_store_encrypts_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.runtime import pipeline_queue_store as store

    monkeypatch.setattr(store, "application_data_dir", lambda: tmp_path)
    settings, values = _settings_with_all_secrets()
    assert store.save_pipeline_queue([{"kind": "pipeline", "settings": settings, "qty": 1}])
    _assert_no_plaintext(store.store_path(), values)

    restored = store.load_pipeline_queue()
    assert len(restored) == 1
    for field, value in values.items():
        assert getattr(restored[0]["settings"], field) == value


def test_series_snapshot_omits_secrets_and_rehydrates_from_live(tmp_path: Path) -> None:
    from src.series.rehydrate import rehydrate_settings_from_series_snapshot
    from src.series.store import find_or_create_series, load_series_record, series_root_for

    paths = _paths(tmp_path)
    paths.videos_dir.mkdir(parents=True)
    settings, values = _settings_with_all_secrets()
    slug, _ = find_or_create_series(paths, settings, display_name="Leak check", episode_total=2)
    root = series_root_for(paths, slug)
    _assert_no_plaintext(root / "series.json", values)

    record = load_series_record(root)
    assert record is not None
    live = replace(AppSettings(), **{f: f"live-{f}" for f in SECRET_FIELDS})
    eff = rehydrate_settings_from_series_snapshot(live=live, snapshot=record.settings_snapshot)
    for field in SECRET_FIELDS:
        assert getattr(eff, field) == f"live-{field}"


def test_run_report_snapshot_redacts_every_secret() -> None:
    from src.runtime.run_report import settings_snapshot

    settings, values = _settings_with_all_secrets()
    snap = settings_snapshot(settings)
    for field in values:
        assert snap[field] == "(redacted)"


def test_cli_config_show_redacts_every_secret() -> None:
    from src.cli.main import _redact_settings_dict

    settings, values = _settings_with_all_secrets()
    out = _redact_settings_dict(dataclasses.asdict(settings))
    leaked = [f for f, v in values.items() if out.get(f) == v]
    assert not leaked
