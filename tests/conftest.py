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
def paths_under_tmp(tmp_path: Path):
    """Canonical ``Paths`` layout under a temp root (matches ``patch_paths`` / series tests)."""
    from src.core.config import Paths

    ada = tmp_path / ".Aquaduct_data"
    data_dir = ada / "data"
    cache_dir = ada / ".cache"
    return Paths(
        root=tmp_path,
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


@pytest.fixture()
def patch_paths(monkeypatch: pytest.MonkeyPatch, tmp_repo_root: Path):
    """
    Monkeypatch src.core.config.get_paths() to use a temp directory so tests don't touch real disk.

    Tests should call ``config.get_paths()`` (attribute on ``src.core.config``) or a helper patched
    here — avoid ``from src.core.config import get_paths`` at module level, or the name keeps the
    pre-patch function object.
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
    # Modules that did `from src.core.config import get_paths` at import time keep the old function
    # object — patch their copy so tests using those helpers hit the temp layout.
    monkeypatch.setattr("src.content.characters.store.get_paths", _fake_get_paths)
    monkeypatch.setattr("src.content.characters_store.get_paths", _fake_get_paths)
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


@pytest.fixture(autouse=True)
def _fast_main_window_for_qt_tests(monkeypatch, request):
    """Skip heavy background work when constructing MainWindow in @pytest.mark.qt tests."""
    if request.node.get_closest_marker("qt") is None:
        return
    monkeypatch.setattr(
        "src.content.llm_chat_rag.build_chat_docs_index",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "UI.main_window.MainWindow._start_chat_docs_index_build",
        lambda self: None,
    )
    monkeypatch.setattr(
        "UI.main_window.MainWindow._tasks_refresh",
        lambda self: None,
    )
    monkeypatch.setattr(
        "UI.main_window.MainWindow._maybe_prompt_hf_token",
        lambda self: None,
    )
    monkeypatch.setattr(
        "UI.main_window.MainWindow._maybe_show_first_run_tutorial",
        lambda self: None,
    )


@pytest.fixture()
def qtbot(qapplication):
    """
    Minimal `qtbot` shim for UI tests when pytest-qt isn't available.

    Supports the subset used in this repo: `addWidget()` and `waitUntil()`.
    """
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtTest import QTest

    class _QtBotShim:
        def __init__(self):
            self._widgets = []

        def addWidget(self, w) -> None:
            self._widgets.append(w)
            try:
                w.show()
            except Exception:
                pass
            try:
                qapplication.processEvents()
            except Exception:
                pass

        def waitUntil(self, predicate, *, timeout: int = 5000, interval: int = 50) -> None:
            end = time.time() + (max(0, int(timeout)) / 1000.0)
            while time.time() < end:
                try:
                    if predicate():
                        return
                except Exception:
                    pass
                try:
                    qapplication.processEvents()
                except Exception:
                    pass
                QTest.qWait(max(1, int(interval)))
            raise AssertionError("qtbot.waitUntil timed out")

    return _QtBotShim()


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

