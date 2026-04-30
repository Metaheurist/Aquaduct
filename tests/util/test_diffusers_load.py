from __future__ import annotations

import pytest


def test_diffusers_from_pretrained_passes_disable_mmap_when_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSERS_DISABLE_MMAP", "1")

    class _P:
        last_kw: dict

        @classmethod
        def from_pretrained(cls, load_path: str, **kw):  # noqa: ANN401
            cls.last_kw = dict(kw)
            return ("pipe", load_path)

    from src.util.diffusers_load import diffusers_from_pretrained

    r = diffusers_from_pretrained(_P, "/models/x", torch_dtype="half", low_cpu_mem_usage=True)
    assert r == ("pipe", "/models/x")
    assert _P.last_kw["disable_mmap"] is True
    assert _P.last_kw["low_cpu_mem_usage"] is True


def test_diffusers_from_pretrained_drops_disable_mmap_on_typeerror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSERS_DISABLE_MMAP", "1")

    class _P:
        attempts: list[dict] = []

        @classmethod
        def from_pretrained(cls, load_path: str, **kw):  # noqa: ANN401
            cls.attempts.append(dict(kw))
            if kw.get("disable_mmap"):
                raise TypeError("unsupported disable_mmap")
            return ("ok", load_path)

    from src.util.diffusers_load import diffusers_from_pretrained

    r = diffusers_from_pretrained(_P, "/y", foo=1)
    assert r == ("ok", "/y")
    assert any("disable_mmap" in a for a in _P.attempts)
    assert "disable_mmap" not in _P.attempts[-1]
