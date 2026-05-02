"""Phase 2/7 tests for smoothness preflight warnings in ``src/runtime/preflight.py``.

We validate that selecting ``smoothness_mode='rife'`` produces actionable warnings
when the optional package is missing, when VRAM is too tight, or when the run is
in API mode (where post-render smoothing is a no-op). The ``ffmpeg`` and ``off``
modes never warn because the bundled FFmpeg is always available.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.core.config import AppSettings, VideoSettings
from src.runtime import preflight


def _settings_with_smoothness(mode: str) -> AppSettings:
    video = dataclasses.replace(VideoSettings(), smoothness_mode=mode)
    return dataclasses.replace(AppSettings(), video=video)


def test_off_mode_no_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "is_api_mode", lambda s: False)
    assert preflight._preflight_smoothness_warnings(_settings_with_smoothness("off")) == []


def test_ffmpeg_mode_no_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "is_api_mode", lambda s: False)
    assert preflight._preflight_smoothness_warnings(_settings_with_smoothness("ffmpeg")) == []


def test_rife_mode_in_api_mode_emits_skip_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "is_api_mode", lambda s: True)
    out = preflight._preflight_smoothness_warnings(_settings_with_smoothness("rife"))
    assert len(out) == 1
    assert "API-mode" in out[0]
    assert "skip" in out[0].lower()


def test_rife_warning_when_package_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "is_api_mode", lambda s: False)
    from src.render import temporal_smooth as ts

    monkeypatch.setattr(ts, "rife_available", lambda: False)
    monkeypatch.setattr(ts, "rife_vram_budget_ok", lambda *, free_vram_mb=None: True)
    out = preflight._preflight_smoothness_warnings(_settings_with_smoothness("rife"))
    assert any("rife_ncnn_vulkan_python" in w for w in out)
    assert any("FFmpeg" in w for w in out)


def test_rife_warning_when_vram_tight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "is_api_mode", lambda s: False)
    from src.render import temporal_smooth as ts

    monkeypatch.setattr(ts, "rife_available", lambda: True)
    monkeypatch.setattr(ts, "rife_vram_budget_ok", lambda *, free_vram_mb=None: False)
    out = preflight._preflight_smoothness_warnings(_settings_with_smoothness("rife"))
    assert any("free VRAM" in w for w in out)


def test_rife_no_warning_when_everything_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "is_api_mode", lambda s: False)
    from src.render import temporal_smooth as ts

    monkeypatch.setattr(ts, "rife_available", lambda: True)
    monkeypatch.setattr(ts, "rife_vram_budget_ok", lambda *, free_vram_mb=None: True)
    out = preflight._preflight_smoothness_warnings(_settings_with_smoothness("rife"))
    assert out == []
