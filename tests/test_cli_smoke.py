"""Smoke tests for headless CLI (parser + settings wiring)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.cli.main import EXIT_OK, main as cli_main
from src.cli.parser import build_parser
from src.cli.settings_merge import merge_partial_app_settings
from src.core.config import AppSettings
from src.settings.ui_settings import app_settings_from_dict


def test_parser_run_requires_once_or_watch() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["run"])


def test_parser_run_once() -> None:
    p = build_parser()
    a = p.parse_args(["run", "--once"])
    assert a.once is True


def test_parser_config_show() -> None:
    p = build_parser()
    a = p.parse_args(["config", "show", "--no-secrets"])
    assert a.config_cmd == "show"
    assert a.no_secrets is True


def test_merge_partial_video_format() -> None:
    base = AppSettings()
    out = merge_partial_app_settings(base, {"video_format": "cartoon"})
    assert out.video_format == "cartoon"


def test_app_settings_from_dict_roundtrip_minimal() -> None:
    d = {"video_format": "news", "video": {"fps": 24}}
    s = app_settings_from_dict(d)
    assert s.video_format == "news"
    assert s.video.fps == 24


def test_cli_version_exit_code() -> None:
    code = cli_main(["version"])
    assert code == EXIT_OK


def test_cli_config_path_prints_line(capsys) -> None:
    code = cli_main(["config", "path"])
    assert code == EXIT_OK
    out = capsys.readouterr().out.strip()
    assert "ui_settings.json" in out


def test_cli_run_once_dry_run_mock_preflight(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from src.runtime.preflight import PreflightResult

    monkeypatch.setattr(
        "src.cli.main.preflight_check",
        lambda **kwargs: PreflightResult(ok=True, errors=[], warnings=[]),
    )
    code = cli_main(["run", "--once", "--dry-run"])
    assert code == EXIT_OK
    err = capsys.readouterr().err
    assert "Dry run" in err or "preflight OK" in err.lower()


def test_main_cli_daemon_loop_loads_settings_from_disk() -> None:
    """Regression: --cli watch loop must call load_settings() (not bare AppSettings())."""
    root = Path(__file__).resolve().parents[1]
    text = (root / "main.py").read_text(encoding="utf-8")
    start = text.find("while True:")
    assert start != -1
    chunk = text[start : start + 1200]
    assert "load_settings()" in chunk
