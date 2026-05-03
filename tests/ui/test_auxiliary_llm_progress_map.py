"""Pure mapping helpers for auxiliary generation progress dialogs."""

from __future__ import annotations

from UI.dialogs.auxiliary_progress_dialog import map_llm_on_task_to_overall


def test_map_llm_load_scales_first_band() -> None:
    assert map_llm_on_task_to_overall("llm_load", 0) == 0
    assert map_llm_on_task_to_overall("llm_load", 100) == 40
    assert map_llm_on_task_to_overall("llm_load", 50) == 20


def test_map_llm_generate_second_band() -> None:
    assert map_llm_on_task_to_overall("llm_generate", 0) == 40
    assert map_llm_on_task_to_overall("llm_generate", 100) == 100
    assert map_llm_on_task_to_overall("llm_generate", 50) == 70


def test_unknown_task_clamps_pct() -> None:
    assert map_llm_on_task_to_overall("other", -5) == 0
    assert map_llm_on_task_to_overall("", 111) == 100
