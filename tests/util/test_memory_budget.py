from __future__ import annotations

from src.util.memory_budget import release_between_stages


def test_release_between_stages_cheap_calls_cleanup_only(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr("src.util.memory_budget.cleanup_vram", lambda: calls.append("clean"))
    monkeypatch.setattr(
        "src.util.memory_budget.prepare_for_next_model",
        lambda cuda_device_index=None: calls.append(("prep", cuda_device_index)),
    )
    release_between_stages("stage_a", variant="cheap")
    assert calls == ["clean"]


def test_release_between_stages_prepare_calls_prepare(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr("src.util.memory_budget.cleanup_vram", lambda: calls.append("clean"))
    monkeypatch.setattr(
        "src.util.memory_budget.prepare_for_next_model",
        lambda cuda_device_index=None: calls.append(("prep", cuda_device_index)),
    )
    release_between_stages("stage_b", cuda_device_index=2, variant="prepare_diffusion")
    assert calls == [("prep", 2)]
