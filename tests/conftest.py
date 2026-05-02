from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _disable_memory_preflight_host_ram_gating(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent catastrophic-RAM shortfall checks from failing tests on constrained hosts.

    ``preflight_check`` imports ``check_stage_memory_*`` from ``memory_budget_preflight``
    on each call, so patching the module restores deterministic ``pytest`` runs.
    """

    monkeypatch.setattr(
        "src.runtime.memory_budget_preflight.check_stage_memory_hard_blocks",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        "src.runtime.memory_budget_preflight.check_stage_memory_budget",
        lambda **_kwargs: [],
    )


@pytest.fixture()
def tmp_repo_root(tmp_path: Path) -> Path:
    # Provides a fake repo root for path monkeypatching
    return tmp_path


@pytest.fixture()
def patch_paths(monkeypatch: pytest.MonkeyPatch, tmp_repo_root: Path):
    """
    Monkeypatch src.core.config.get_paths() to use a temp directory so tests don't touch real disk.
    """
    from src.core import config as config_mod

    def _fake_get_paths():
        root = tmp_repo_root
        ada = root / ".Aquaduct_data"
        data_dir = ada / "data"
        cache_dir = ada / ".cache"
        return config_mod.Paths(
            root=root,
            app_data_dir=ada,
            data_dir=data_dir,
            news_cache_dir=data_dir / "news_cache",
            runs_dir=ada / "runs",
            videos_dir=ada / "videos",
            pictures_dir=ada / "pictures",
            models_dir=ada / "models",
            cache_dir=cache_dir,
            ffmpeg_dir=cache_dir / "ffmpeg",
        )

    monkeypatch.setattr(config_mod, "get_paths", _fake_get_paths)
    # MainWindow does `from src.core.config import get_paths` — keep the same binding in sync.
    try:
        import importlib

        mw = importlib.import_module("UI.main_window")
        monkeypatch.setattr(mw, "get_paths", _fake_get_paths)
    except Exception:
        pass
    return _fake_get_paths


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch):
    """
    Disable real HTTP by making requests.get raise unless tests explicitly mock it.
    """
    import requests

    def _blocked(*args, **kwargs):
        raise RuntimeError("Network disabled in unit tests; mock requests.get")

    monkeypatch.setattr(requests, "get", _blocked)


@pytest.fixture()
def qapplication():
    """Minimal QApplication for UI unit tests when pytest-qt is not installed."""
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture()
def write_ui_settings(tmp_repo_root: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Helper to write ui_settings.json into a temp root and patch application_data_dir().
    """
    from src.settings import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "application_data_dir", lambda: tmp_repo_root)

    def _write(payload: dict) -> Path:
        p = tmp_repo_root / "ui_settings.json"
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return p

    return _write

