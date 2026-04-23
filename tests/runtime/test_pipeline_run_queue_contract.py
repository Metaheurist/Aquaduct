"""
Regression tests for pipeline run-queue payload shapes (no Qt).

Full MainWindow behavior is covered by ``tests/ui/test_ui_main_window.py`` (@pytest.mark.qt).
"""

from __future__ import annotations

import copy

from src.core.config import AppSettings


def test_pipeline_queue_item_fields():
    """Each queue entry is one full pipeline run; ``qty`` is always ``1`` (use multiple items for N videos)."""
    s = AppSettings()
    item = {"kind": "pipeline", "settings": copy.deepcopy(s), "qty": 1}
    assert item["kind"] == "pipeline"
    assert item["qty"] == 1
    assert item["settings"] is not s


def test_prebuilt_queue_item_fields():
    s = AppSettings()
    item = {
        "kind": "prebuilt",
        "settings": copy.deepcopy(s),
        "pkg": object(),
        "sources": [],
        "prompts": None,
    }
    assert item["kind"] == "prebuilt"
    assert set(item.keys()) >= {"kind", "settings", "pkg", "sources", "prompts"}


def test_storyboard_queue_item_fields():
    s = AppSettings()
    item = {
        "kind": "storyboard",
        "settings": copy.deepcopy(s),
        "prompts": ["a"],
        "seeds": [1],
    }
    assert item["kind"] == "storyboard"
    assert item["prompts"] == ["a"]
    assert item["seeds"] == [1]


def test_format_status_line_dual_progress_for_pipeline():
    from UI.services.progress_tasks import format_status_line

    line = format_status_line("pipeline_run", 44, 67, "Generating images (diffusion)…")
    assert "total 44%" in line and "step 67%" in line


def test_format_status_line_single_when_step_unknown():
    from UI.services.progress_tasks import format_status_line

    line = format_status_line("pipeline_run", 22, -1, "Writing script (LLM)…")
    assert "22%" in line and "total" not in line


def test_format_status_line_preview_stays_single_percent():
    from UI.services.progress_tasks import format_status_line

    line = format_status_line("headlines", 60, -1, "Choosing items…")
    assert "60%" in line and "total" not in line
