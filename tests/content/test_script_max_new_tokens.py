"""Tests for script completion token clamping (JSON batch relax path)."""

from unittest.mock import MagicMock

import pytest

import src.models.inference_profiles as inference_profiles
from src.content.brain import _script_generation_max_new_tokens


@pytest.fixture
def patch_script_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_resolve(*, kind: str, settings: object) -> float:
        return 8.0

    def fake_pick(repo_id: str, vram_gb: float | None) -> MagicMock:
        m = MagicMock()
        m.max_new_tokens = 384
        return m

    monkeypatch.setattr(inference_profiles, "resolve_effective_vram_gb", fake_resolve)
    monkeypatch.setattr(inference_profiles, "pick_script_profile", fake_pick)


def test_relax_short_json_batch_allows_above_narrative_cap(patch_script_profile: None) -> None:
    st = MagicMock()
    assert (
        _script_generation_max_new_tokens(
            1200,
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            inference_settings=st,
            relax_short_json_batch=True,
        )
        == 1200
    )
    assert (
        _script_generation_max_new_tokens(
            3000,
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            inference_settings=st,
            relax_short_json_batch=True,
        )
        == 1536
    )


def test_narrative_path_stays_at_profile_cap(patch_script_profile: None) -> None:
    st = MagicMock()
    assert (
        _script_generation_max_new_tokens(
            1200,
            model_id="x",
            inference_settings=st,
            relax_short_json_batch=False,
        )
        == 384
    )
