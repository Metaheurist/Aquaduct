"""Lightweight import smoke for API pipeline and UI modules used in frozen builds."""

from __future__ import annotations

import importlib

import pytest


def test_import_generation_facade() -> None:
    pytest.importorskip("torch")
    importlib.import_module("src.runtime.generation_facade")


def test_import_pipeline_api() -> None:
    pytest.importorskip("torch")
    importlib.import_module("src.runtime.pipeline_api")


def test_import_brain_api() -> None:
    importlib.import_module("src.content.brain_api")


def test_import_ui_api_model_widgets() -> None:
    pytest.importorskip("PyQt6.QtWidgets")
    importlib.import_module("UI.services.api_model_widgets")


def test_import_ui_tutorial_links() -> None:
    pytest.importorskip("PyQt6.QtWidgets")
    importlib.import_module("UI.help.tutorial_links")


def test_import_ui_title_bar_outline_button() -> None:
    pytest.importorskip("PyQt6.QtWidgets")
    importlib.import_module("UI.widgets.title_bar_outline_button")


def test_import_ui_frameless_dialog() -> None:
    pytest.importorskip("PyQt6.QtWidgets")
    importlib.import_module("UI.dialogs.frameless_dialog")
