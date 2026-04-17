"""
Regression tests for pipeline run-queue payload shapes (no Qt).

Full MainWindow behavior is covered by ``tests/test_ui_main_window.py`` (@pytest.mark.qt).
"""

from __future__ import annotations

import copy

from src.config import AppSettings


def test_pipeline_queue_item_fields():
    s = AppSettings()
    item = {"kind": "pipeline", "settings": copy.deepcopy(s), "qty": 3}
    assert item["kind"] == "pipeline"
    assert item["qty"] == 3
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
