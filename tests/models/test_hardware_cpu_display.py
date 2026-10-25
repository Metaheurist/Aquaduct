from __future__ import annotations

import platform

import pytest

from src.models import hardware
from src.models.hardware import _format_cpu_display_line


def test_cpu_brand_lookup_runs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def _fake() -> tuple[str, float]:
        calls.append(1)
        return "Fake CPU", 3.0

    hardware._cpu_brand_clock_detect.cache_clear()
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(hardware, "_cpu_brand_clock_windows", _fake)
    try:
        assert hardware._cpu_brand_clock() == ("Fake CPU", 3.0)
        assert hardware._cpu_brand_clock() == ("Fake CPU", 3.0)
        assert len(calls) == 1
    finally:
        hardware._cpu_brand_clock_detect.cache_clear()


def test_format_cpu_display_shows_clock_when_known() -> None:
    s = _format_cpu_display_line(
        fallback="AMD64 Family 25 Model 33 Stepping 2, AuthenticAMD",
        friendly="AMD Ryzen 9 5900X 12-Core Processor",
        clock_ghz=3.8,
    )
    assert "Ryzen" in s
    assert "~3.80 GHz max" in s


def test_format_cpu_display_fallback_when_no_friendly_name() -> None:
    s = _format_cpu_display_line(fallback="SomeCPU", friendly=None, clock_ghz=2.5)
    assert s.startswith("SomeCPU")
    assert "~2.50 GHz max" in s


def test_format_cpu_display_no_clock_suffix_when_missing() -> None:
    s = _format_cpu_display_line(fallback="AMD64 …", friendly="AMD Ryzen 7 5800X", clock_ghz=None)
    assert "~GHz" not in s
